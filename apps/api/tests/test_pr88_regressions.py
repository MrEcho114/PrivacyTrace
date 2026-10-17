"""PR88 regression guards; fixture doubles and real Docker evidence are separate."""

import json
import os
import threading
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

    def unavailable(path):
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

    def metadata(path):
        entered.set()
        assert release.wait(5)
        return {"policy_urls": ["https://example.com/stale"]}

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as executor:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        assert client.post(route + "/apk", headers=HEADERS, content=b"fixture").status_code == 200
        service = app.state.web_intake
        pending = executor.submit(service.discover_sources, draft["id"])
        try:
            assert entered.wait(3)
            # Independent readers/writers can finish while the worker is blocked.
            current = executor.submit(service.get, draft["id"]).result(timeout=1)
            assert current["uploaded"]
            changed = client.post(
                route + "/import-external", headers=HEADERS, json={"source": {"text": "补充政策"}}
            )
            assert changed.status_code == 200
        finally:
            release.set()
        with pytest.raises(ValueError, match="Input changed"):
            pending.result(timeout=3)
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
                "source": {"text": text},
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
