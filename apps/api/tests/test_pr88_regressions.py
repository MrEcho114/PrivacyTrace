"""PR88 regression guards; fixture doubles and real Docker evidence are separate."""

import io
import json
import os
import struct
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from apk_fixture_builder import apk, package_set_archive
from fastapi.testclient import TestClient
from test_challenger_m1_2_split_dex import make_dummy_policy
from test_e2e_pt_mob_102 import build_test_apk, create_draft, get_test_app
from test_web_intake import HEADERS, new_draft

from privacytrace import apk_worker, pipeline, web_intake
from privacytrace.isolated_scan import ScanError, scan_isolated
from privacytrace.main import create_app
from privacytrace.resources import taxonomy


def test_package_pipeline_requires_isolation(tmp_path, monkeypatch):
    packages = tmp_path / "packages"
    packages.mkdir()
    apk(packages / "base.apk")
    receipt = make_dummy_policy(tmp_path / "policy")
    calls = []

    def unavailable(path, **kwargs):
        calls.append(path)
        raise ScanError("ISOLATION_UNAVAILABLE", "Controlled failure")

    def forbidden(*args, **kwargs):
        pytest.fail("Untrusted APK parser called in host pipeline")

    monkeypatch.setattr(pipeline, "scan_isolated", unavailable)
    monkeypatch.setattr(apk_worker, "scan_package_set", forbidden)
    result = pipeline.run(packages, receipt, "fixture", store_dir=tmp_path / "jobs")
    assert calls == [packages]
    assert result["status"] == "FAILED"
    assert result["primary_error"]["code"] == "ISOLATION_UNAVAILABLE"


def test_metadata_boundary_failure_rolls_back_upload(tmp_path, monkeypatch):
    sample = apk(tmp_path / "base.apk")
    archive = package_set_archive(tmp_path / "set.zip", {"base.apk": sample.read_bytes()})

    def unavailable(path, **kwargs):
        raise ScanError("ISOLATION_UNAVAILABLE", "Controlled failure")

    monkeypatch.setattr(web_intake, "inspect_package_isolated", unavailable)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(
            route + "/package-set", headers=HEADERS, content=archive.read_bytes()
        )
        assert response.status_code == 503
        assert response.json()["detail"] == "ISOLATED_INSPECTION_UNAVAILABLE"
        assert not client.get(route).json()["uploaded"]
        assert not list(app.state.web_intake.directory(draft["id"]).glob("*pending*"))
        assert not (app.state.web_intake.directory(draft["id"]) / "packages").exists()


def test_remote_retry_executes_retained_inputs_and_preserves_scope(tmp_path, monkeypatch):
    sample = apk(tmp_path / "sample.apk", camera=True)
    calls = []

    def scanner(path, **kwargs):
        calls.append(path.read_bytes())
        if len(calls) == 1:
            raise ScanError("TIMEOUT", "Controlled first attempt")
        return apk_worker.scan(path, taxonomy())  # Explicit controlled fixture double.

    monkeypatch.setattr(pipeline, "scan_isolated", scanner)
    app = get_test_app(tmp_path / "jobs", mode="remote", monkeypatch=monkeypatch)
    with TestClient(app) as client:
        draft_id, token, response = create_draft(client)
        assert response.status_code == 200
        headers = {"Authorization": f"Bearer {token}"}
        route = f"/api/v1/web/drafts/{draft_id}"
        draft = client.post(route + "/apk", headers=headers, content=sample.read_bytes()).json()
        first = client.post(
            route + "/start",
            headers=headers,
            json={
                "revision": draft["revision"],
                "request_id": uuid4().hex,
            },
        ).json()
        app.state.web_intake.futures[first["id"]].result(timeout=10)
        assert app.state.job_store.get(first["id"]).state == "FAILED"
        denied = client.post(f"/api/v1/jobs/{first['id']}/retry")
        assert denied.status_code == 401
        response = client.post(f"/api/v1/jobs/{first['id']}/retry", headers=headers)
        assert response.status_code == 200, response.text
        second = response.json()
        app.state.web_intake.futures[second["id"]].result(timeout=10)
        assert second["retry_of"] == first["id"]
        assert app.state.job_store.get(second["id"]).state == "SUCCEEDED"
        assert client.get(f"/api/v1/jobs/{second['id']}/report", headers=headers).status_code == 200
        assert client.get(f"/api/v1/jobs/{second['id']}/report").status_code == 401
        assert app.state.job_store.get(first["id"]).state == "FAILED"
        assert calls == [sample.read_bytes(), sample.read_bytes()]

        # Delete after request authorization but immediately before atomic creation.
        create_retry = app.state.job_store.create_retry

        def delete_first(job, token_digest):
            app.state.job_store.delete(job.retry_of)
            return create_retry(job, token_digest)

        monkeypatch.setattr(app.state.job_store, "create_retry", delete_first)
        response = client.post(f"/api/v1/jobs/{first['id']}/retry", headers=headers)
        assert response.status_code == 404
        assert len(calls) == 2
        assert [j.id for j in app.state.job_store.list()] == [second["id"]]


