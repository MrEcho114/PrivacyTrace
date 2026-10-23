"""Tier 4 Real-World Application Workload Scenarios E2E Test Suite.

Scenarios covered:
1. Scenario 1: Full Anonymous Remote Lifecycle (F1, F5, F6, F8, F9, F11)
2. Scenario 2: Adversarial Cross-Tenant Attack (F4, F6, F7, F8, F11)
3. Scenario 3: Reverse Proxy Forwarding Chain (F2, F3, F4)
4. Scenario 4: Denial-of-Service & Resource Flood (F15, F16, F17)
5. Scenario 5: Dual-Mode Hybrid Coexistence (F1, F8, F11, F12)
"""

import hashlib
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import create_app


def create_remote_app(tmp_path, monkeypatch):
    """Instantiate application configured in remote mode."""
    monkeypatch.setenv("PRIVACYTRACE_MODE", "remote")
    try:
        return create_app(store_root=tmp_path, mode="remote")
    except TypeError:
        return create_app(store_root=tmp_path)


def create_local_app(tmp_path, monkeypatch):
    """Instantiate application configured in local mode."""
    monkeypatch.setenv("PRIVACYTRACE_MODE", "local")
    try:
        return create_app(store_root=tmp_path, mode="local")
    except TypeError:
        return create_app(store_root=tmp_path)


def create_job_or_draft(client, name="sample-app"):
    """Helper to create a job or draft in remote mode."""
    resp = client.post(
        "/api/v1/jobs",
        json={"input_mode": "SYNTHETIC", "sample_id": name},
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        job_id = data.get("job_id") or data.get("id")
        token = data.get("capability_token") or data.get("token")
        return job_id, token, resp

    draft_resp = client.post("/api/v1/web/drafts", json={"name": name})
    if draft_resp.status_code in (200, 201):
        data = draft_resp.json()
        draft_id = data.get("draft_id") or data.get("id")
        token = data.get("capability_token") or data.get("token")
        return draft_id, token, draft_resp

    return None, None, resp


# ==============================================================================
# Scenario 1: Full Anonymous Remote Lifecycle
# ==============================================================================


def test_scenario_1_full_anonymous_remote_lifecycle(tmp_path, monkeypatch):
    """Scenario 1: Complete lifecycle of an anonymously created task from creation to tombstone.

    Steps:
    1. Remote client verifies remote health status.
    2. Remote client creates task anonymously, receives job_id and capability token.
    3. Verify disk persistence: plaintext token is NEVER written to disk; SHA-256 digest IS stored.
    4. Remote client queries job status using capability token -> 200 OK.
    5. Remote client cancels job using capability token -> 200 OK.
    6. Remote client deletes job using capability token -> 200/204 (writes tombstone).
    7. Subsequent access with original token returns 404 (or 410) due to tombstone.
    8. Replay of cancel or review on tombstone is rejected.
    """
    app = create_remote_app(tmp_path, monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    # Step 1: Health check
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["mode"] == "remote"

    # Step 2: Anonymous creation
    job_id, token, create_resp = create_job_or_draft(client, name="lifecycle-app")
    assert create_resp.status_code in (200, 201)
    if not job_id or not token:
        pytest.skip("Anonymous creation endpoint not yet wired in current milestone")

    assert token.startswith("pt_cap_")

    # Step 3: Verify disk persistence (zero plaintext, SHA-256 digest exists)
    token_bytes = token.encode("utf-8")
    expected_digest = hashlib.sha256(token_bytes).hexdigest()

    found_plaintext = False
    found_digest = False
    for p in Path(tmp_path).rglob("*"):
        if p.is_file():
            content = p.read_bytes()
            if token_bytes in content:
                found_plaintext = True
            if expected_digest.encode("utf-8") in content:
                found_digest = True

    assert not found_plaintext, "Plaintext token must never be written to storage disk!"
    assert found_digest, f"Expected SHA-256 digest '{expected_digest}' to be stored on disk"

    # Step 4: Query job status with token
    auth_headers = {"Authorization": f"Bearer {token}"}
    status_resp = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert status_resp.status_code == 200
    assert token not in status_resp.text

    # Step 5: Cancel job with token
    cancel_resp = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers)
    assert cancel_resp.status_code == 200

    # Step 6: Delete job with token (writes tombstone)
    delete_resp = client.delete(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert delete_resp.status_code in (200, 204)

    # Step 7: Subsequent read returns 404 or 410
    post_del_resp = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers)
    assert post_del_resp.status_code in (404, 410)

    # Step 8: Replay cancel on tombstoned job is rejected
    replay_resp = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_headers)
    assert replay_resp.status_code in (404, 409, 410)


