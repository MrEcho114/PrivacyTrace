"""R10: prevent client origin spoofing and silently incomplete package sets.

All APKs are constructed binary fixtures. Real Docker seams are opt-in.
"""

import hashlib
import json
import os
from uuid import uuid4

import pytest
from apk_fixture_builder import apk, apk_bytes, package_set_archive
from fastapi.testclient import TestClient
from policy_discovery_fixture import policy_resource_apk
from test_pr88_intake_limits import scan_fixture_set
from test_web_intake import HEADERS, new_draft

from privacytrace import apk_worker, pipeline, web_intake
from privacytrace.isolated_scan import ScanError, scan_isolated
from privacytrace.main import create_app
from privacytrace.package_set import PackageSetIntegrityError, parse_package_input
from privacytrace.policy_fetch import FetchError
from privacytrace.resources import taxonomy


def finish_report(client, app, route, draft):
    response = client.post(route + "/start", headers=HEADERS, json={
        "revision": draft["revision"], "request_id": uuid4().hex,
    })
    assert response.status_code == 200, response.text
    job_id = response.json()["id"]
    app.state.web_intake.futures[job_id].result(timeout=60)
    assert app.state.job_store.get(job_id).state == "SUCCEEDED"
    return app.state.job_store.report(job_id)


@pytest.mark.parametrize("provenance", [
    "MANIFEST_METADATA", "EXTERNAL_CHAT_EXPORT", "DIRECT_WEB_FETCH", "MANUAL_INPUT",
])
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("client_status", ["ready", "manual", "empty", "failed", "url_only"])
def test_client_origin_never_becomes_report_acquisition(
    tmp_path, monkeypatch, provenance, legacy, client_status,
):
    monkeypatch.setattr(
        pipeline, "scan_isolated", lambda path, **kw: apk_worker.scan(path, taxonomy()),
    )
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        response = client.post("/api/v1/web/drafts", headers=HEADERS, json={
            "name": "Origin fixture", "sources": [{
                "id": "manual", "title": "Policy", "text": "Manually supplied policy text.",
                "status": client_status, "provenance": provenance,
            }],
        })
        assert response.status_code == 200, response.text
        draft = response.json()
        route = f"/api/v1/web/drafts/{draft['id']}"
        if legacy:
            # Simulate an older stored draft with the previously accepted label.
            current = app.state.web_intake.directory(draft["id"]) / "current.json"
            stored = json.loads(current.read_text())
            stored["sources"][0]["provenance"] = provenance
            current.write_text(json.dumps(stored), encoding="utf-8")
        assert client.get(route).json()["sources"][0]["provenance"] == "MANUAL_INPUT"
        uploaded = client.post(route + "/apk", headers=HEADERS, content=apk_bytes()).json()
        report = finish_report(client, app, route, uploaded)
        assert json.loads(report.tools["web_policy_sources"])[0]["provenance"] == "MANUAL_INPUT"
        doc = report.policy_documents[0]
        evidence = next(ev for ev in report.evidence if ev.id == doc.evidence_id)
        assert "acquisition=MANUAL_INPUT;" in evidence.locator
        assert "discovery=" not in evidence.locator
        assert doc.review_status == "UNREVIEWED"


@pytest.mark.usefixtures("synthetic_package_metadata")
def test_discovered_url_and_fetched_text_keep_distinct_origins(tmp_path, monkeypatch):
    policy = "https://example.com/privacy"
    sample = policy_resource_apk(tmp_path / "policy.apk", values={"policy": policy})
    text = "Fetched policy text."
    monkeypatch.setattr(web_intake, "fetch_policy", lambda url: {
        "text": text, "status": "ready", "final_url": url, "error_code": None,
        "captured_at": "2026-10-18T00:00:00Z", "sha256": hashlib.sha256(text.encode()).hexdigest(),
    })
    monkeypatch.setattr(
        pipeline, "scan_isolated", lambda path, **kw: apk_worker.scan(path, taxonomy()),
    )
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(route + "/apk", headers=HEADERS, content=sample.read_bytes())
        assert uploaded.status_code == 200, uploaded.text
        discovery = client.post(route + "/sources/discover", headers=HEADERS)
        source = next(s for s in discovery.json()["sources"] if s["url"] == policy)
        fetched = client.post(route + f"/sources/{source['id']}/fetch", headers=HEADERS,
                              json={"revision": client.get(route).json()["revision"]})
        assert fetched.status_code == 200, fetched.text
        report = finish_report(client, app, route, fetched.json())
        receipt = next(s for s in json.loads(report.tools["web_policy_sources"])
                       if s["id"] == source["id"])
        assert receipt["provenance"] == "MANIFEST_METADATA"
        doc = next(d for d in report.policy_documents if d.id == "web-" + source["id"])
        locator = next(ev.locator for ev in report.evidence if ev.id == doc.evidence_id)
        assert "acquisition=DIRECT_WEB_FETCH;" in locator
        assert "discovery=MANIFEST_METADATA;" in locator
        assert doc.review_status == "UNREVIEWED"


