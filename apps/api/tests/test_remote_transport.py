"""Opaque-box E2E test suite for Remote vs Local Mode & Transport Security (R1).

Requirements covered:
- Feature 1: Mode Switch & Loopback Compatibility (Tiers 1-3)
- Feature 2: Remote Host & DNS Rebinding Protection (Tiers 1-3)
- Feature 3: Trusted Reverse Proxy Header Validation (Tiers 1-3)
- Feature 4: Anti-Spoofing of Local Flag (Tiers 1-3)
"""

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import create_app


def get_test_app(tmp_path, mode="local", monkeypatch=None, allowed_hosts=None):
    """Instantiate application with configured mode and environment."""
    if monkeypatch:
        monkeypatch.setenv("PRIVACYTRACE_MODE", mode)
        if allowed_hosts:
            monkeypatch.setenv("PRIVACYTRACE_ALLOWED_HOSTS", ",".join(allowed_hosts))
    try:
        return create_app(store_root=tmp_path, mode=mode)
    except TypeError:
        return create_app(store_root=tmp_path)


# ==============================================================================
# Feature 1: Mode Switch & Loopback Compatibility (Tiers 1-3)
# ==============================================================================


def test_local_mode_default_loopback_health(tmp_path, monkeypatch):
    """Tier 1: By default, app runs in local mode and health returns status ok."""
    monkeypatch.delenv("PRIVACYTRACE_MODE", raising=False)
    app = get_test_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mode"] in ("local", "local-jobs")


def test_remote_mode_switch_via_env(tmp_path, monkeypatch):
    """Tier 1: Setting PRIVACYTRACE_MODE=remote switches app to remote mode."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mode"] == "remote"


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "[::1]", "testserver"],
    ids=["ipv4-loopback", "localhost-name", "ipv6-loopback", "testserver"],
)
def test_local_mode_allows_loopback_hosts(tmp_path, monkeypatch, host):
    """Tier 2: Local mode strictly allows standard loopback hosts."""
    app = get_test_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    base_url = f"http://{host}"
    client = TestClient(app, base_url=base_url)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_local_mode_requires_local_header_for_write(tmp_path, monkeypatch):
    """Tier 1: Local mode requires X-PrivacyTrace-Local: 1 for review and cancel writes."""
    app = get_test_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")
    # Missing header -> 403
    resp_no_header = client.post("/api/v1/jobs/nonexistent-job/cancel")
    assert resp_no_header.status_code == 403

    # With header -> passes local_write check (job not found yields 404 or 409)
    resp_with_header = client.post(
        "/api/v1/jobs/nonexistent-job/cancel",
        headers={"X-PrivacyTrace-Local": "1"},
    )
    assert resp_with_header.status_code in (404, 409)


def test_local_mode_preserves_jobs_list_access(tmp_path, monkeypatch):
    """Tier 1: Local mode allows listing all jobs without capability tokens."""
    app = get_test_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert "jobs" in resp.json()


def test_invalid_mode_configuration_behavior(tmp_path, monkeypatch):
    """Tier 2: Invalid mode value should either default safely to local or raise."""
    monkeypatch.setenv("PRIVACYTRACE_MODE", "unsupported_mode")
    try:
        app = get_test_app(tmp_path, monkeypatch=monkeypatch)
        client = TestClient(app, base_url="http://localhost")
        resp = client.get("/api/v1/health")
        # If it defaulted safely, it should report a valid status
        assert resp.status_code == 200
    except (ValueError, KeyError):
        # Raising on invalid config is also acceptable
        pass


# ==============================================================================
# Feature 2: Remote Host & DNS Rebinding Protection (Tiers 1-3)
# ==============================================================================


@pytest.mark.parametrize(
    "malicious_host",
    [
        "attacker.example",
        "evil.com",
        "192.168.1.100",
        "localhost.attacker.com",
        "attacker.example:8080",
        "subdomain.127.0.0.1.nip.io",
    ],
    ids=[
        "external-domain",
        "evil-domain",
        "private-ip-rebinding",
        "subdomain-spoof",
        "domain-with-port",
        "nip-io-rebinding",
    ],
)
def test_remote_host_rejection_unauthorized_host(tmp_path, monkeypatch, malicious_host):
    """Tier 1 & 2: Remote mode strictly rejects unauthorized hosts with 400 Bad Request."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url=f"http://{malicious_host}")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 400