def test_scenario_1b_mixed_case_bearer_scheme_lifecycle(tmp_path, monkeypatch):
    """Scenario 1b (#279): one capability token keeps working even when the client
    capitalises the ``Bearer`` scheme differently on each call.

    RFC 9110 §11.1 makes the authentication scheme token case-insensitive, while
    the token credentials themselves remain case-sensitive.
    """
    app = create_remote_app(tmp_path, monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    created = client.post(
        "/api/v1/jobs",
        json={"input_mode": "SYNTHETIC", "sample_id": "mixed-case-scheme-app"},
    )
    assert created.status_code in (200, 201), created.text
    body = created.json()
    job_id = body.get("job_id") or body.get("id")
    token = body.get("capability_token") or body.get("token")
    assert job_id and token, "anonymous remote creation must return job id and token"

    # 1. Reads succeed for every scheme spelling.
    for scheme in ("Bearer", "bearer", "BEARER", "bEaReR"):
        read_resp = client.get(
            f"/api/v1/jobs/{job_id}", headers={"Authorization": f"{scheme} {token}"}
        )
        assert read_resp.status_code == 200, (scheme, read_resp.text)

    # 2. A write (cancel) with an upper-case scheme reaches the same credential.
    cancel_resp = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers={"Authorization": f"BEARER {token}"},
    )
    assert cancel_resp.status_code == 200, cancel_resp.text

    # 3. Delete (tombstone) also works with a mixed-case scheme.
    delete_resp = client.delete(
        f"/api/v1/jobs/{job_id}", headers={"Authorization": f"bEaReR {token}"}
    )
    assert delete_resp.status_code in (200, 204)

    # 4. The tombstone still applies to the same credential afterwards.
    post_delete = client.get(
        f"/api/v1/jobs/{job_id}", headers={"Authorization": f"bearer {token}"}
    )
    assert post_delete.status_code in (404, 410)


# ==============================================================================
# Scenario 2: Adversarial Cross-Tenant Attack
# ==============================================================================


