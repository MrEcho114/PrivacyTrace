"""HTTP intake invariants; model/scanner doubles are reported separately from live proof."""

import json
import threading
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from privacytrace import pipeline, policy_fetch
from privacytrace.main import create_app
from privacytrace.models import AnalysisJob
from privacytrace.resources import taxonomy
from privacytrace.web_models import DraftInput

HEADERS = {"X-PrivacyTrace-Local": "1"}


def new_draft(client):
    response = client.post(
        "/api/v1/web/drafts",
        headers=HEADERS,
        json={
            "name": "Controlled bytes on ordinary web lane",
            "sources": [
                {
                    "id": "a",
                    "title": "Host policy",
                    "text": "我们不会读取联系人。",
                    "status": "manual",
                },
                {
                    "id": "b",
                    "title": "Unavailable policy",
                    "url": "http://127.0.0.1/",
                    "status": "empty",
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def candidates(draft, checked=True, excerpt="我们不会读取联系人。"):
    return {
        "revision": draft["revision"],
        "candidates": [
            {
                "id": "quote1",
                "source_id": "a",
                "excerpt": excerpt,
                "data_type": "CONTACTS",
                "polarity": "NEGATIVE",
                "subject": "HOST_APP",
                "checked": checked,
            }
        ],
    }


def test_local_write_auth_secret_redaction_and_body_limits(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/v1/web/drafts", json={}).status_code == 403
    assert (
        client.post(
            "/api/v1/web/settings", headers={**HEADERS, "Origin": "https://evil.org"}, json={}
        ).status_code
        == 403
    )
    secret = "PRIVATE_MODEL_CREDENTIAL"
    response = client.post(
        "/api/v1/web/settings", headers=HEADERS, json={"api_key": secret, "enabled": "malformed"}
    )
    assert response.status_code == 422 and secret not in response.text
    response = client.post(
        "/api/v1/web/settings",
        headers=HEADERS,
        json={
            "enabled": True,
            "api_base": "https://model.example/v1",
            "model": "test",
            "api_key": secret,
        },
    )
    assert response.status_code == 200 and secret not in response.text
    assert response.json()["key_configured"] is True
    assert secret not in client.get("/api/v1/web/settings").text
    assert (
        client.post(
            "/api/v1/web/drafts", headers=HEADERS, content=b" " * (8 * 1024 * 1024 + 1)
        ).status_code
        == 413
    )


def test_quote_scope_and_revision_are_validated_before_scanning(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    assert (
        client.post(
            endpoint + "/candidates", headers=HEADERS, json=candidates(draft, excerpt="不是原句")
        ).status_code
        == 409
    )
    payload = candidates(draft)
    payload["candidates"][0]["source_id"] = "missing"
    assert client.post(endpoint + "/candidates", headers=HEADERS, json=payload).status_code == 409
    response = client.post(
        endpoint + "/candidates", headers=HEADERS, json=candidates(draft, checked=False)
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["revision"] == 2
    assert (
        client.post(endpoint + "/candidates", headers=HEADERS, json=candidates(draft)).status_code
        == 409
    )
    captures = app.state.web_intake.captures(updated, require_checked=False)
    doc = captures[0]["document"]
    assert (doc.completeness, doc.review_status, doc.attachments_status) == (
        "PARTIAL",
        "UNREVIEWED",
        "NOT_CHECKED",
    )
    assert captures[0]["claims"][0].polarity == "NEGATIVE"
    original = json.loads((tmp_path / "web" / draft["id"] / "revision-1.json").read_bytes())
    assert original["candidates"] == []
    assert (
        client.post(
            endpoint + "/start", headers=HEADERS, json={"revision": 2, "request_id": uuid4().hex}
        ).status_code
        == 409
    )


def test_failed_source_retained_and_manual_fallback(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    response = client.post(endpoint + "/sources/b/fetch", headers=HEADERS, json={"revision": 1})
    assert response.status_code == 200
    draft = response.json()
    assert draft["sources"][1]["status"] == "failed"
    assert draft["sources"][1]["error_code"] == "PUBLIC_URL_REQUIRED"
    assert draft["sources"][0]["text"] == "我们不会读取联系人。"
    assert (
        client.post(endpoint + "/sources/a/extract", headers=HEADERS, json={"revision": 2}).json()[
            "detail"
        ]
        == "MODEL_NOT_CONFIGURED"
    )


def test_stream_upload_duplicate_start_cancel_retry_and_refresh(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def scan(apk, cancelled, **kwargs):
        from privacytrace.scan_workspace import ScanError

        calls.append(apk.read_bytes())
        entered.set()
        assert release.wait(5)
        if cancelled():
            raise ScanError("CANCELLED", "cancelled")
        raise ScanError("ISOLATION_UNAVAILABLE", "test boundary failure")

    monkeypatch.setattr(pipeline, "scan_isolated", scan)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        draft = new_draft(client)
        endpoint = f"/api/v1/web/drafts/{draft['id']}"
        assert client.post(endpoint + "/apk", headers=HEADERS, content=b"").status_code == 409
        upload = client.post(endpoint + "/apk", headers=HEADERS, content=b"bounded test bytes")
        assert upload.status_code == 200
        draft = upload.json()
        assert (
            client.post(endpoint + "/apk", headers=HEADERS, content=b"second file").status_code
            == 409
        )
        saved = client.post(endpoint + "/candidates", headers=HEADERS, json=candidates(draft))
        assert saved.status_code == 200
        draft = saved.json()
        payload = {"revision": draft["revision"], "request_id": uuid4().hex}
        response = client.post(endpoint + "/start", headers=HEADERS, json=payload)
        assert response.status_code == 200, response.text
        job = response.json()
        assert entered.wait(3)
        duplicate = client.post(endpoint + "/start", headers=HEADERS, json=payload)
        assert duplicate.json()["id"] == job["id"] and len(calls) == 1
        assert (
            client.post(
                endpoint + "/start", headers=HEADERS, json={**payload, "request_id": uuid4().hex}
            ).status_code
            == 409
        )
        assert (
            client.post(
                endpoint + "/candidates", headers=HEADERS, json=candidates(draft)
            ).status_code
            == 409
        )
        assert client.post(f"/api/v1/jobs/{job['id']}/cancel", headers=HEADERS).status_code == 200
        release.set()
        app.state.web_intake.futures[job["id"]].result(timeout=5)
        assert client.get(f"/api/v1/jobs/{job['id']}").json()["state"] == "CANCELLED"
        refreshed = client.get(endpoint).json()
        assert refreshed["jobs"][0]["job_id"] == job["id"]
        assert refreshed["jobs"][0]["events"][-1]["state"] == "CANCELLED"
        retry = client.post(
            endpoint + "/start", headers=HEADERS, json={**payload, "request_id": uuid4().hex}
        )
        assert retry.status_code == 200 and retry.json()["id"] != job["id"]
        app.state.web_intake.futures[retry.json()["id"]].result(timeout=5)
        assert client.get(f"/api/v1/jobs/{retry.json()['id']}").json()["state"] == "FAILED"
        assert len(calls) == 2
    with TestClient(create_app(tmp_path)) as client:
        assert len(client.get(endpoint).json()["jobs"]) == 2


def test_service_restart_marks_only_owned_incomplete_jobs(tmp_path):
    app = create_app(tmp_path)
    draft = app.state.web_intake.create(
        DraftInput(name="stale", sources=[{"id": "a", "title": "policy", "text": "policy"}])
    )
    job = AnalysisJob(
        id=uuid4().hex,
        sample_id="stale",
        input_mode="APK",
        source_origin="REAL_SCAN",
        state="STATIC_ANALYSIS",
        ruleset_version=taxonomy()["version"],
        created_at=draft["created_at"],
    )
    other = job.model_copy(update={"id": "unrelated-cli"})
    app.state.job_store.create_if_absent(job)
    app.state.job_store.create_if_absent(other)
    draft["jobs"] = [{"job_id": job.id, "request_id": uuid4().hex, "revision": 1, "events": []}]
    from privacytrace.web_intake import write_private

    write_private(tmp_path / "web" / draft["id"] / "current.json", draft)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/v1/jobs/{job.id}").json()["state"] == "FAILED"
        assert "SERVICE_INTERRUPTED" in client.get(f"/api/v1/jobs/{job.id}").json()["error"]
        assert client.get("/api/v1/jobs/unrelated-cli").json()["state"] == "STATIC_ANALYSIS"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/",
        "https://user:secret@example.org/",
        "http://localhost:8000/",
    ],
)
def test_nonpublic_policy_targets_rejected(url):
    with pytest.raises(policy_fetch.FetchError):
        policy_fetch.public_target(url)


def test_mixed_public_private_dns_rejected(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443)),
        ],
    )
    with pytest.raises(policy_fetch.FetchError, match="PUBLIC_URL_REQUIRED"):
        policy_fetch.public_target("https://public.example/privacy")


def test_fake_ip_fallback_still_requires_global_dns(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.67", 443)),
        ],
    )
    monkeypatch.setattr(
        policy_fetch,
        "public_dns",
        lambda *a: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(policy_fetch.FetchError, match="PUBLIC_URL_REQUIRED"):
        policy_fetch.public_target("https://public.example/privacy")
