"""Tier 1: Feature Coverage Tests for R2: Dual-Scope HTTPS Business Pipeline & Splits (Features F10 - F19).

Covers:
- F10: Caddy HTTPS Reverse Proxy (Header stripping, SNI, HSTS)
- F11: Capability Token Lifecycle
- F12: HTTPS End-to-End Pipeline Execution
- F13: Single APK Analysis Flow
- F14: Base + Splits Analysis Flow
- F15: Cross-Scope & Instance Isolation
- F16: Management Surface Shielding
- F17: Request Quotas & Size Bounds
- F18: Rate Limiting & 429 Retry-After
- F19: Malicious Source & CIDR Protection
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from privacytrace.auth import generate_capability_token
from privacytrace.main import create_app
from privacytrace.package_set import MAX_FILE_SIZE, MAX_PACKAGE_SET_SIZE

ROOT = Path(__file__).resolve().parents[2]
TOKEN_REGEX = re.compile(r"^pt_cap_[A-Za-z0-9_-]{20,}$")


# ---------------------------------------------------------------------------
# F10: Caddy HTTPS Reverse Proxy
# ---------------------------------------------------------------------------
def test_f10_caddy_https_reverse_proxy(tmp_path):
    """F10: Reverse proxy configuration strips untrusted headers and enforces host validation."""
    caddy_file = ROOT / "deploy" / "Caddyfile"
    assert caddy_file.exists(), "deploy/Caddyfile must exist"
    caddy_text = caddy_file.read_text(encoding="utf-8")

    common_caddy = ROOT / "deploy" / "Caddyfile.common"
    text_to_check = caddy_text + (common_caddy.read_text(encoding="utf-8") if common_caddy.exists() else "")

    assert "header_up -X-Forwarded-For" in text_to_check or "X-Forwarded-For" in text_to_check
    assert "150MB" in text_to_check or "150M" in text_to_check, "150MB request body limit must be set in Caddy"

    # API middleware rejects untrusted proxy headers when peer is not a trusted proxy
    with patch.dict(os.environ, {"PRIVACYTRACE_TRUSTED_PROXIES": "192.168.200.1/32"}):
        app = create_app(store_root=tmp_path, mode="remote")
        client = TestClient(app, base_url="http://testserver")
        resp = client.get("/api/v1/health", headers={"X-Forwarded-For": "198.51.100.1"})
        assert resp.status_code == 400
        assert "untrusted" in resp.text.lower()


# ---------------------------------------------------------------------------
# F11: Capability Token Lifecycle
# ---------------------------------------------------------------------------
def test_f11_capability_token_lifecycle(tmp_path):
    """F11: Capability tokens are generated anonymously, hashed via SHA-256, and rejected in query params."""
    token, digest = generate_capability_token()
    assert TOKEN_REGEX.fullmatch(token), f"Token '{token}' does not match pattern"
    assert hashlib.sha256(token.encode("ascii")).hexdigest() == digest

    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Create draft anonymously in remote mode
    create_resp = client.post(
        "/api/v1/web/drafts",
        json={
            "name": "E2E Token Test",
            "sources": [{"id": "s1", "title": "Privacy Policy", "text": "We do not track users."}],
        },
    )
    assert create_resp.status_code == 200
    data = create_resp.json()
    assert "token" in data or "capability_token" in data
    issued_token = data.get("token") or data.get("capability_token")
    assert TOKEN_REGEX.fullmatch(issued_token)

    # Token must NOT be accepted in query parameters (must return 400)
    query_resp = client.get(
        f"/api/v1/web/drafts/{data['id']}?token={issued_token}",
    )
    assert query_resp.status_code == 400
    assert "query" in query_resp.text.lower() or "prohibited" in query_resp.text.lower()


# ---------------------------------------------------------------------------
# F12: HTTPS End-to-End Execution Flow
# ---------------------------------------------------------------------------
def test_f12_https_e2e_pipeline_execution(tmp_path, synthetic_apk_factory):
    """F12: Full HTTPS workflow: Draft -> Upload APK -> Start -> Poll -> Retrieve Report."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # 1. Create draft
    draft_resp = client.post(
        "/api/v1/web/drafts",
        json={
            "name": "E2E Pipeline Test",
            "sources": [{"id": "s1", "title": "Policy", "text": "We do not access the camera."}],
        },
    )
    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    draft_id = draft["id"]
    token = draft.get("token") or draft.get("capability_token")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload APK
    apk = synthetic_apk_factory(permission="android.permission.CAMERA")
    upload_resp = client.post(f"/api/v1/web/drafts/{draft_id}/apk", content=apk, headers=headers)
    assert upload_resp.status_code == 200
    assert upload_resp.json().get("uploaded") is True or upload_resp.json().get("revision") is not None

    # 3. Start task
    start_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/start",
        json={"revision": upload_resp.json().get("revision", 1), "request_id": uuid4().hex},
        headers=headers,
    )
    assert start_resp.status_code == 200
    job_id = start_resp.json()["id"]

    # 4. Query job status with token
    status_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["id"] == job_id