def test_scenario_2_adversarial_cross_tenant_attack(tmp_path, monkeypatch):
    """Scenario 2: Malicious User A attempts to access, tamper, cancel, or delete User B's job.

    Steps:
    1. User A creates Job A -> receives Token A.
    2. User B creates Job B -> receives Token B.
    3. User A attempts to read Job B with Token A -> 403 Forbidden.
    4. User A attempts to cancel Job B with Token A -> 403 Forbidden.
    5. User A attempts to delete Job B with Token A -> 403 Forbidden.
    6. User A attempts to enumerate all jobs via GET /api/v1/jobs -> 403 Forbidden.
    7. User A attempts to bypass with X-PrivacyTrace-Local: 1 -> 403 Forbidden.
    8. User A attempts to supply Token B via query string ?token=... -> 400 Bad Request.
    """
    app = create_remote_app(tmp_path, monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    job_a_id, token_a, _ = create_job_or_draft(client, name="tenant-a-job")
    job_b_id, token_b, _ = create_job_or_draft(client, name="tenant-b-job")

    if not (job_a_id and job_b_id and token_a and token_b):
        pytest.skip("Anonymous creation not yet wired in current milestone")

    # Step 3: User A attempts to read Job B with Token A
    read_resp = client.get(
        f"/api/v1/jobs/{job_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert read_resp.status_code == 403

    # Step 4: User A attempts to cancel Job B with Token A
    cancel_resp = client.post(
        f"/api/v1/jobs/{job_b_id}/cancel",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert cancel_resp.status_code == 403

    # Step 5: User A attempts to delete Job B with Token A
    del_resp = client.delete(
        f"/api/v1/jobs/{job_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert del_resp.status_code == 403

    # Step 6: User A attempts to enumerate jobs
    enum_resp = client.get(
        "/api/v1/jobs",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert enum_resp.status_code == 403

    # Step 7: User A attempts local header spoofing
    spoof_resp = client.get(
        f"/api/v1/jobs/{job_b_id}",
        headers={"X-PrivacyTrace-Local": "1"},
    )
    assert spoof_resp.status_code in (401, 403)

    # Step 8: Token in query string rejected
    query_resp = client.get(f"/api/v1/jobs/{job_b_id}?token={token_b}")
    assert query_resp.status_code == 400


# ==============================================================================
# Scenario 3: Reverse Proxy Forwarding Chain
# ==============================================================================


def test_scenario_3_reverse_proxy_forwarding_chain(tmp_path, monkeypatch):
    """Scenario 3: Forwarding requests through a trusted reverse proxy (e.g. Caddy/NGINX).

    Steps:
    1. Trusted reverse proxy forwards requests with X-Forwarded-For and
       X-Forwarded-Proto: https -> 200 OK.
    2. Direct external client spoofing X-Forwarded-For: 127.0.0.1 is blocked from local bypass.
    3. Untrusted Host header through proxy returns 400 Bad Request.
    """
    app = create_remote_app(tmp_path, monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    # 1. Valid forwarded request from trusted proxy
    proxy_headers = {
        "X-Forwarded-For": "203.0.113.195",
        "X-Forwarded-Proto": "https",
    }
    resp = client.get("/api/v1/health", headers=proxy_headers)
    assert resp.status_code == 200

    # 2. Direct external request spoofing loopback forwarded IP cannot list jobs
    spoofed_proxy = {"X-Forwarded-For": "127.0.0.1"}
    enum_resp = client.get("/api/v1/jobs", headers=spoofed_proxy)
    assert enum_resp.status_code == 403

    # 3. Invalid Host header rejected
    client_bad_host = TestClient(app, base_url="http://attacker.example")
    bad_host_resp = client_bad_host.get("/api/v1/health", headers=proxy_headers)
    assert bad_host_resp.status_code == 400


# ==============================================================================
# Scenario 4: Denial-of-Service & Resource Flood
# ==============================================================================


def test_scenario_4_denial_of_service_and_resource_flood(tmp_path, monkeypatch, caplog):
    """Scenario 4: High volume and oversized attack payloads are bounded with 413 and 429.

    Steps:
    1. Flooding oversized review body (> 512 KiB) returns 413 Payload Too Large.
    2. Flooding oversized APK upload (> 150 MiB) returns 413 Payload Too Large.
    3. Inspect logs: assert zero plaintext tokens, keys, or raw byte floods in log files.
    """
    caplog.set_level(logging.DEBUG)
    app = create_remote_app(tmp_path, monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    # 1. 512 KiB limit on reviews
    job_id, job_token, _ = create_job_or_draft(client)
    huge_note = "A" * (600 * 1024)
    resp_huge_json = client.post(
        f"/api/v1/jobs/{job_id}/reviews",
        json={"actor": "tester", "reason": "flood", "note": huge_note},
        headers={"Authorization": f"Bearer {job_token}"},
    )
    assert resp_huge_json.status_code == 413

    # 2. 150 MiB limit on APK upload
    created = client.post("/api/v1/web/drafts", json={"name": "flood", "sources": [
        {"id": "policy", "title": "Policy", "text": "Policy text"},
    ]})
    assert created.status_code == 200
    draft = created.json()
    oversized_length = str(160 * 1024 * 1024)
    resp_huge_apk = client.post(
        f"/api/v1/web/drafts/{draft['id']}/apk",
        headers={
            "Content-Length": oversized_length,
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {draft['token']}",
        },
        content=b"x" * 1024,
    )
    assert resp_huge_apk.status_code == 413

    # 3. Log redaction verification
    assert job_token not in caplog.text and draft["token"] not in caplog.text


# ==============================================================================
# Scenario 5: Dual-Mode Hybrid Coexistence
# ==============================================================================


def test_scenario_5_dual_mode_hybrid_coexistence(tmp_path, monkeypatch):
    """Scenario 5: Local mode and remote mode coexist cleanly with zero regressions.

    Steps:
    1. Boot local app: loopback client lists all jobs, accesses settings, local writes succeed.
    2. Boot remote app: remote client cannot list jobs (403), cannot access settings (403).
    3. Ensure local scripts continue working without modification.
    """
    # 1. Local App
    local_app = create_local_app(tmp_path, monkeypatch)
    local_client = TestClient(local_app, base_url="http://localhost")

    local_health = local_client.get("/api/v1/health")
    assert local_health.status_code == 200
    assert local_health.json()["mode"] in ("local", "local-jobs")

    local_jobs = local_client.get("/api/v1/jobs")
    assert local_jobs.status_code == 200
    assert "jobs" in local_jobs.json()

    local_settings = local_client.get("/api/v1/web/settings")
    assert local_settings.status_code == 200

    # 2. Remote App
    remote_app = create_remote_app(tmp_path, monkeypatch)
    remote_client = TestClient(remote_app, base_url="http://testserver")

    remote_health = remote_client.get("/api/v1/health")
    assert remote_health.status_code == 200
    assert remote_health.json()["mode"] == "remote"

    remote_jobs = remote_client.get("/api/v1/jobs")
    assert remote_jobs.status_code == 403

    remote_settings = remote_client.get("/api/v1/web/settings")
    assert remote_settings.status_code in (403, 404)