@pytest.mark.usefixtures("synthetic_package_metadata")
def test_discovered_sources_inherit_uploaded_package_identity(tmp_path):
    """A URL found in the app manifest is scoped to the uploaded package, not left unknown."""
    policy = "https://example.com/privacy"
    sample = policy_resource_apk(tmp_path / "policy.apk", values={"policy": policy})
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(route + "/apk", headers=HEADERS, content=sample.read_bytes())
        assert uploaded.status_code == 200, uploaded.text
        discovery = client.post(route + "/sources/discover", headers=HEADERS)
        assert discovery.status_code == 200, discovery.text
        source = next(s for s in discovery.json()["sources"] if s["url"] == policy)
        assert source["package_name"] == "org.privacytrace.fixture"
        assert source["version_code"] == 7


@pytest.mark.usefixtures("synthetic_package_metadata")
def test_discovered_sources_inherit_registered_package_set_identity(tmp_path):
    """A package-set draft keeps its registered identity while discovery inspects real fixtures."""
    policy = "https://example.com/privacy"
    base = policy_resource_apk(tmp_path / "base.apk", values={"policy": policy})
    split = policy_resource_apk(
        tmp_path / "feature.apk", values={"policy": policy}, split="feature",
    )
    archive = package_set_archive(apks={
        base.name: base.read_bytes(), split.name: split.read_bytes(),
    })
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(route + "/package-set", headers=HEADERS, content=archive)
        assert uploaded.status_code == 200, uploaded.text
        discovery = client.post(route + "/sources/discover", headers=HEADERS)
        assert discovery.status_code == 200, discovery.text
        source = next(s for s in discovery.json()["sources"] if s["url"] == policy)
        assert source["package_name"] == "org.privacytrace.fixture"
        assert source["version_code"] == 7


def test_isolated_dependency_error_is_rejected_as_input(tmp_path, monkeypatch):
    """The isolated worker's malformed-dependency code is a 4xx input rejection, not a 503."""
    def metadata(path, **kwargs):
        raise ScanError("INVALID_SPLIT_DEPENDENCY", "Synthetic isolated rejection")

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(route + "/package-set", headers=HEADERS, content=apk_bytes())
        assert response.status_code == 400
        assert response.json()["detail"] == "INVALID_SPLIT_DEPENDENCY"
        current = client.get(route).json()
        assert not current["uploaded"] and current["revision"] == draft["revision"]
        directory = app.state.web_intake.directory(draft["id"])
        assert not list(directory.glob("*pending*"))
        assert not (directory / "packages").exists() and not (directory / "input.apk").exists()


def test_discovery_maps_transport_input_error_to_rejection(tmp_path, monkeypatch):
    """The single-APK discovery lane keeps a worker's input code at 4xx, not 503."""
    def metadata(path, **kwargs):
        raise ScanError("INVALID_SPLIT_DEPENDENCY", "Synthetic isolated rejection")

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(route + "/apk", headers=HEADERS, content=apk_bytes())
        assert uploaded.status_code == 200, uploaded.text
        response = client.post(route + "/sources/discover", headers=HEADERS)
        assert response.status_code == 400
        assert response.json()["detail"] == "INVALID_SPLIT_DEPENDENCY"
        assert client.get(route).json()["revision"] == uploaded.json()["revision"]