def test_remote_host_allowed_hosts_whitelist(tmp_path, monkeypatch):
    """Tier 1: Remote mode accepts hosts explicitly included in allowed_hosts."""
    app = get_test_app(
        tmp_path,
        mode="remote",
        monkeypatch=monkeypatch,
        allowed_hosts=["api.privacytrace.example", "testserver"],
    )
    client = TestClient(app, base_url="http://api.privacytrace.example")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


def test_remote_host_case_insensitivity(tmp_path, monkeypatch):
    """Tier 2: Host header matching is case-insensitive per RFC standards."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://TESTSERVER")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200


# ==============================================================================
# Feature 3: Trusted Reverse Proxy Header Validation (Tiers 1-3)
# ==============================================================================


def test_trusted_proxy_forwarded_proto_https(tmp_path, monkeypatch):
    """Tier 1: Requests from trusted proxy forwarding HTTPS scheme are accepted."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get(
        "/api/v1/health",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.195"},
    )
    assert resp.status_code == 200


def test_rfc7239_forwarded_header_from_trusted_proxy(tmp_path, monkeypatch):
    """Tier 1: Standard RFC 7239 Forwarded header from trusted proxy is accepted."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get(
        "/api/v1/health",
        headers={"Forwarded": "for=203.0.113.195;proto=https;host=testserver"},
    )
    assert resp.status_code == 200


def test_untrusted_direct_proxy_headers_cannot_gain_local_access(tmp_path, monkeypatch):
    """Tier 3: Spoofed X-Forwarded-For: 127.0.0.1 cannot grant loopback privileges
    in remote mode."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    # Attempting to list all jobs with spoofed proxy loopback IP
    resp = client.get(
        "/api/v1/jobs",
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    # Remote mode must never allow global jobs enumeration
    assert resp.status_code == 403


def test_multiple_forwarded_for_proxy_chain(tmp_path, monkeypatch):
    """Tier 2: Multiple comma-separated client and proxy IPs are handled safely."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get(
        "/api/v1/health",
        headers={"X-Forwarded-For": "198.51.100.17, 203.0.113.195"},
    )
    assert resp.status_code == 200


# ==============================================================================
# Feature 4: Anti-Spoofing of Local Flag (Tiers 1-3)
# ==============================================================================


def test_remote_mode_rejects_spoofed_local_header_on_jobs_list(tmp_path, monkeypatch):
    """Tier 1: Remote mode rejects X-PrivacyTrace-Local: 1 on GET /api/v1/jobs (403)."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get("/api/v1/jobs", headers={"X-PrivacyTrace-Local": "1"})
    assert resp.status_code == 403


def test_remote_mode_rejects_spoofed_local_header_on_admin_settings(tmp_path, monkeypatch):
    """Tier 1: Remote mode rejects X-PrivacyTrace-Local: 1 on POST /api/v1/web/settings (403)."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.post(
        "/api/v1/web/settings",
        headers={"X-PrivacyTrace-Local": "1", "Origin": "http://localhost:5173"},
        json={"enabled": True, "api_base": "http://localhost:11434/v1", "model": "qwen2.5"},
    )
    assert resp.status_code == 403


def test_remote_mode_rejects_spoofed_local_header_on_job_detail_without_token(
    tmp_path, monkeypatch
):
    """Tier 1: Remote mode rejects X-PrivacyTrace-Local: 1 on job details
    without capability token."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get(
        "/api/v1/jobs/target-job-123",
        headers={"X-PrivacyTrace-Local": "1"},
    )
    # Must be rejected with 401 Unauthorized or 403 Forbidden, never bypassed
    assert resp.status_code in (401, 403)


@pytest.mark.parametrize(
    "header_name,header_value",
    [
        ("X-PrivacyTrace-Local", "1"),
        ("x-privacytrace-local", "1"),
        ("X-PRIVACYTRACE-LOCAL", "1"),
        ("X-PrivacyTrace-Local", "true"),
        ("X-PrivacyTrace-Local", "True"),
    ],
    ids=["exact-case", "lower-case", "upper-case", "bool-true", "bool-True"],
)
def test_remote_mode_case_variants_of_local_header_rejected(
    tmp_path, monkeypatch, header_name, header_value
):
    """Tier 2: Case variants and truthy values of local header cannot bypass remote controls."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get("/api/v1/jobs", headers={header_name: header_value})
    assert resp.status_code == 403


def test_remote_mode_loopback_client_still_enforces_remote_rules(tmp_path, monkeypatch):
    """Tier 3: Even if client IP is loopback, remote mode configuration enforces remote security."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://127.0.0.1")
    # Enumeration must still be blocked
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 403