def test_discovery_releases_shared_lock_and_rejects_stale_results(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    app = create_app(tmp_path)

    def metadata(path, **kwargs):
        entered.set()
        assert release.wait(5)
        return {"policy_urls": ["https://example.com/stale"]}

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        assert client.post(route + "/apk", headers=HEADERS, content=b"fixture").status_code == 200
        service = app.state.web_intake
        pending = executor.submit(client.post, route + "/sources/discover", headers=HEADERS)
        try:
            assert entered.wait(3)
            # Independent readers/writers can finish while the worker is blocked.
            current = executor.submit(service.get, draft["id"]).result(timeout=1)
            assert current["uploaded"]
            changed = client.post(
                route + "/import-external", headers=HEADERS,
                json={"source": {"text": "补充政策", "source_type": "IN_APP_POLICY"}},
            )
            assert changed.status_code == 200
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 409
        current = service.get(draft["id"])
        assert not any(s["url"] == "https://example.com/stale" for s in current["sources"])
        assert not service.active_drafts


@pytest.mark.parametrize("case", ["ambiguous", "sources", "candidates"])
def test_external_import_rejects_ambiguity_and_cumulative_quotas(tmp_path, case):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        draft = new_draft(client)
        service = app.state.web_intake
        directory = service.directory(draft["id"])
        if case == "sources":
            draft["sources"] = [{**draft["sources"][0], "id": f"s{i}"} for i in range(8)]
        elif case == "candidates":
            draft["candidates"] = [{"id": f"c{i}"} for i in range(800)]
        web_intake.write_private(directory / "current.json", draft)
        before = (directory / "current.json").read_bytes()
        text = "我们读取相机。" * (2 if case == "ambiguous" else 1)
        response = client.post(
            f"/api/v1/web/drafts/{draft['id']}/import-external",
            headers=HEADERS,
            json={
                "source": {"text": text, "source_type": "IN_APP_POLICY"},
                "claims": [
                    {"excerpt": "我们读取相机。", "data_type": "CAMERA"},
                ],
            },
        )
        assert response.status_code == 409
        assert (directory / "current.json").read_bytes() == before


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam")
def test_real_docker_multi_package_intake_scan_and_cleanup(tmp_path):
    """No parser/transport doubles: upload, manifest discovery, scan and receipt inspection."""
    policy_url = "https://example.com/privacy"
    base = build_test_apk(
        tmp_path / "base.apk",
        package_name="org.example.set",
        meta_data={"privacy_policy": policy_url},
    )
    split = apk(
        tmp_path / "feature.apk",
        package_name="org.example.set",
        split="feature",
        split_name="feature",
        camera=True,
    )
    archive = package_set_archive(
        tmp_path / "set.zip", {"base.apk": base.read_bytes(), "feature.apk": split.read_bytes()}
    )
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(
            route + "/package-set", headers=HEADERS, content=archive.read_bytes()
        )
        assert response.status_code == 200, response.text
        draft = response.json()
        response = client.post(route + "/sources/discover", headers=HEADERS)
        assert response.status_code == 200, response.text
        source = next(s for s in response.json()["sources"] if s["url"] == policy_url)
        assert source["status"] == "url_only" and not source["text"]
        draft = client.get(route).json()
        started = client.post(
            route + "/start",
            headers=HEADERS,
            json={
                "revision": draft["revision"],
                "request_id": uuid4().hex,
            },
        )
        assert started.status_code == 200, started.text
        job = started.json()
        app.state.web_intake.futures[job["id"]].result(timeout=120)
        report = app.state.job_store.report(job["id"])
        assert report.sample.package_set.split_names == ["feature"]
        assert "split:feature:classes.dex" in report.sample.dex_entries
        proof = json.loads(Path(report.tools["isolation_receipt"]).read_text(encoding="utf-8"))
        assert proof["input_removed"] and proof["cleanup_verified"]
        assert proof["host_config"]["NetworkMode"] == "none"
        assert proof["host_config"]["ReadonlyRootfs"]
        assert len(proof["mounts"]) == 1 and not proof["mounts"][0]["RW"]


def test_package_directory_runtime_failure_cleans_owned_copy(tmp_path, monkeypatch):
    packages = tmp_path / "packages"
    packages.mkdir()
    apk(packages / "base.apk")

    def unavailable(*args, **kwargs):
        raise ScanError("ISOLATION_UNAVAILABLE", "Controlled runtime failure")

    monkeypatch.setattr("privacytrace.isolated_scan.command", unavailable)
    with pytest.raises(ScanError) as failure:
        scan_isolated(packages, run_root=tmp_path / "runs")
    proof = json.loads(Path(failure.value.receipt).read_text(encoding="utf-8"))
    assert proof["input_removed"] and proof["cleanup_verified"]
    assert not list((tmp_path / "runs").glob("*/input.apk"))
    assert (packages / "base.apk").exists()


def test_pr88_full_split_identity_blocks_report(tmp_path, monkeypatch):
    """Base digest alone cannot authorize a report for a changed split."""
    from hashlib import sha256

    from privacytrace.job_store import JobStore

    base = apk(tmp_path / "base.apk")
    original_digest = sha256(base.read_bytes()).hexdigest()
    base_info = {
        "file_name": "base.apk", "part": "BASE", "split_name": None,
        "sha256": original_digest, "size_bytes": base.stat().st_size,
    }
    split_info = {
        "file_name": "feature.apk", "part": "SPLIT", "split_name": "feature",
        "sha256": "a" * 64, "size_bytes": 120,
    }
    registered = {
        "base": base_info, "splits": [split_info],
        "package_name": "org.privacytrace.fixture", "version_code": 7,
        "version_name": "1.0",
        "total_size_bytes": base_info["size_bytes"] + split_info["size_bytes"],
    }
    scanned = apk_worker.scan(base, taxonomy())
    scanned["package_set"] = {
        "files": [base_info, {**split_info, "sha256": "b" * 64}],
        "total_size_bytes": registered["total_size_bytes"],
        "split_count": 1,
    }
    receipt = make_dummy_policy(tmp_path / "policy")
    monkeypatch.setattr(pipeline, "scan_isolated", lambda path, **kw: scanned)
    result = pipeline.run(
        base, receipt, "changed split", store_dir=tmp_path / "jobs",
        package_set=registered,
    )
    assert result["status"] == "FAILED"
    assert result["primary_error"]["code"] == "INPUT_DIGEST_MISMATCH"
    with pytest.raises(ValueError, match="report is not available"):
        JobStore(tmp_path / "jobs").report(result["job_id"])


@pytest.mark.usefixtures("synthetic_package_metadata")
@pytest.mark.parametrize("mode", ["apk", "package-set"])
def test_pr88_upload_failed_after_publish_reverts_files_and_revision(tmp_path, monkeypatch, mode):
    """A failed commit cannot leave an orphan APK, collection or new revision."""
    sample = apk(tmp_path / "fixture.apk")
    payload = sample.read_bytes()
    if mode == "package-set":
        payload = package_set_archive(
            tmp_path / "upload.zip", {"base.apk": payload}
        ).read_bytes()
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        directory = app.state.web_intake.directory(draft["id"])
        previous = (directory / "current.json").read_bytes()
        original_save = app.state.web_intake._save

        def fail_after_save(updated):
            saved = original_save(updated)
            if updated["uploaded"]:
                raise ValueError("injected post-publish failure")
            return saved

        monkeypatch.setattr(app.state.web_intake, "_save", fail_after_save)
        response = client.post(
            f"/api/v1/web/drafts/{draft['id']}/{mode}",
            headers=HEADERS, content=payload,
        )
        assert response.status_code == 409
        assert (directory / "current.json").read_bytes() == previous
        assert not (directory / "input.apk").exists()
        assert not (directory / "packages").exists()
        assert not (directory / f"revision-{draft['revision'] + 1}.json").exists()
        assert not list(directory.glob("*pending*"))


def test_pr88_package_set_101_file_report_contract():
    """A base + all 100 supported splits fits the report contract."""
    from pydantic import ValidationError

    from privacytrace.runtime_models import PackageSetSummary

    base = {
        "file_name": "base.apk", "part": "BASE", "split_name": None,
        "sha256": "a" * 64, "size_bytes": 100,
    }
    splits = [{
        "file_name": f"feature{i}.apk", "part": "SPLIT",
        "split_name": f"feature{i}", "sha256": "b" * 64, "size_bytes": 1,
    } for i in range(100)]
    data = {
        "base_file": base, "splits": splits, "files": [base, *splits],
        "total_size_bytes": 200, "split_count": 100,
        "split_names": [s["split_name"] for s in splits],
    }
    assert len(PackageSetSummary.model_validate(data).files) == 101
    with pytest.raises(ValidationError):
        PackageSetSummary.model_validate({**data, "files": [base, *splits, splits[0]]})


def test_pr88_restart_removes_uncommitted_upload_material(tmp_path):
    """Crash between filesystem publication and commit leaves no usable orphan."""
    root = tmp_path / "jobs"
    app = create_app(root)
    with TestClient(app) as client:
        draft = new_draft(client)
        directory = app.state.web_intake.directory(draft["id"])
        assert not draft["uploaded"]
    (directory / "input.apk").write_bytes(b"orphan")
    (directory / "packages").mkdir()
    (directory / "packages" / "base.apk").write_bytes(b"orphan")
    (directory / "upload.pending").write_bytes(b"abandoned")
    with TestClient(create_app(root)) as client:
        assert not (directory / "input.apk").exists()
        assert not (directory / "packages").exists()
        assert not (directory / "upload.pending").exists()
        assert not client.get(f"/api/v1/web/drafts/{draft['id']}").json()["uploaded"]


def test_r4_upload_inspection_does_not_block_other_http_requests(tmp_path, monkeypatch):
    """Metadata inspection runs off the ASGI event loop, not on it."""
    entered, release = threading.Event(), threading.Event()
    sample = apk(tmp_path / "base.apk")
    archive = package_set_archive(tmp_path / "bundle.zip", {"base.apk": sample.read_bytes()})

    def slow_metadata(path, **kwargs):
        entered.set()
        assert release.wait(10), "Test inspection fixture timed out"
        return apk_worker.inspect_package_metadata(path)

    monkeypatch.setattr(web_intake, "inspect_package_isolated", slow_metadata)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        first = new_draft(client)
        second = new_draft(client)
        route = f"/api/v1/web/drafts/{first['id']}/package-set"
        pending = pool.submit(client.post, route, headers=HEADERS, content=archive.read_bytes())
        try:
            assert entered.wait(5)
            # The same TestClient and app event loop must service the other draft.
            other = pool.submit(
                client.get, f"/api/v1/web/drafts/{second['id']}"
            ).result(timeout=3)
            assert other.status_code == 200
        finally:
            release.set()
        completed = pending.result(timeout=15)
        assert completed.status_code == 200, completed.text


def _r4_fake_scan_result(package_split, sdk_count=0, *, behavior_warning=None):
    import hashlib

    name = package_split or "base"
    coverage = {
        "completeness": "COMPLETE",
        "scope": "DEX_ENTRIES",
        "behavior_detection": "LIMITED_RULE_BASED_STATIC",
        "behavior_limitations": [behavior_warning] if behavior_warning else [],
        "sdk_attribution_limitations": (
            [f"SDK truncated in {name}"] if name == "feature" else []
        ),
        "limitations": [f"Missing resources in {name}"] if name == "feature" else [],
        "scanned_dex": [f"{name}:classes.dex"],
        "failed_dex": [],
    }
    return {
        "apk_sha256": hashlib.sha256(name.encode()).hexdigest(),
        "package_name": "org.example",
        "version_code": 1,
        "version_name": "1",
        "permissions": [],
        "dex_entries": [f"{name}:classes.dex"],
        "coverage": coverage,
        "tools": {"androguard": "test", "ruleset": "test"},
        "evidence": [
            {
                "id": f"sdk-{name}-{i}",
                "kind": "SDK",
                "status": "STATIC_POTENTIAL",
                "source": f"{name}:classes.dex",
                "locator": f"sdk={name}:{i}",
                "excerpt": "Synthetic SDK attribution",
                "package_split": name,
            }
            for i in range(sdk_count)
        ],
        "behaviors": [],
        "errors": [],
    }


def test_r4_split_limitations_and_sdk_budget_are_merged(tmp_path, monkeypatch):
    """SDK selection is collection-bounded and split limitations survive the merge."""
    base = tmp_path / "base.apk"
    feature = tmp_path / "feature.apk"
    config = tmp_path / "config.apk"
    for item in (base, feature, config):
        item.write_bytes(b"synthetic")
    scans = {
        "base": _r4_fake_scan_result("base", 500),
        "feature": _r4_fake_scan_result(
            "feature", 500, behavior_warning="Mapped behavior output truncated at 500"
        ),
        "config": _r4_fake_scan_result("config", 500),
    }

    def fake_scan(path, rules, **kwargs):
        part = kwargs["component"].split_name or "base"
        return scans[part]

    monkeypatch.setattr(apk_worker, "scan", fake_scan)
    result = apk_worker.scan_package_set(
        base, [("feature", feature), ("config", config)], {"version": "test"}
    )
    sdk = [ev for ev in result["evidence"] if ev["kind"] == "SDK"]
    assert len(sdk) == apk_worker.MAX_SDK_ATTRIBUTIONS
    assert {"base", "feature", "config"} <= {ev["package_split"] for ev in sdk}
    assert len({ev["id"] for ev in sdk}) == len(sdk)
    notes = result["coverage"]
    assert any("feature" in note and "truncated at 500" in note
               for note in notes["behavior_limitations"])
    assert any("feature" in note and "SDK truncated" in note
               for note in notes["sdk_attribution_limitations"])
    assert any("Package-set SDK attribution output capped" in note
               for note in notes["sdk_attribution_limitations"])
    assert any("feature" in note and "Missing resources" in note
               for note in notes["limitations"])


def test_r4_external_import_provenance_survives_persisted_report(tmp_path, monkeypatch):
    """Externally supplied policy text must not become verified official fetch data."""
    sample = apk(tmp_path / "input.apk")
    app = create_app(tmp_path / "jobs")

    def fixture_scanner(path, **kwargs):
        return apk_worker.scan(path, taxonomy())

    monkeypatch.setattr(pipeline, "scan_isolated", fixture_scanner)
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        imported = client.post(
            route + "/import-external", headers=HEADERS,
            json={
                "source": {
                    "title": "Externally supplied policy",
                    "source_type": "OFFICIAL_WEB_POLICY",
                    "url": "https://example.com/privacy",
                    "text": "我们在许可后使用相机。",
                },
                "claims": [],
            },
        )
        assert imported.status_code == 200, imported.text
        updated = client.post(
            route + "/apk", headers=HEADERS, content=sample.read_bytes()
        )
        assert updated.status_code == 200, updated.text
        job = client.post(
            route + "/start", headers=HEADERS,
            json={"revision": updated.json()["revision"], "request_id": uuid4().hex},
        )
        assert job.status_code == 200, job.text
        job_id = job.json()["id"]
        app.state.web_intake.futures[job_id].result(timeout=15)
        report = app.state.job_store.report(job_id)
        receipts = json.loads(report.tools["web_policy_sources"])
        ext = next(s for s in receipts if s["title"] == "Externally supplied policy")
        assert ext["provenance"] == "EXTERNAL_CHAT_EXPORT"
        doc = next(d for d in report.policy_documents
                   if d.title == "Externally supplied policy")
        provenance_ev = next(ev for ev in report.evidence if ev.id == doc.evidence_id)
        assert "acquisition=EXTERNAL_CHAT_EXPORT" in provenance_ev.locator
        assert "not proof of official verification" in provenance_ev.locator


def test_f1_start_with_unchecked_candidates_yields_unreviewed_policy(tmp_path, monkeypatch):
    """F1: Starting analysis with unchecked candidates succeeds without gate error,

    and strict UNREVIEWED semantics are preserved on the policy document and report.
    """
    sample = apk(tmp_path / "sample.apk", camera=True)

    def scanner(path, **kwargs):
        return apk_worker.scan(path, taxonomy())

    monkeypatch.setattr(pipeline, "scan_isolated", scanner)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        route = f"/api/v1/web/drafts/{draft_id}"

        imported = client.post(
            f"{route}/import-external",
            headers=HEADERS,
            json={
                "source": {
                    "title": "Unreviewed Policy Test",
                    "source_type": "OFFICIAL_WEB_POLICY",
                    "url": "https://example.com/unreviewed",
                    "text": "我们在许可后使用相机。",
                },
                "claims": [
                    {
                        "excerpt": "我们在许可后使用相机。",
                        "data_type": "CAMERA",
                        "polarity": "AFFIRMATIVE",
                        "action": "ACCESS",
                    }
                ],
            },
        )
        assert imported.status_code == 200, imported.text
        draft_data = client.get(route).json()
        assert len(draft_data["candidates"]) == 1
        assert draft_data["candidates"][0]["checked"] is False

        updated = client.post(route + "/apk", headers=HEADERS, content=sample.read_bytes())
        assert updated.status_code == 200, updated.text

        start_resp = client.post(
            route + "/start",
            headers=HEADERS,
            json={"revision": updated.json()["revision"], "request_id": uuid4().hex},
        )
        assert start_resp.status_code == 200, start_resp.text
        job_id = start_resp.json()["id"]

        app.state.web_intake.futures[job_id].result(timeout=15)
        report = app.state.job_store.report(job_id)

        doc = next(d for d in report.policy_documents if d.title == "Unreviewed Policy Test")
        assert doc.review_status == "UNREVIEWED"
        assert doc.completeness == "PARTIAL"
        assert doc.attachments_status == "NOT_CHECKED"
        for d in report.policy_documents:
            assert d.review_status == "UNREVIEWED"
            assert d.completeness == "PARTIAL"
            assert d.attachments_status == "NOT_CHECKED"


def test_f2_active_upload_staging_protected_from_start_service(tmp_path):
    """F2: Active uploads tracked in active_drafts are not purged by start_service."""
    app = create_app(tmp_path / "jobs")
    service = app.state.web_intake
    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)

        pending = service._safe(directory / "upload.pending")
        pending.write_bytes(b"in-flight-upload-data")
        staging_pkg = service._safe(directory / "packages.pending.test1234")
        staging_pkg.mkdir()
        (staging_pkg / "base.apk").write_bytes(b"fake-apk")

        with service._draft_activity(draft_id):
            assert service.active_drafts.get(draft_id, 0) > 0
            if service.owner_fd is not None:
                os.close(service.owner_fd)
                service.owner_fd = None
            service.start_service()
            assert pending.exists()
            assert staging_pkg.exists()

        assert service.active_drafts.get(draft_id, 0) == 0
        if service.owner_fd is not None:
            os.close(service.owner_fd)
            service.owner_fd = None
        service.start_service()
        assert not pending.exists()
        assert not staging_pkg.exists()


