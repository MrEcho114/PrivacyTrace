"""Adversarial stress-test and empirical challenge suite for R3 & R4.

Covers:
- R3 Endpoint Matrix Circumvention (enumeration bypass, admin shielding, path traversal)
- R4 Resource Bounds & DoS (payload limits, streaming limits, rate limiting)
- R4 Log Redaction & Sensitive Data Leakage (status codes 400, 401, 403, 404, 413, 422, 429, 500)
- Empirical reproduction of security gaps and edge cases
"""

import logging
import sys
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import create_app
from privacytrace.middleware import TokenRedactionFilter, install_log_redaction


def get_remote_app(tmp_path):
    return create_app(store_root=tmp_path, mode="remote")


def get_local_app(tmp_path):
    return create_app(store_root=tmp_path, mode="local")


# ==============================================================================
# 1. R3: Endpoint Matrix Circumvention Attacks
# ==============================================================================


def test_adversarial_jobs_listing_direct_remote_forbidden(tmp_path):
    """Adversarial: Direct GET /api/v1/jobs in remote mode must return 403."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 403
    assert "detail" in resp.json()


def test_adversarial_jobs_listing_trailing_slash_remote(tmp_path):
    """Adversarial: GET /api/v1/jobs/ (trailing slash) must NOT leak job list.
    Both redirect modes are rejected by the pre-body guard with 403.
    """
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    # Without following redirect
    r_no_redir = client.get("/api/v1/jobs/", follow_redirects=False)
    assert r_no_redir.status_code == 403
    assert "jobs" not in r_no_redir.json()

    # Following redirect
    r_redir = client.get("/api/v1/jobs/", follow_redirects=True)
    assert r_redir.status_code == 403


@pytest.mark.parametrize(
    "attack_path",
    [
        "/api/v1/jobs/..",
        "/api/v1/jobs/../jobs",
        "/api/v1/jobs/%2e%2e",
        "/api/v1/jobs/%2e%2e/jobs",
        "/api/v1/web/../jobs",
        "/api/v1/jobs/.",
        "/api/v1/health/../../api/v1/jobs",
    ],
    ids=[
        "jobs-parent",
        "jobs-parent-jobs",
        "jobs-url-encoded-parent",
        "jobs-url-encoded-parent-jobs",
        "web-parent-jobs",
        "jobs-current-dir",
        "health-traversal-jobs",
    ],
)
def test_adversarial_jobs_listing_path_traversal(tmp_path, attack_path):
    """Adversarial: Path traversal variants attempting to reach job enumeration are blocked."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get(attack_path)
    assert resp.status_code in (401, 403, 404)
    if resp.headers.get("content-type", "").startswith("application/json"):
        assert "jobs" not in resp.json()


@pytest.mark.parametrize(
    "header_name,header_val",
    [
        ("X-HTTP-Method-Override", "GET"),
        ("X-Method-Override", "GET"),
        ("X-HTTP-Method", "GET"),
    ],
    ids=["http-method-override", "method-override", "http-method"],
)
def test_adversarial_jobs_listing_method_override_headers(tmp_path, header_name, header_val):
    """Adversarial: Method override headers on POST /api/v1/jobs cannot trick
    the server into listing jobs."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")
    resp = client.post(
        "/api/v1/jobs",
        headers={header_name: header_val},
        json={"sample_id": "method-override-test"},
    )
    # Server processes as POST (creating single job), does not list jobs
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "job_id" in data
    assert "jobs" not in data


@pytest.mark.parametrize("method", ["head", "options", "put", "delete", "patch"])
def test_adversarial_jobs_listing_alternative_methods(tmp_path, method):
    """Adversarial: Alternative HTTP methods on /api/v1/jobs return 405 Method Not Allowed."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")
    req_fn = getattr(client, method)
    resp = req_fn("/api/v1/jobs")
    assert resp.status_code == 405


