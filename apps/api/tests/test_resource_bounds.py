"""Opaque-box E2E test suite for Resource Bounds, Rate Limiting & Log Redaction (R4).

Requirements covered:
- Feature 15: Strict Request Body Limits (413) (Tiers 1-3)
- Feature 16: Concurrency & Rate Limiting (429) (Tiers 1-3)
- Feature 17: Log & Error Response Redaction (Tiers 1-3)
"""

import logging

from fastapi.testclient import TestClient

from privacytrace.main import create_app
from privacytrace.middleware import TokenRedactionFilter


def get_app(tmp_path, mode="remote", monkeypatch=None):
    """Instantiate application with configured mode and environment."""
    if monkeypatch:
        monkeypatch.setenv("PRIVACYTRACE_MODE", mode)
    try:
        return create_app(store_root=tmp_path, mode=mode)
    except TypeError:
        return create_app(store_root=tmp_path)


# ==============================================================================
# Feature 15: Strict Request Body Limits (413) (Tiers 1-3)
# ==============================================================================


def test_review_body_exceeding_512k_returns_413(tmp_path, monkeypatch):
    """Tier 1: Request payload to /api/v1/jobs/{id}/reviews exceeding 512 KiB returns 413."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    oversized_note = "x" * (512 * 1024 + 100)
    payload = {
        "actor": "operator",
        "reason": "oversized test",
        "note": oversized_note,
    }

    resp = client.post(
        "/api/v1/jobs/test-job/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json=payload,
    )
    assert resp.status_code == 413
    assert "detail" in resp.json()


def test_review_body_within_512k_accepted(tmp_path, monkeypatch):
    """Tier 2: Request payload to reviews within 512 KiB is NOT rejected by body limit."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    small_payload = {
        "actor": "operator",
        "reason": "normal test",
        "note": "A" * 1024,
    }
    resp = client.post(
        "/api/v1/jobs/test-job/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json=small_payload,
    )
    # Fails with job not found (404) or job not completed (409), but NOT 413
    assert resp.status_code != 413


def test_draft_body_exceeding_8mb_returns_413(tmp_path, monkeypatch):
    """Tier 1: Request payload to /api/v1/web/drafts exceeding 8 MiB returns 413."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    oversized_name = "x" * (8 * 1024 * 1024 + 100)
    payload = {"name": oversized_name}

    resp = client.post(
        "/api/v1/web/drafts",
        headers={"X-PrivacyTrace-Local": "1"},
        json=payload,
    )
    assert resp.status_code == 413
    assert resp.json().get("detail") in ("INPUT_TOO_LARGE", "Request too large")


def test_draft_body_within_8mb_accepted(tmp_path, monkeypatch):
    """Tier 2: Request payload to web drafts within 8 MiB does not return 413."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    payload = {
        "name": "valid-draft-name",
        "sources": [
            {
                "id": "official-web",
                "title": "Official Privacy Policy",
                "source_type": "OFFICIAL_WEB_POLICY",
            }
        ],
    }
    resp = client.post(
        "/api/v1/web/drafts",
        headers={"X-PrivacyTrace-Local": "1"},
        json=payload,
    )
    assert resp.status_code != 413


def test_apk_upload_content_length_exceeding_150mb_returns_413(tmp_path, monkeypatch):
    """Tier 1: Content-Length header exceeding 150 MiB on APK upload
    returns 413 without reading body."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    excess_length = str(150 * 1024 * 1024 + 1)
    resp = client.post(
        "/api/v1/web/drafts/test-draft/apk",
        headers={
            "X-PrivacyTrace-Local": "1",
            "Content-Length": excess_length,
            "Content-Type": "application/octet-stream",
        },
        content=b"dummy",
    )
    assert resp.status_code == 413
    assert resp.json().get("detail") in ("UPLOAD_TOO_LARGE", "Request too large")


def test_apk_upload_streaming_exceeding_150mb_returns_413(tmp_path, monkeypatch):
    """Tier 2: Streaming chunked upload exceeding 150 MiB aborts with 413."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    created = client.post(
        "/api/v1/web/drafts",
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "name": "stream-limit",
            "sources": [{"id": "policy", "title": "Privacy", "text": "policy text"}],
        },
    )
    assert created.status_code == 200
    draft_url = f"/api/v1/web/drafts/{created.json()['id']}/apk"

    def chunk_generator():
        chunk = b"a" * (1024 * 1024)
        for _ in range(151):
            yield chunk

    resp = client.post(
        draft_url,
        headers={"X-PrivacyTrace-Local": "1", "Content-Type": "application/octet-stream"},
        content=chunk_generator(),
    )
    assert resp.status_code == 413


# ==============================================================================
# Feature 16: Concurrency & Rate Limiting (429) (Tiers 1-3)
# ==============================================================================


def test_remote_rate_limiting_returns_429_on_burst(tmp_path, monkeypatch):
    """Tier 1: Burst of rapid requests in remote mode triggers 429 Too Many Requests."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "5")
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    hit_429 = False
    rate_limited_resp = None
    for _ in range(15):
        resp = client.get("/api/v1/health")
        if resp.status_code == 429:
            hit_429 = True
            rate_limited_resp = resp
            break

    assert hit_429, "Expected rapid burst requests in remote mode to trigger 429"
    assert rate_limited_resp.headers.get("Retry-After") == "60"
    assert "detail" in rate_limited_resp.json()


def test_rate_limit_response_structure_when_triggered(tmp_path, monkeypatch):
    """Tier 2: When rate limit is triggered, response format is structured JSON."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "1")
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    responses = [client.get("/api/v1/health") for _ in range(5)]
    rate_limited = [r for r in responses if r.status_code == 429]
    assert len(rate_limited) > 0, "Expected at least one request to be throttled"
    for r in rate_limited:
        assert r.headers.get("content-type", "").startswith("application/json")
        data = r.json()
        assert "detail" in data