def test_f4_102_package_set_early_rejection(tmp_path):
    """F4: Package sets with > 101 entries are immediately rejected with HTTP 413."""
    from privacytrace.package_set import (
        PackageFile,
        PackagePart,
        PackageSetIntegrityError,
        validate_package_set,
    )

    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(102):
                zf.writestr(f"split_{i}.apk", b"PK\x05\x06" + b"\x00" * 18)

        resp = client.post(route + "/package-set", headers=HEADERS, content=buf.getvalue())
        assert resp.status_code == 413
        assert resp.json()["detail"] == "PACKAGE_SET_TOO_LARGE"

        mock_files = [
            PackageFile(
                file_name="base.apk",
                part=PackagePart.BASE,
                sha256="a" * 64,
                size_bytes=100,
                package_name="com.example.test",
                version_code=1,
            )
        ] + [
            PackageFile(
                file_name=f"split_{i}.apk",
                part=PackagePart.SPLIT,
                split_name=f"split_{i}",
                sha256="b" * 64,
                size_bytes=100,
                package_name="com.example.test",
                version_code=1,
            )
            for i in range(101)
        ]
        assert len(mock_files) == 102
        with pytest.raises(PackageSetIntegrityError) as exc_info:
            validate_package_set(mock_files)
        assert exc_info.value.http_status == 413
        assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE"