@pytest.mark.usefixtures("synthetic_package_metadata")
def test_discovery_maps_in_process_input_error_to_rejection(tmp_path):
    """The in-process fixture parser keeps the same 4xx classification as the worker."""
    sample = apk(tmp_path / "bad.apk", manifest_options={
        "split": "feature", "is_feature_split": True, "uses_split": "bad name",
    })
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(route + "/apk", headers=HEADERS, content=sample.read_bytes())
        assert uploaded.status_code == 200, uploaded.text
        response = client.post(route + "/sources/discover", headers=HEADERS)
        assert response.status_code == 400
        assert response.json()["detail"] == "INVALID_SPLIT_DEPENDENCY"


@pytest.mark.parametrize("outcome", ["failure", "success", "success_then_failure"])
def test_imported_material_survives_fetch_attempts(tmp_path, monkeypatch, outcome):
    supplied = "We access the camera with permission."
    fetched_text = "A newly fetched policy."

    def fetched(url):
        return {
            "text": fetched_text, "status": "ready", "error_code": None, "final_url": url,
            "captured_at": "2026-10-18T00:00:00Z",
            "sha256": hashlib.sha256(fetched_text.encode()).hexdigest(),
        }

    def unavailable(url):
        raise FetchError("FETCH_TIMEOUT")

    monkeypatch.setattr(
        pipeline, "scan_isolated", lambda path, **kw: apk_worker.scan(path, taxonomy()),
    )
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        imported = client.post(route + "/import-external", headers=HEADERS, json={
            "source": {"id": "material", "title": "External policy", "text": supplied,
                       "url": "https://example.com/privacy", "source_type": "OFFICIAL_WEB_POLICY"},
            "claims": [{"excerpt": supplied, "data_type": "CAMERA"}],
        })
        assert imported.status_code == 200, imported.text
        draft = imported.json()
        audit = draft["external_imports"]
        for succeeds in ([False] if outcome == "failure" else
                         [True] if outcome == "success" else [True, False]):
            before = next(s for s in draft["sources"] if s["id"] == "material")
            previous_candidates = draft["candidates"]
            monkeypatch.setattr(web_intake, "fetch_policy", fetched if succeeds else unavailable)
            response = client.post(route + "/sources/material/fetch", headers=HEADERS,
                                   json={"revision": draft["revision"]})
            assert response.status_code == 200, response.text
            draft = response.json()
            source = next(s for s in draft["sources"] if s["id"] == "material")
            assert source["provenance"] == "EXTERNAL_CHAT_EXPORT"
            if not succeeds:
                assert source == {**before, "error_code": "FETCH_TIMEOUT"}
                assert draft["candidates"] == previous_candidates
            else:
                assert source["text"] == fetched_text and not draft["candidates"]
            assert draft["external_imports"] == audit
        uploaded = client.post(route + "/apk", headers=HEADERS, content=apk_bytes()).json()
        report = finish_report(client, app, route, uploaded)
        doc = next(d for d in report.policy_documents if d.id == "web-material")
        assert doc.artifact.text == (supplied if outcome == "failure" else fetched_text)
        locator = next(ev.locator for ev in report.evidence if ev.id == doc.evidence_id)
        acquisition = "EXTERNAL_CHAT_EXPORT" if outcome == "failure" else "DIRECT_WEB_FETCH"
        assert f"acquisition={acquisition};" in locator
        assert doc.review_status == "UNREVIEWED"


def package_archive(*components):
    return package_set_archive(apks={
        f"{index}.apk": apk_bytes(manifest_options=options)
        for index, options in enumerate(components)
    })