def test_adversarial_jobs_listing_with_valid_bearer_token(tmp_path):
    """Adversarial: Even a client holding a valid capability token cannot
    enumerate global jobs list."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    # Create legitimate job
    create_resp = client.post("/api/v1/jobs", json={"sample_id": "valid-user"})
    token = create_resp.json()["capability_token"]

    # Attempt to list all jobs using the valid token
    list_resp = client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 403


def test_adversarial_jobs_listing_header_spoofing(tmp_path):
    """Adversarial: Header spoofing (X-PrivacyTrace-Local, X-Forwarded-For) in remote mode
    cannot bypass job enumeration block."""
    app = get_remote_app(tmp_path)

    # 1. Local header spoofing
    client1 = TestClient(app, base_url="http://testserver")
    r1 = client1.get("/api/v1/jobs", headers={"X-PrivacyTrace-Local": "1"})
    assert r1.status_code == 403

    # 2. Case-insensitive local header spoofing
    r2 = client1.get("/api/v1/jobs", headers={"x-privacytrace-local": "true"})
    assert r2.status_code == 403

    # 3. Untrusted proxy forward spoofing
    client_untrusted = TestClient(app, base_url="http://testserver", client=("198.51.100.1", 50000))
    r3 = client_untrusted.get(
        "/api/v1/jobs",
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert r3.status_code in (400, 403)


# ==============================================================================
# 2. R3: Admin Settings Shielding Attacks
# ==============================================================================


def test_adversarial_settings_direct_remote_forbidden(tmp_path):
    """Adversarial: GET and POST /api/v1/web/settings in remote mode return 403."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    get_resp = client.get("/api/v1/web/settings")
    assert get_resp.status_code == 403

    post_resp = client.post("/api/v1/web/settings", json={"enabled": True})
    assert post_resp.status_code == 403


def test_adversarial_settings_trailing_slash_remote(tmp_path):
    """Adversarial: Trailing slash on /api/v1/web/settings/ is shielded and redirected/blocked."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    r_get = client.get("/api/v1/web/settings/", follow_redirects=True)
    assert r_get.status_code == 403

    r_post = client.post("/api/v1/web/settings/", json={"enabled": True}, follow_redirects=True)
    assert r_post.status_code == 403


@pytest.mark.parametrize(
    "query",
    [
        "?admin=1",
        "?role=admin",
        "?sudo=true",
        "?debug=1",
        "?mode=local",
        "?bypass=1",
    ],
)
def test_adversarial_settings_query_parameter_pollution(tmp_path, query):
    """Adversarial: Query parameters cannot bypass admin settings shielding."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    get_resp = client.get(f"/api/v1/web/settings{query}")
    assert get_resp.status_code == 403

    post_resp = client.post(f"/api/v1/web/settings{query}", json={"enabled": True})
    assert post_resp.status_code == 403


@pytest.mark.parametrize("method", ["put", "delete", "patch", "head", "options"])
def test_adversarial_settings_alternative_methods(tmp_path, method):
    """All remote methods on admin settings are rejected before body parsing."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")
    req_fn = getattr(client, method)
    resp = req_fn("/api/v1/web/settings")
    assert resp.status_code == 403


# ==============================================================================
# 3. R4: Resource Bounds & DoS Attacks
# ==============================================================================


def test_adversarial_apk_upload_exceeding_150mb(tmp_path):
    """Adversarial: APK upload payload exceeding 150 MiB returns 413."""
    app = get_local_app(tmp_path)
    client = TestClient(app, base_url="http://localhost")

    # Content-Length header exceeding 150 MiB
    r_hdr = client.post(
        "/api/v1/web/drafts/d1/apk",
        headers={
            "X-PrivacyTrace-Local": "1",
            "Content-Length": str(150 * 1024 * 1024 + 1024),
            "Content-Type": "application/octet-stream",
        },
        content=b"dummy",
    )
    assert r_hdr.status_code == 413
    assert r_hdr.json().get("detail") in ("UPLOAD_TOO_LARGE", "Request too large")

    # Stream test must reach an authorized existing Draft, otherwise the route
    # intentionally rejects before consuming the upload body.
    created = client.post(
        "/api/v1/web/drafts",
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "name": "bounded",
            "sources": [{"id": "policy", "title": "Privacy", "text": "policy text"}],
        },
    )
    assert created.status_code == 200
    draft_url = f"/api/v1/web/drafts/{created.json()['id']}/apk"

    # Streaming chunks exceeding 150 MiB
    def chunk_gen():
        chunk = b"X" * (1024 * 1024)
        for _ in range(151):
            yield chunk

    r_stream = client.post(
        draft_url,
        headers={"X-PrivacyTrace-Local": "1", "Content-Type": "application/octet-stream"},
        content=chunk_gen(),
    )
    assert r_stream.status_code == 413


def test_adversarial_draft_body_exceeding_8mb(tmp_path):
    """Adversarial: Draft creation payload exceeding 8 MiB returns 413."""
    app = get_local_app(tmp_path)
    client = TestClient(app, base_url="http://localhost")

    oversized_name = "A" * (8 * 1024 * 1024 + 1024)
    resp = client.post(
        "/api/v1/web/drafts",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"name": oversized_name},
    )
    assert resp.status_code == 413
    assert resp.json().get("detail") in ("INPUT_TOO_LARGE", "Request too large")


def test_adversarial_review_write_exceeding_512kb(tmp_path):
    """Adversarial: Job review write payload exceeding 512 KiB returns 413."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    oversized_note = "B" * (512 * 1024 + 1024)
    created = client.post("/api/v1/jobs", json={}).json()
    resp = client.post(
        f"/api/v1/jobs/{created['id']}/reviews",
        headers={"Authorization": f"Bearer {created['token']}"},
        json={"actor": "operator", "reason": "test", "note": oversized_note},
    )
    assert resp.status_code == 413
    assert resp.json().get("detail") == "Request too large"


