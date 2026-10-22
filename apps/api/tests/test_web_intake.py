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


def candidates(draft, checked=True, excerpt="我们不会读取联系人。", candidate_id="quote1"):
    return {
        "revision": draft["revision"],
        "candidates": [
            {
                "id": candidate_id,
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


def test_candidate_id_bound_matches_the_internal_evidence_limit(tmp_path):
    """#246: the public bound must be what the prefixed evidence id can actually hold."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    saved = client.post(
        endpoint + "/candidates", headers=HEADERS, json=candidates(draft, candidate_id="c" * 87)
    )
    assert saved.status_code == 200, saved.text
    updated = saved.json()
    assert updated["candidates"][0]["id"] == "c" * 87
    evidence = app.state.web_intake.captures(updated, require_checked=False)[0]["evidence"]
    sentence = next(item for item in evidence if item.kind == "POLICY_SENTENCE")
    assert sentence.id == "web-sentence-" + "c" * 87 and len(sentence.id) == 100
    claim = app.state.web_intake.captures(updated, require_checked=False)[0]["claims"][0]
    assert claim.evidence_ids == [sentence.id]
    for length in (88, 100, 101):
        before = client.get(endpoint).json()
        response = client.post(
            endpoint + "/candidates", headers=HEADERS,
            json=candidates(before, candidate_id="c" * length),
        )
        assert response.status_code == 422, response.text
        assert client.get(endpoint).json() == before
    duplicate = client.get(endpoint).json()
    payload = candidates(duplicate)
    payload["candidates"].append({**payload["candidates"][0]})
    response = client.post(endpoint + "/candidates", headers=HEADERS, json=payload)
    assert response.status_code == 409, response.text
    assert client.get(endpoint).json() == duplicate


def test_candidate_empty_condition_is_stored_as_absent(tmp_path):
    """#247: the save route accepts the same absent condition as the legacy import."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    payload = candidates(draft)
    payload["candidates"][0]["condition"] = ""
    response = client.post(endpoint + "/candidates", headers=HEADERS, json=payload)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["candidates"][0]["condition"] is None
    capture = app.state.web_intake.captures(updated, require_checked=False)[0]
    assert capture["claims"][0].condition is None


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
        reserve = client.post(endpoint + "/sources/a/attempts", headers=HEADERS, json={
            "revision": old_revision, "attempt_id": attempt,
        })
        assert reserve.status_code == 200, reserve.text
        assert reserve.json()["state"] == "RESERVED"
        result = client.post(extract_path, headers=HEADERS, json={
            "revision": old_revision, "attempt_id": attempt,
        })
        assert result.status_code == 200, result.text
        draft = result.json()
        assert draft["revision"] == old_revision + 1
        assert draft["sources"][0]["model_audit"]["status"] == original_status
        assert draft["sources"][0]["model_audit"]["attempt_id"] == attempt
        receipt = client.get(endpoint + "/sources/a/attempts/" + attempt).json()
        assert receipt["state"] == "COMMITTED"
        assert client.get(endpoint).json()["sources"][0]["model_audit"]["attempt_id"] == attempt
        assert draft["sources"][1]["model_audit"] == {}
        if attempt == "a" * 32:
            # A committed at old_revision+1. B's stale request must reject with
            # 409 without replacing A's same-status audit or advancing revision.
            rejected = client.post(extract_path, headers=HEADERS, json={
                "revision": old_revision, "attempt_id": "d" * 32,
            })
            assert rejected.status_code == 409, rejected.text
            persisted = client.get(endpoint).json()
            assert persisted["revision"] == draft["revision"]
            assert persisted["sources"][0]["model_audit"]["attempt_id"] == attempt
            assert persisted["sources"][0]["model_audit"]["status"] == original_status
    for invalid in ("bad", "F" * 32, "g" * 32, "a" * 33, 1234):
        bad = client.post(extract_path, headers=HEADERS, json={
            "revision": draft["revision"], "attempt_id": invalid,
        })
        assert bad.status_code == 422, bad.text
        assert bad.json()["detail"] == "INPUT_VALIDATION_FAILED"
        assert client.get(endpoint).json()["revision"] == draft["revision"]



def test_concurrent_source_extraction_refuses_second_paid_request_and_releases_slot(
    tmp_path, monkeypatch
):
    """Only one external model invocation may run per draft/source at a time."""
    from concurrent.futures import ThreadPoolExecutor

    from privacytrace import web_intake
    from privacytrace.policy_llm_extractor import MockLLMClient

    entered = threading.Event()
    release = threading.Event()
    calls = []
    suggestions = [{"excerpt": "我们不会读取联系人。", "data_type": "CONTACTS"}]

    def delayed_response(*args):
        calls.append(1)
        entered.set()
        assert release.wait(12), "blocked extraction never released"
        return json.dumps(suggestions, ensure_ascii=False)

    monkeypatch.setattr(
        web_intake, "UrllibLLMClient",
        lambda **kw: MockLLMClient(delayed_response),
    )
    client = TestClient(create_app(tmp_path))
    assert client.post("/api/v1/web/settings", headers=HEADERS, json={
        "enabled": True, "api_base": "https://model.example/v1", "model": "mock",
        "api_key": "test-only-mock-model-key",
    }).status_code == 200
    draft = new_draft(client)
    endpoint = f"/api/v1/web/drafts/{draft['id']}"
    extract_path = endpoint + "/sources/a/extract"
    reserve = client.post(endpoint + "/sources/a/attempts", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": "a" * 32,
    })
    assert reserve.status_code == 200, reserve.text
    with ThreadPoolExecutor(max_workers=2) as pool:
        initial = pool.submit(
            client.post, extract_path, headers=HEADERS,
            json={"revision": draft["revision"], "attempt_id": "a" * 32},
        )
        try:
            assert entered.wait(8), "first extraction never entered model client"
            # An old client without attempt_id must be protected too.
            duplicate = client.post(
                extract_path, headers=HEADERS,
                json={"revision": draft["revision"]},
            )
            assert duplicate.status_code == 409, duplicate.text
            assert duplicate.json()["detail"] == "EXTRACTION_IN_PROGRESS"
            assert len(calls) == 1
            assert client.get(endpoint).json()["revision"] == draft["revision"]
        finally:
            release.set()
        completed = initial.result(timeout=12)
    assert completed.status_code == 200, completed.text
    assert completed.json()["sources"][0]["model_audit"]["attempt_id"] == "a" * 32
    # The lane is released: a fresh attempt may reserve against the new revision.
    assert client.post(endpoint + "/sources/a/attempts", headers=HEADERS, json={
        "revision": completed.json()["revision"], "attempt_id": "b" * 32,
    }).status_code == 200
    assert len(calls) == 1



def test_delayed_reserved_attempt_and_late_expired_post_rejected(
    tmp_path, monkeypatch
):
    from privacytrace import web_intake
    from privacytrace.policy_llm_extractor import MockLLMClient

    calls = []
    monkeypatch.setattr(
        web_intake, "UrllibLLMClient",
        lambda **kw: MockLLMClient(lambda *a: calls.append(1) or "[]"),
    )
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.post("/api/v1/web/settings", headers=HEADERS, json={
        "enabled": True, "api_base": "http://127.0.0.1:9011/v1", "model": "test",
    }).status_code == 200
    draft = new_draft(client)
    path = f"/api/v1/web/drafts/{draft['id']}/sources/a"
    revision = draft["revision"]
    attempt = "e" * 32
    reserve = client.post(path + "/attempts", headers=HEADERS, json={
        "revision": revision, "attempt_id": attempt,
    })
    assert reserve.status_code == 200
    assert reserve.json()["state"] == "RESERVED"
    assert client.get(path + "/attempts/" + attempt).json()["state"] == "RESERVED"
    assert len(calls) == 0
    # The model POST arrives only after registration and multiple idle reads.
    result = client.post(path + "/extract", headers=HEADERS, json={
        "revision": revision, "attempt_id": attempt,
    })
    assert result.status_code == 200, result.text
    assert len(calls) == 1
    assert client.get(path + "/attempts/" + attempt).json()["state"] == "COMMITTED"
    assert client.post(path + "/extract", headers=HEADERS, json={
        "revision": revision, "attempt_id": attempt,
    }).status_code == 409
    assert len(calls) == 1

    # A separate reserved attempt expires while no model POST has been sent.
    later = "f" * 32
    next_revision = result.json()["revision"]
    app.state.web_intake.ATTEMPT_RESERVATION_SECONDS = -1
    assert client.post(path + "/attempts", headers=HEADERS, json={
        "revision": next_revision, "attempt_id": later,
    }).status_code == 200
    assert client.get(path + "/attempts/" + later).json()["state"] == "EXPIRED"
    late = client.post(path + "/extract", headers=HEADERS, json={
        "revision": next_revision, "attempt_id": later,
    })
    assert late.status_code == 409
    assert len(calls) == 1


def test_reserved_attempt_blocks_legacy_and_source_fetch_and_terminal_failure_frees_lane(
    tmp_path
):
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = new_draft(client)
    path = f"/api/v1/web/drafts/{draft['id']}/sources/a"
    attempt = "c" * 32
    reserve = client.post(path + "/attempts", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": attempt,
    })
    assert reserve.status_code == 200
    assert client.post(path + "/attempts", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": "d" * 32,
    }).status_code == 409
    assert client.post(path + "/extract", headers=HEADERS, json={
        "revision": draft["revision"],
    }).status_code == 409
    # The existing /fetch endpoint must not mutate an outstanding reservation.
    assert client.post(path + "/fetch", headers=HEADERS, json={
        "revision": draft["revision"],
    }).status_code == 409
    app.state.web_intake.ATTEMPT_RESERVATION_SECONDS = -1
    # Preserve terminal EXPIRED on next status check after advancing expiry
    records = app.state.web_intake._load_attempts(draft["id"])
    records[attempt]["expires_at"] = 0
    app.state.web_intake._save_attempts(draft["id"], records)
    assert client.get(path + "/attempts/" + attempt).json()["state"] == "EXPIRED"
    assert client.post(path + "/attempts", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": "d" * 32,
    }).status_code == 200
    assert client.get(path + "/attempts/" + attempt).json()["state"] == "EXPIRED"