@pytest.mark.parametrize("components,code", [
    ([{}, {"split": "a", "is_feature_split": True, "uses_split": "b"}], "MISSING_REQUIRED_SPLIT"),
    ([{}, {"split": "a", "is_feature_split": True, "uses_split": "a"}], "INVALID_SPLIT_DEPENDENCY"),
    ([{}, {"split": "a", "is_feature_split": True, "uses_split": "b"},
      {"split": "b", "is_feature_split": True, "uses_split": "a"}], "INVALID_SPLIT_DEPENDENCY"),
    ([{}, {"split": "config.en", "config_for_split": "feature"}], "MISSING_REQUIRED_SPLIT"),
    ([{}, {"split": "config.en", "config_for_split": "config.fr"},
      {"split": "config.fr"}], "INVALID_SPLIT_DEPENDENCY"),
    ([{"is_split_required": True}], "MISSING_REQUIRED_SPLIT"),
    ([{"required_split_types": "base__abi, base__density"},
      {"split": "config.arm", "split_types": "base__abi"}], "MISSING_REQUIRED_SPLIT"),
    ([{}, {"split": "feature", "is_feature_split": True,
           "required_split_types": "feature__lang"}], "MISSING_REQUIRED_SPLIT"),
])
def test_declared_split_dependencies_cannot_be_silently_dropped(components, code):
    with pytest.raises(PackageSetIntegrityError) as caught:
        parse_package_input(package_archive(*components))
    assert caught.value.code == code


@pytest.mark.parametrize("components", [
    [{}],
    [{}, {"split": "config.en"}],
    [{}, {"split": "a", "is_feature_split": True, "uses_split": "b"}, {"split": "b"}],
    [{}, {"split": "feature", "is_feature_split": True},
     {"split": "config.en", "config_for_split": "feature"}],
    [{"is_split_required": True, "required_split_types": "base__abi, base__density"},
     {"split": "config.arm", "split_types": "base__abi, base__abi"},
     {"split": "config.dpi", "split_types": "base__density"}],
    [{}, {"split": "feature", "is_feature_split": True, "required_split_types": "feature__lang"},
     {"split": "config.en", "config_for_split": "feature", "split_types": "feature__lang"}],
])
def test_satisfied_dependencies_and_ordinary_apks_remain_valid(components):
    parsed, _ = parse_package_input(package_archive(*components))
    assert len(parsed.all_files) == len(components)


@pytest.mark.parametrize("declarations", [
    {"is_split_required": True}, {"required_split_types": "base__abi"},
])
def test_single_base_lane_does_not_bypass_required_splits(tmp_path, declarations):
    sample = apk(tmp_path / "base.apk", manifest_options=declarations)
    with pytest.raises(PackageSetIntegrityError) as caught:
        apk_worker.scan(sample, taxonomy())
    assert caught.value.code == "MISSING_REQUIRED_SPLIT"


@pytest.mark.parametrize("name", [None, ""])
def test_direct_scanner_missing_split_name_keeps_separate_namespace(tmp_path, name):
    base = apk(tmp_path / "base.apk")
    split = apk(tmp_path / "feature.apk", split="feature")
    scanned = apk_worker.scan_package_set(base, [(name, split)], taxonomy())
    assert scanned["dex_entries"] == ["base:classes.dex", "split:unknown:classes.dex"]


def exercise_dependency_retry(tmp_path, monkeypatch, real_worker):
    if not real_worker:
        monkeypatch.setattr(web_intake, "inspect_package_isolated",
                            lambda path, **kw: apk_worker.inspect_package_metadata(path))
        monkeypatch.setattr(pipeline, "scan_isolated", scan_fixture_set)
    base = apk(tmp_path / "base.apk")
    feature_a = apk(tmp_path / "a.apk", manifest_options={
        "split": "a", "is_feature_split": True, "uses_split": "b",
    })
    feature_b = apk(tmp_path / "b.apk", manifest_options={"split": "b", "is_feature_split": True})
    payload = {p.name: p.read_bytes() for p in (base, feature_a)}
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(route + "/package-set", headers=HEADERS,
                               content=package_set_archive(apks=payload))
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "MISSING_REQUIRED_SPLIT"
        current = client.get(route).json()
        assert not current["uploaded"] and current["revision"] == draft["revision"]
        directory = app.state.web_intake.directory(draft["id"])
        assert not list(directory.glob("*pending*"))
        assert not (directory / "packages").exists() and not (directory / "input.apk").exists()
        payload[feature_b.name] = feature_b.read_bytes()
        response = client.post(route + "/package-set", headers=HEADERS,
                               content=package_set_archive(apks=payload))
        assert response.status_code == 200, response.text
        report = finish_report(client, app, route, response.json())
        assert {"base:classes.dex", "split:a:classes.dex", "split:b:classes.dex"} <= set(
            report.sample.dex_entries
        )