def test_adversarial_cancel_write_exceeding_512kb(tmp_path):
    """Adversarial: Job cancel write payload exceeding 512 KiB returns 413."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    oversized_data = "C" * (512 * 1024 + 1024)
    created = client.post("/api/v1/jobs", json={}).json()
    resp = client.post(
        f"/api/v1/jobs/{created['id']}/cancel",
        headers={"Authorization": f"Bearer {created['token']}"},
        json={"reason": oversized_data},
    )
    assert resp.status_code == 413
    assert resp.json().get("detail") == "Request too large"


def test_adversarial_job_creation_payload_limit_gap(tmp_path):
    """Adversarial: POST /api/v1/jobs (job creation) must enforce 512 KiB body limit.
    Vulnerability: Currently, path.startswith('/api/v1/jobs/') does not match
    '/api/v1/jobs', allowing arbitrarily large payloads (e.g. 10 MB) to be accepted
    with 200 OK.
    """
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    oversized_body = {"sample_id": "X" * (600 * 1024)}
    resp = client.post("/api/v1/jobs", json=oversized_body)
    # Expected: 413 Payload Too Large
    # Actual without fix: 200 OK
    assert resp.status_code == 413


def test_adversarial_remote_rate_limiting_burst_and_headers(tmp_path, monkeypatch):
    """Adversarial: Burst requests in remote mode trigger 429 Too Many Requests,
    returning structured JSON and Retry-After header."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "5")
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    hit_429 = False
    rate_resp = None
    for _ in range(20):
        r = client.get("/api/v1/health")
        if r.status_code == 429:
            hit_429 = True
            rate_resp = r
            break

    assert hit_429, "Expected burst requests to trigger 429"
    assert rate_resp.headers.get("Retry-After") == "60"
    assert rate_resp.headers.get("content-type", "").startswith("application/json")
    data = rate_resp.json()
    assert data.get("detail") == "Rate limit exceeded"


def test_adversarial_rate_limiting_ip_isolation(tmp_path, monkeypatch):
    """Adversarial: Rate limiting one client IP behind trusted proxy does not DoS another client."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "3")
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver", client=("127.0.0.1", 50000))

    # Attacker IP exhausts limit
    for _ in range(3):
        r = client.get("/api/v1/health", headers={"X-Forwarded-For": "198.51.100.99"})
        assert r.status_code == 200
    throttled = client.get("/api/v1/health", headers={"X-Forwarded-For": "198.51.100.99"})
    assert throttled.status_code == 429

    # Legitimate victim IP still succeeds
    victim_resp = client.get("/api/v1/health", headers={"X-Forwarded-For": "198.51.100.100"})
    assert victim_resp.status_code == 200


# ==============================================================================
# 4. R4: Log Redaction & Sensitive Data Leakage
# ==============================================================================


@pytest.mark.parametrize(
    "status_code,endpoint,method,headers,query,body",
    [
        (
            400,
            "/api/v1/jobs/test-id",
            "GET",
            {},
            "?token=pt_cap_secrettoken_400_query_12345678",
            None,
        ),
        (
            401,
            "/api/v1/jobs/test-id",
            "GET",
            {"Authorization": "Bearer pt_cap_short_401"},
            "",
            None,
        ),
        (
            404,
            "/api/v1/jobs/nonexistent-id",
            "GET",
            {"Authorization": "Bearer pt_cap_valid_token_404_123456789012"},
            "",
            None,
        ),
        (
            413,
            "/api/v1/jobs/test-id/reviews",
            "POST",
            {"Authorization": "Bearer pt_cap_valid_token_413_123456789012"},
            "",
            {"note": "x" * (512 * 1024 + 100), "secret": "pt_cap_inside_payload_413_123456"},
        ),
    ],
    ids=["error-400", "error-401", "error-404", "error-413"],
)
def test_adversarial_error_response_bodies_no_token_leakage(
    tmp_path, status_code, endpoint, method, headers, query, body
):
    """Adversarial: Error response bodies across 400, 401, 404, 413
    must NEVER echo plaintext capability tokens back to the caller."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    if status_code == 413:
        created = client.post("/api/v1/jobs", json={}).json()
        endpoint = f"/api/v1/jobs/{created['id']}/reviews"
        headers = {"Authorization": f"Bearer {created['token']}"}

    req_fn = getattr(client, method.lower())
    kwargs = {"headers": headers}
    if body is not None:
        kwargs["json"] = body

    resp = req_fn(f"{endpoint}{query}", **kwargs)
    assert resp.status_code == status_code

    # Search for any capability token in response body
    assert "pt_cap_" not in resp.text