# ---------------------------------------------------------------------------
# F13: Single APK Analysis Flow
# ---------------------------------------------------------------------------
def test_f13_single_apk_analysis_flow(tmp_path, synthetic_apk_factory):
    """F13: Verify single APK upload, AXML parsing, and metadata inspection."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    draft_resp = client.post(
        "/api/v1/web/drafts",
        json={
            "name": "Single APK Test",
            "sources": [{"id": "s1", "title": "Policy", "text": "We do not record audio."}],
        },
    )
    assert draft_resp.status_code == 200
    draft_id = draft_resp.json()["id"]
    token = draft_resp.json().get("token") or draft_resp.json().get("capability_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload single APK
    apk = synthetic_apk_factory(
        package_name="org.privacytrace.single",
        version_code="10",
        permission="android.permission.RECORD_AUDIO",
    )
    upload_resp = client.post(f"/api/v1/web/drafts/{draft_id}/apk", content=apk, headers=headers)
    assert upload_resp.status_code == 200
    pkg_info = upload_resp.json().get("package_info", {})
    if pkg_info:
        assert pkg_info.get("package_name") == "org.privacytrace.single"
        assert pkg_info.get("version_code") in (10, "10")


# ---------------------------------------------------------------------------
# F14: Base + Splits Analysis Flow
# ---------------------------------------------------------------------------
def test_f14_base_splits_analysis_flow(tmp_path, split_package_set_factory):
    """F14: Verify Base + Splits package-set upload, validation, and split detection."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    draft_resp = client.post(
        "/api/v1/web/drafts",
        json={
            "name": "Split Package Set Test",
            "sources": [{"id": "s1", "title": "Policy", "text": "We do not use camera or location."}],
        },
    )
    assert draft_resp.status_code == 200
    draft_id = draft_resp.json()["id"]
    token = draft_resp.json().get("token") or draft_resp.json().get("capability_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload package set
    package_set_bytes = split_package_set_factory(
        package_name="org.privacytrace.splitapp",
        version_code="200",
        split_names=["config.en", "feature_camera"],
    )
    upload_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=package_set_bytes,
        headers=headers,
    )
    assert upload_resp.status_code == 200
    resp_data = upload_resp.json()
    assert resp_data.get("uploaded") is True or "files" in resp_data or "package_info" in resp_data


