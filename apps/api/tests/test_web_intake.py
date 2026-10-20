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


def test_manual_url_uses_supplied_source_and_redacts_credentials(tmp_path):
    app = create_app(tmp_path)
    draft = app.state.web_intake.create(DraftInput(name="manual", sources=[{
        "id": "manual", "title": "Manual text", "text": "我们不会读取联系人。",
        "url": "https://user:PRIVATE@public.example/policy?key=SECRET",
        "final_url": "https://unfetched.example/fabricated",
        "captured_at": "2000-01-01T00:00:00Z", "sha256": "fabricated",
    }]))
    assert draft["sources"][0]["final_url"] is None
    assert draft["sources"][0]["sha256"] != "fabricated"
    evidence = app.state.web_intake.captures(draft)[0]["evidence"][0]
    assert evidence.source == "https://public.example/policy?key=REDACTED"


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


def test_new_endpoint_cannot_reuse_retained_model_credential(tmp_path):
    client = TestClient(create_app(tmp_path))
    original = {"enabled": True, "api_base": "https://model.example/v1",
                "model": "test", "api_key": "PRIVATE_CONFIGURED_KEY"}
    assert client.post("/api/v1/web/settings", headers=HEADERS, json=original).status_code == 200
    changed = {**original, "api_base": "https://another.example/v1"}
    del changed["api_key"]
    assert client.post("/api/v1/web/settings", headers=HEADERS, json=changed).status_code == 409
    changed["enabled"] = False
    response = client.post("/api/v1/web/settings", headers=HEADERS, json=changed)
    assert response.status_code == 200 and response.json()["key_configured"] is False
    assert "PRIVATE_CONFIGURED_KEY" not in response.text


def test_reextraction_retains_checked_candidates_within_quota(tmp_path, monkeypatch):
    from privacytrace import web_intake
    from privacytrace.policy_llm_extractor import MockLLMClient

    suggestions = [{"excerpt": "我们不会读取联系人。", "data_type": "CONTACTS"},
                   {"excerpt": "我们不会读取联系人。", "data_type": "LOCATION"}]
    monkeypatch.setattr(web_intake, "UrllibLLMClient", lambda **kw: MockLLMClient(
        lambda *a: json.dumps(suggestions, ensure_ascii=False)))
    app = create_app(tmp_path)
    client = TestClient(app)
    client.post("/api/v1/web/settings", headers=HEADERS, json={
        "enabled": True, "api_base": "http://127.0.0.1:9001/v1", "model": "test"})
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    payload = candidates(draft)
    payload["candidates"] = [{**payload["candidates"][0], "id": f"checked-{i}"}
                             for i in range(799)]
    draft = client.post(endpoint + "/candidates", headers=HEADERS, json=payload).json()
    response = client.post(endpoint + "/sources/a/extract", headers=HEADERS,
                           json={"revision": draft["revision"]})
    assert response.status_code == 200
    draft = response.json()
    assert len(draft["candidates"]) == 800
    assert sum(c["checked"] for c in draft["candidates"]) == 799
    assert draft["sources"][0]["model_audit"]["status"] == "PARTIAL"
    assert draft["sources"][0]["model_audit"]["limited_candidates"] == 1
    saved = client.post(endpoint + "/candidates", headers=HEADERS,
                        json={"revision": draft["revision"], "candidates": draft["candidates"]})
    assert saved.status_code == 200