def test_adversarial_403_mismatched_token_no_leakage(tmp_path):
    """Adversarial: 403 on existing job with mismatched token does not leak token."""
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    # Create real job
    create_resp = client.post("/api/v1/jobs", json={"sample_id": "test-job-403"})
    jid = create_resp.json()["job_id"]

    mismatched_token = "pt_cap_mismatched_attacker_token_1234567890"
    resp = client.get(
        f"/api/v1/jobs/{jid}", headers={"Authorization": f"Bearer {mismatched_token}"}
    )
    assert resp.status_code == 403
    assert mismatched_token not in resp.text


def test_adversarial_422_validation_error_leaks_token_gap(tmp_path):
    """Adversarial: Pydantic 422 validation errors must not echo sensitive tokens.
    Vulnerability: In web_api.py, RequestValidationError handler only sanitizes /api/v1/web/,
    delegating other routes (reviews, consistency evaluate) to FastAPI's default handler
    which reflects caller input in detail[*].input.
    """
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    # Create job
    create_resp = client.post("/api/v1/jobs", json={"sample_id": "test-job-422"})
    jid = create_resp.json()["job_id"]
    token = create_resp.json()["capability_token"]

    # Post invalid payload to reviews
    bad_payload = {"actor": 123, "sensitive_token": token}
    resp = client.post(
        f"/api/v1/jobs/{jid}/reviews",
        headers={"Authorization": f"Bearer {token}"},
        json=bad_payload,
    )
    assert resp.status_code == 422
    # Expected: token is redacted and not echoed back
    # Actual without fix: token is echoed in detail[*].input
    assert token not in resp.text


def test_adversarial_rate_limit_429_body_no_token_leakage(tmp_path, monkeypatch):
    """Adversarial: 429 response body does not echo caller's capability token."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "1")
    app = get_remote_app(tmp_path)
    client = TestClient(app, base_url="http://testserver")

    token = "pt_cap_burst_token_12345678901234567890"
    client.get("/api/v1/health", headers={"Authorization": f"Bearer {token}"})
    resp_429 = client.get("/api/v1/health", headers={"Authorization": f"Bearer {token}"})
    assert resp_429.status_code == 429
    assert token not in resp_429.text


def test_adversarial_500_response_body_no_token_leakage(tmp_path):
    """Adversarial: In unhandled 500 server crash, response body does not leak token."""
    app = get_remote_app(tmp_path)

    token = "pt_cap_crash_token_12345678901234567890"

    @app.get("/api/v1/test-server-crash")
    def trigger_crash():
        raise RuntimeError(f"Server internal crash with secret {token}")

    client = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
    resp = client.get("/api/v1/test-server-crash")
    assert resp.status_code == 500
    assert token not in resp.text


def test_adversarial_log_filter_message_and_args_redacted():
    """Adversarial: TokenRedactionFilter successfully sanitizes log message strings,
    tuple arguments, and dict arguments."""
    filter_obj = TokenRedactionFilter()
    token1 = "pt_cap_sensitive_log_token_111111111111"
    token2 = "pt_cap_sensitive_log_token_222222222222"

    rec = logging.LogRecord(
        name="privacytrace",
        level=logging.INFO,
        pathname="auth.py",
        lineno=42,
        msg=f"Processing {token1}",
        args=({"current_token": token2, "status": "active"},),
        exc_info=None,
    )
    filter_obj.filter(rec)

    assert "pt_cap_***" in rec.msg
    assert token1 not in rec.msg
    assert "pt_cap_***" in str(rec.args)
    assert token2 not in str(rec.args)


def test_adversarial_log_filter_exception_traceback_leakage_gap():
    """Adversarial: When an exception containing a capability token is logged
    via exc_info, TokenRedactionFilter must redact the token from the traceback.
    Vulnerability: TokenRedactionFilter does not inspect record.exc_info or record.exc_text,
    leaving the plaintext token exposed in stdout/log streams.
    """
    stream = StringIO()
    h = logging.StreamHandler(stream)
    logger = logging.getLogger("uvicorn.error")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(h)
    install_log_redaction()

    token = "pt_cap_unhandled_crash_token_123456789012"
    try:
        raise ValueError(f"Failed verifying token {token}")
    except Exception:
        logger.error("Exception in ASGI application", exc_info=sys.exc_info())

    h.flush()
    log_content = stream.getvalue()
    # Expected: token is redacted from log output
    # Actual without fix: token appears in traceback
    assert token not in log_content, f"Token leaked in exception traceback: {log_content}"