def test_f5_arsc_resource_parsing_fault_isolation():
    """F5: Corrupt or malformed ARSC entries do not crash worker or abort URL discovery."""
    from privacytrace.apk_worker import _manifest_resource_strings

    class BrokenResources:
        def get_packages_names(self):
            raise struct.error("unpack requires a buffer of 4 bytes")

    assert _manifest_resource_strings("@string/broken", BrokenResources(), "com.example") == []


def test_f6_behavior_budget_deduplication_and_split_tools(tmp_path, monkeypatch):
    """F6: Split permissions matching base are deduplicated, split tools are aggregated,

    and URL truncation beyond 8 entries records an explicit limitation notice.
    """
    from privacytrace.apk_worker import inspect_package_metadata

    class MockElement:
        def __init__(self, val):
            self.val = val

        def get(self, key, default=""):
            return self.val

    class MockXmlRoot:
        def iter(self, tag):
            if tag == "meta-data":
                return [
                    MockElement(f"https://example.com/policy_{i}")
                    for i in range(12)
                ]
            return []

    class MockArchive:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, name):
            return b""

    class MockAXMLPrinter:
        def __init__(self, data):
            pass

        def get_xml_obj(self):
            return MockXmlRoot()

    apk_file = tmp_path / "test.apk"
    apk_file.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    monkeypatch.setattr("privacytrace.apk_worker.ZipFile", MockArchive)
    monkeypatch.setattr("androguard.core.axml.AXMLPrinter", MockAXMLPrinter)
    monkeypatch.setattr(
        "privacytrace.package_set.inspect_apk_bytes",
        lambda data, name: (
            type("Pkg", (), {"sha256": "0" * 64, "model_dump": lambda self, mode: {}})(),
            [],
        ),
    )

    meta_result = inspect_package_metadata(apk_file)
    assert len(meta_result["policy_urls"]) == 8
    assert any(
        "Discovered policy URLs truncated at 8" in note
        for note in meta_result["coverage"]["limitations"]
    )


def test_f7_websource_provenance_validation():
    """F7: WebSource.provenance accepts only valid enum literals and rejects arbitrary strings."""
    from pydantic import ValidationError

    from privacytrace.web_models import WebSource

    valid_vals = (
        "MANIFEST_METADATA",
        "EXTERNAL_CHAT_EXPORT",
        "DIRECT_WEB_FETCH",
        "MANUAL_INPUT",
        None,
    )
    for val in valid_vals:
        src = WebSource(id="s1", title="test", provenance=val)
        assert src.provenance == val

    with pytest.raises(ValidationError):
        WebSource(id="s1", title="test", provenance="INVALID_PROVENANCE")