def test_http_missing_dependency_rolls_back_and_allows_complete_retry(tmp_path, monkeypatch):
    exercise_dependency_retry(tmp_path, monkeypatch, real_worker=False)


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam")
def test_real_worker_malformed_dependency_is_a_client_error(tmp_path):
    """The real isolated worker serialises a malformed dependency as a 4xx input rejection."""
    base = apk(tmp_path / "base.apk")
    broken = apk(tmp_path / "feature.apk", manifest_options={
        "split": "feature", "is_feature_split": True, "uses_split": "bad name",
    })
    archive = package_set_archive(apks={
        base.name: base.read_bytes(), broken.name: broken.read_bytes(),
    })
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(route + "/package-set", headers=HEADERS, content=archive)
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "INVALID_SPLIT_DEPENDENCY"
        assert not client.get(route).json()["uploaded"]


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam")
def test_real_worker_discovery_malformed_dependency_is_a_client_error(tmp_path):
    """The real worker also keeps a malformed dependency on the discovery lane at 4xx."""
    broken = apk(tmp_path / "bad.apk", manifest_options={
        "split": "feature", "is_feature_split": True, "uses_split": "bad name",
    })
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(route + "/apk", headers=HEADERS, content=broken.read_bytes())
        assert uploaded.status_code == 200, uploaded.text
        response = client.post(route + "/sources/discover", headers=HEADERS)
        assert response.status_code == 400, response.text
        assert response.json()["detail"] == "INVALID_SPLIT_DEPENDENCY"


@pytest.mark.parametrize("tampered", [False, True])
def test_registered_package_set_identity_is_bound_before_report(tmp_path, monkeypatch, tampered):
    """A registered package set that no longer matches the scanned bytes cannot publish."""
    base = apk(tmp_path / "base.apk")
    split = apk(tmp_path / "feature.apk", split=True, split_name="feature")
    archive = package_set_archive(apks={
        base.name: base.read_bytes(), split.name: split.read_bytes(),
    })
    monkeypatch.setattr(pipeline, "scan_isolated", scan_fixture_set)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(route + "/package-set", headers=HEADERS, content=archive)
        assert uploaded.status_code == 200, uploaded.text
        if tampered:
            current = app.state.web_intake.directory(draft["id"]) / "current.json"
            stored = json.loads(current.read_text(encoding="utf-8"))
            stored["package_set"]["splits"][0]["sha256"] = "0" * 64
            current.write_text(json.dumps(stored), encoding="utf-8")
        started = client.post(route + "/start", headers=HEADERS, json={
            "revision": uploaded.json()["revision"], "request_id": uuid4().hex,
        })
        assert started.status_code == 200, started.text
        job_id = started.json()["id"]
        app.state.web_intake.futures[job_id].result(timeout=60)
        job = app.state.job_store.get(job_id)
        assert job.state == ("FAILED" if tampered else "SUCCEEDED")
        if tampered:
            assert json.loads(job.error)["code"] == "INPUT_DIGEST_MISMATCH"


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam")
def test_real_worker_dependency_metadata_rejection_and_retry(tmp_path, monkeypatch):
    exercise_dependency_retry(tmp_path, monkeypatch, real_worker=True)


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam")
def test_real_worker_rejects_dependencies_without_intake_preflight(tmp_path):
    """Directory scans and the legacy asynchronous APK lane must keep the error code."""
    packages = tmp_path / "packages"
    packages.mkdir()
    base = apk(packages / "base.apk", manifest_options={"is_split_required": True})
    with pytest.raises(ScanError) as caught:
        scan_isolated(packages)
    assert caught.value.code == "MISSING_REQUIRED_SPLIT"
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        upload = client.post(route + "/apk", headers=HEADERS, content=base.read_bytes())
        assert upload.status_code == 200, upload.text  # Existing asynchronous validation boundary.
        started = client.post(route + "/start", headers=HEADERS, json={
            "revision": upload.json()["revision"], "request_id": uuid4().hex,
        })
        assert started.status_code == 200, started.text
        job_id = started.json()["id"]
        app.state.web_intake.futures[job_id].result(timeout=60)
        job = app.state.job_store.get(job_id)
        assert job.state == "FAILED"
        assert json.loads(job.error)["code"] == "MISSING_REQUIRED_SPLIT"