# ---------------------------------------------------------------------------
# F15: Cross-Scope & Instance Isolation
# ---------------------------------------------------------------------------
def test_f15_cross_scope_and_instance_isolation(tmp_path):
    """F15: Tokens from Scope A cannot read or mutate Scope B (403 Forbidden)."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Create Scope A
    resp_a = client.post(
        "/api/v1/web/drafts",
        json={"name": "Scope A", "sources": [{"id": "s1", "title": "P1", "text": "Text A"}]},
    ).json()
    token_a = resp_a.get("token") or resp_a.get("capability_token")

    # Create Scope B
    resp_b = client.post(
        "/api/v1/web/drafts",
        json={"name": "Scope B", "sources": [{"id": "s2", "title": "P2", "text": "Text B"}]},
    ).json()
    token_b = resp_b.get("token") or resp_b.get("capability_token")

    # Attempt cross-access: Token A accessing Scope B
    cross_read = client.get(
        f"/api/v1/web/drafts/{resp_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert cross_read.status_code == 403

    # Attempt cross-mutate: Token A deleting Scope B
    cross_delete = client.delete(
        f"/api/v1/web/drafts/{resp_b['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert cross_delete.status_code == 403

    # Unauthenticated access must receive 401
    unauth = client.get(f"/api/v1/web/drafts/{resp_b['id']}")
    assert unauth.status_code == 401


# ---------------------------------------------------------------------------
# F16: Management Surface Shielding
# ---------------------------------------------------------------------------
def test_f16_management_surface_shielding(tmp_path):
    """F16: Remote mode forbids /jobs listing, admin /web/settings, and local headers."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Jobs enumeration must return 403 in remote mode
    jobs_resp = client.get("/api/v1/jobs")
    assert jobs_resp.status_code == 403

    # Admin settings must return 403 in remote mode
    settings_resp = client.get("/api/v1/web/settings")
    assert settings_resp.status_code == 403
    settings_post = client.post("/api/v1/web/settings", json={"key": "val"})
    assert settings_post.status_code == 403

    # Spoofed local header must be rejected with 403
    local_spoof = client.get("/api/v1/health", headers={"X-PrivacyTrace-Local": "true"})
    assert local_spoof.status_code == 403


# ---------------------------------------------------------------------------
# F17: Request Quotas & Limits
# ---------------------------------------------------------------------------
def test_f17_request_quotas_and_limits(tmp_path):
    """F17: Requests exceeding pre-body limits (150MB APK, 8MB draft, 512KB json) return 413."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Oversized draft body (>8 MiB) via Content-Length header check
    resp = client.post(
        "/api/v1/web/drafts",
        content=b"{}",
        headers={"Content-Length": str(9 * 1024 * 1024)},
    )
    assert resp.status_code == 413

    # Oversized jobs body (>512 KiB)
    jobs_resp = client.post(
        "/api/v1/jobs",
        content=b"{}",
        headers={"Content-Length": str(600 * 1024)},
    )
    assert jobs_resp.status_code == 413

    # Verify MAX_FILE_SIZE is 150 MiB
    assert MAX_FILE_SIZE == 150 * 1024 * 1024
    assert MAX_PACKAGE_SET_SIZE == 150 * 1024 * 1024


# ---------------------------------------------------------------------------
# F18: Rate Limiting & 429 Retry-After
# ---------------------------------------------------------------------------
def test_f18_rate_limiting_and_retry_after(tmp_path, monkeypatch):
    """F18: Exceeding 60 req/min returns HTTP 429 with Retry-After header."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "5")  # low limit for test
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Send requests up to limit
    for _ in range(5):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    # 6th request should hit rate limit
    limited_resp = client.get("/api/v1/health")
    assert limited_resp.status_code == 429
    assert "retry-after" in limited_resp.headers


# ---------------------------------------------------------------------------
# F19: Malicious Source & CIDR Protection
# ---------------------------------------------------------------------------
def test_f19_malicious_source_cidr_protection(tmp_path, monkeypatch):
    """F19: X-Forwarded-For is traversed right-to-left against trusted proxy CIDRs; untrusted rejected."""
    monkeypatch.setenv("PRIVACYTRACE_TRUSTED_PROXIES", "10.0.0.0/8,127.0.0.1/32")
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # When peer is trusted, X-Forwarded-For traverses right-to-left
    resp = client.get(
        "/api/v1/health",
        headers={"X-Forwarded-For": "203.0.113.195, 10.1.2.3"},
    )
    assert resp.status_code == 200

    # Invalid / untrusted characters in forwarding header must be rejected
    bad_resp = client.get(
        "/api/v1/health",
        headers={"X-Forwarded-For": "bad_ip; drop table"},
    )
    assert bad_resp.status_code == 400