def test_attempt_quota_and_unreserved_attempt_report_their_own_codes(tmp_path):
    """A spent attempt history is not the same failure as a stale revision."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = new_draft(client)
    path = f"/api/v1/web/drafts/{draft['id']}/sources/a"
    service = app.state.web_intake
    service.MAX_ATTEMPT_RECORDS_PER_SOURCE = 1
    assert client.post(path + "/attempts", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": "a" * 32,
    }).status_code == 200
    service.ATTEMPT_RESERVATION_SECONDS = -1
    records = service._load_attempts(draft["id"])
    records["a" * 32]["expires_at"] = 0
    service._save_attempts(draft["id"], records)
    exhausted = client.post(path + "/attempts", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": "b" * 32,
    })
    assert exhausted.status_code == 409, exhausted.text
    assert exhausted.json()["detail"] == "EXTRACTION_ATTEMPT_QUOTA_REACHED"
    unreserved = client.post(path + "/extract", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": "c" * 32,
    })
    assert unreserved.status_code == 409, unreserved.text
    assert unreserved.json()["detail"] == "EXTRACTION_ATTEMPT_NOT_RESERVED"


def test_startup_recovers_interrupted_running_attempt_from_its_audit(tmp_path):
    """A killed process leaves RUNNING behind; the audit decides COMMITTED or FAILED."""
    client = TestClient(create_app(tmp_path))
    draft = new_draft(client)
    app = client.app
    service = app.state.web_intake
    committed, failed = "a" * 32, "b" * 32
    service._save_attempts(draft["id"], {
        committed: {
            "attempt_id": committed, "source_id": "a", "revision": draft["revision"],
            "state": "RUNNING", "created_at": 0, "expires_at": 0,
        },
        failed: {
            "attempt_id": failed, "source_id": "b", "revision": draft["revision"],
            "state": "RUNNING", "created_at": 0, "expires_at": 0,
        },
    })
    with service.data_store._transaction():
        current = service._get(draft["id"])
        current["sources"][0]["model_audit"] = {"status": "SUCCESS", "attempt_id": committed}
        # The committed audit is already on disk when the process dies; only
        # current.json needs the record, no new revision snapshot is produced.
        service._write_private(service.directory(draft["id"]) / "current.json", current)
    service.close()
    service.start_service()
    records = service._load_attempts(draft["id"])
    assert records[committed]["state"] == "COMMITTED"
    assert records[failed]["state"] == "FAILED"


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
    assert client.post(endpoint + "/sources/a/attempts", headers=HEADERS, json={
        "revision": draft["revision"], "attempt_id": attempt_id,
    }).status_code == 200
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