def test_local_mode_exempt_from_remote_rate_limiting(tmp_path, monkeypatch):
    """Tier 2: Loopback requests in local mode are not throttled by remote rate limiter."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "5")
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    for _ in range(15):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200


def test_rate_limiting_per_client_ip_through_trusted_proxy(tmp_path, monkeypatch):
    """Tier 3: Behind a trusted proxy, rate limiting tracks original client IP
    via X-Forwarded-For."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "3")
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver", client=("127.0.0.1", 50000))

    # Client A exhausts quota
    for _ in range(3):
        resp_a = client.get("/api/v1/health", headers={"X-Forwarded-For": "203.0.113.10"})
        assert resp_a.status_code == 200
    throttled_a = client.get("/api/v1/health", headers={"X-Forwarded-For": "203.0.113.10"})
    assert throttled_a.status_code == 429

    # Client B should still have fresh quota
    resp_b = client.get("/api/v1/health", headers={"X-Forwarded-For": "203.0.113.20"})
    assert resp_b.status_code == 200


# ==============================================================================
# Feature 17: Log & Error Response Redaction (Tiers 1-3)
# ==============================================================================


def test_log_redaction_masks_bearer_token(tmp_path, monkeypatch, caplog):
    """Tier 1: Authorization: Bearer capability tokens are masked in server logs."""
    caplog.set_level(logging.DEBUG)
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = "pt_cap_supersecrettokenvalue12345678"
    client.get(
        "/api/v1/jobs/test-job-id",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert "supersecrettokenvalue12345678" not in caplog.text


def test_log_redaction_masks_custom_token_header(tmp_path, monkeypatch, caplog):
    """Tier 1: X-PrivacyTrace-Token header values are masked in server logs."""
    caplog.set_level(logging.DEBUG)
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = "pt_cap_anothersensitivetoken87654321"
    client.get(
        "/api/v1/jobs/test-job-id",
        headers={"X-PrivacyTrace-Token": token},
    )

    assert "anothersensitivetoken87654321" not in caplog.text


def test_token_redaction_filter_unit_level():
    """Tier 2: TokenRedactionFilter properly sanitizes strings, dicts, and tuple args."""
    filter_obj = TokenRedactionFilter()

    # 1. String message
    record1 = logging.LogRecord(
        "test",
        logging.INFO,
        "file.py",
        10,
        "Token: pt_cap_abcdef1234567890abcdef1234567890",
        (),
        None,
    )
    filter_obj.filter(record1)
    assert "pt_cap_***" in record1.msg
    assert "abcdef1234567890" not in record1.msg

    # 2. Dict args
    record2 = logging.LogRecord(
        "test",
        logging.INFO,
        "file.py",
        10,
        "Data %s",
        ({"token": "pt_cap_secrettoken1234567890123456", "other": 42},),
        None,
    )
    filter_obj.filter(record2)
    assert "secrettoken" not in str(record2.args)

    # 3. Multiple tokens
    msg_multi = "Tokens: pt_cap_tok11111111111111111111 and pt_cap_tok22222222222222222222"
    record3 = logging.LogRecord("test", logging.INFO, "file.py", 10, msg_multi, (), None)
    filter_obj.filter(record3)
    assert record3.msg.count("pt_cap_***") == 2
    assert "tok111" not in record3.msg
    assert "tok222" not in record3.msg


def test_error_responses_never_leak_filesystem_paths(tmp_path, monkeypatch):
    """Tier 1: 400, 401, 403, 404, 422 error responses do not leak local absolute paths."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    resp_404 = client.get(
        "/api/v1/jobs/nonexistent-id", headers={"Authorization": "Bearer pt_cap_test"}
    )
    assert resp_404.status_code in (401, 403, 404)
    assert str(tmp_path) not in resp_404.text
    assert "C:\\Users\\" not in resp_404.text
    assert "/Users/" not in resp_404.text


def test_error_responses_never_echo_plaintext_tokens(tmp_path, monkeypatch):
    """Tier 1: Error responses never echo plaintext capability tokens back to client."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    malicious_token = "pt_cap_malicious_attacker_token_xyz"
    resp = client.get(
        "/api/v1/jobs/test-target",
        headers={"Authorization": f"Bearer {malicious_token}"},
    )
    assert resp.status_code in (401, 403, 404)
    assert malicious_token not in resp.text


def test_binary_apk_payload_not_echoed_in_validation_error(tmp_path, monkeypatch):
    """Tier 2: Invalid binary payload uploaded does not echo binary bytes in error response."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")

    garbage_binary = b"\x00\x01\x02\xff\xfe\xfd" * 50
    resp = client.post(
        "/api/v1/web/drafts/test-draft/apk",
        headers={"X-PrivacyTrace-Local": "1", "Content-Type": "application/octet-stream"},
        content=garbage_binary,
    )
    assert resp.status_code in (404, 409, 422)
    assert "\\x00" not in resp.text
    assert "\x00" not in resp.text