def test_extraction_attempt_id_commits_with_same_status_and_legacy_clients(tmp_path, monkeypatch):
    from privacytrace import web_intake
    from privacytrace.policy_llm_extractor import MockLLMClient

    suggestions = [{"excerpt": "我们不会读取联系人。", "data_type": "CONTACTS"}]
    monkeypatch.setattr(
        web_intake, "UrllibLLMClient",
        lambda **kw: MockLLMClient(lambda *a: json.dumps(suggestions, ensure_ascii=False)),
    )
    client = TestClient(create_app(tmp_path))
    client.post("/api/v1/web/settings", headers=HEADERS, json={
        "enabled": True, "api_base": "http://127.0.0.1:9001/v1", "model": "test",
    })
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    extract_path = endpoint + "/sources/a/extract"
    legacy = client.post(extract_path, headers=HEADERS, json={"revision": draft["revision"]})
    assert legacy.status_code == 200, legacy.text
    draft = legacy.json()
    original_status = draft["sources"][0]["model_audit"]["status"]
    assert original_status == "SUCCESS"
    assert "attempt_id" not in draft["sources"][0]["model_audit"]
    for attempt in ("a" * 32, "b" * 32):
        old_revision = draft["revision"]
        result = client.post(extract_path, headers=HEADERS, json={
            "revision": old_revision, "attempt_id": attempt,
        })
        assert result.status_code == 200, result.text
        draft = result.json()
        assert draft["revision"] == old_revision + 1
        assert draft["sources"][0]["model_audit"]["status"] == original_status
        assert draft["sources"][0]["model_audit"]["attempt_id"] == attempt
        assert client.get(endpoint).json()["sources"][0]["model_audit"]["attempt_id"] == attempt
        assert draft["sources"][1]["model_audit"] == {}
    for invalid in ("bad", "F" * 32, "g" * 32, "a" * 33, 1234):
        bad = client.post(extract_path, headers=HEADERS, json={
            "revision": draft["revision"], "attempt_id": invalid,
        })
        assert bad.status_code == 422, bad.text
        assert bad.json()["detail"] == "INPUT_VALIDATION_FAILED"
        assert client.get(endpoint).json()["revision"] == draft["revision"]


def test_failed_extraction_audit_stores_attempt_without_leaking_secrets(tmp_path, monkeypatch):
    from privacytrace import web_intake
    from privacytrace.policy_llm_extractor import MockLLMClient

    secret = "PRIVATE_LLM_RESPONSE_MARKER"
    def failure(*args):
        raise ValueError(secret)
    monkeypatch.setattr(web_intake, "UrllibLLMClient", lambda **kw: MockLLMClient(failure))
    client = TestClient(create_app(tmp_path))
    client.post("/api/v1/web/settings", headers=HEADERS, json={
        "enabled": True, "api_base": "https://model.example/v1", "model": "test",
        "api_key": secret,
    })
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    attempt_id = "c" * 32
    result = client.post(endpoint + "/sources/a/extract", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": attempt_id,
    })
    assert result.status_code == 200, result.text
    audit = result.json()["sources"][0]["model_audit"]
    assert audit["status"] == "FAILED"
    assert audit["attempt_id"] == attempt_id
    assert secret not in result.text and secret not in client.get(endpoint).text


def test_model_error_cannot_echo_secret_into_draft_or_audit(tmp_path, monkeypatch):
    from privacytrace import web_intake
    from privacytrace.policy_llm_extractor import MockLLMClient

    marker = "PRIVATE_SERVER_ECHO_CREDENTIAL"

    def failure(*args):
        raise ValueError(marker)

    monkeypatch.setattr(web_intake, "UrllibLLMClient",
                        lambda **kw: MockLLMClient(failure))
    client = TestClient(create_app(tmp_path))
    client.post("/api/v1/web/settings", headers=HEADERS, json={
        "enabled": True, "api_base": "https://model.example/v1", "model": "test",
        "api_key": marker})
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    response = client.post(endpoint + "/sources/a/extract", headers=HEADERS,
                           json={"revision": draft["revision"]})
    assert response.status_code == 200
    assert response.json()["sources"][0]["model_audit"]["status"] == "FAILED"
    assert marker not in response.text and marker not in client.get(endpoint).text


def test_unsafe_environment_endpoint_cannot_echo_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVACYTRACE_LLM_API_BASE", "https://user:PRIVATE@model.example/v1?key=SECRET")
    response = TestClient(create_app(tmp_path)).get("/api/v1/web/settings")
    assert response.status_code == 200 and response.json()["api_base"] == ""
    assert "PRIVATE" not in response.text and "SECRET" not in response.text


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
        policy_fetch,
        "resolve_addresses",
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
        policy_fetch,
        "resolve_addresses",
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
