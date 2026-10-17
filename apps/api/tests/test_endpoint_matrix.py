"""Opaque-box E2E test suite for Endpoint Access Control Matrix & Admin Isolation (R3).

Requirements covered:
- Feature 11: Global Enumeration Prohibition (Tiers 1-3)
- Feature 12: Instance Config & Model Key Isolation (Tiers 1-3)
- Feature 13: Public Read-Only Transparency Endpoints (Tiers 1-3)
- Feature 14: Consistency Evaluation Guard (Tiers 1-3)
"""

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import create_app
from privacytrace.resources import read_json


def get_app(tmp_path, mode="local", monkeypatch=None):
    """Instantiate application in local or remote mode."""
    if monkeypatch:
        monkeypatch.setenv("PRIVACYTRACE_MODE", mode)
    try:
        return create_app(store_root=tmp_path, mode=mode)
    except TypeError:
        return create_app(store_root=tmp_path)


# ==============================================================================
# Feature 11: Global Enumeration Prohibition (Tiers 1-3)
# ==============================================================================


def test_remote_get_jobs_list_forbidden(tmp_path, monkeypatch):
    """Tier 1: In remote mode, GET /api/v1/jobs returns 403 Forbidden."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 403


def test_remote_get_jobs_list_with_token_still_forbidden(tmp_path, monkeypatch):
    """Tier 1: Even with a valid individual capability token, GET /api/v1/jobs returns 403."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    headers = {"Authorization": "Bearer pt_cap_valid_looking_token_12345"}
    resp = client.get("/api/v1/jobs", headers=headers)
    assert resp.status_code == 403


def test_remote_get_jobs_list_with_spoofed_local_header_forbidden(tmp_path, monkeypatch):
    """Tier 2: Spoofed X-PrivacyTrace-Local: 1 cannot bypass enumeration prohibition."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get("/api/v1/jobs", headers={"X-PrivacyTrace-Local": "1"})
    assert resp.status_code == 403


def test_local_get_jobs_list_allowed(tmp_path, monkeypatch):
    """Tier 1: In local mode, GET /api/v1/jobs returns 200 OK with jobs list."""
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert "jobs" in resp.json()


# ==============================================================================
# Feature 12: Instance Config & Model Key Isolation (Tiers 1-3)
# ==============================================================================


def test_remote_get_web_settings_forbidden(tmp_path, monkeypatch):
    """Tier 1: In remote mode, GET /api/v1/web/settings returns 403 Forbidden."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.get("/api/v1/web/settings")
    assert resp.status_code in (403, 404)


def test_remote_post_web_settings_forbidden(tmp_path, monkeypatch):
    """Tier 1: In remote mode, POST /api/v1/web/settings returns 403 Forbidden."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.post(
        "/api/v1/web/settings",
        json={"enabled": True, "api_base": "http://evil.com", "model": "gpt-4"},
    )
    assert resp.status_code in (403, 404)


def test_remote_post_web_settings_with_user_key_rejected(tmp_path, monkeypatch):
    """Tier 2: Remote user attempting to submit personal API key is blocked."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.post(
        "/api/v1/web/settings",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"api_key": "sk-user-secret-key-12345", "enabled": True},
    )
    assert resp.status_code in (403, 404)


@pytest.mark.parametrize(
    "headers,query",
    [
        ({"X-Admin": "1"}, ""),
        ({"X-Role": "admin"}, ""),
        ({"X-Remote-User": "admin"}, ""),
        ({"Authorization": "Basic YWRtaW46YWRtaW4="}, ""),
        ({"Authorization": "Bearer admin_master_token"}, ""),
        ({"X-PrivacyTrace-Local": "1"}, ""),
        ({"X-Forwarded-For": "127.0.0.1"}, ""),
        ({}, "?admin=true"),
        ({}, "?role=admin"),
        ({}, "?sudo=1"),
    ],
    ids=[
        "x-admin-header",
        "x-role-header",
        "x-remote-user-header",
        "basic-auth-admin",
        "bearer-admin-token",
        "local-header-spoof",
        "forwarded-for-loopback",
        "query-admin-param",
        "query-role-param",
        "query-sudo-param",
    ],
)
def test_remote_settings_spoofing_attempts_blocked(tmp_path, monkeypatch, headers, query):
    """Tier 2: Various admin spoofing headers and query parameters are blocked
    on /api/v1/web/settings.
    """
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    # GET request
    get_resp = client.get(f"/api/v1/web/settings{query}", headers=headers)
    assert get_resp.status_code == 403

    # POST request
    post_resp = client.post(
        f"/api/v1/web/settings{query}",
        headers=headers,
        json={"enabled": True},
    )
    assert post_resp.status_code == 403


def test_local_web_settings_accessible(tmp_path, monkeypatch):
    """Tier 1: In local mode, GET /api/v1/web/settings returns 200 and POST works
    with local header.
    """
    app = get_app(tmp_path, mode="local", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://localhost")
    get_resp = client.get("/api/v1/web/settings")
    assert get_resp.status_code == 200

    post_resp = client.post(
        "/api/v1/web/settings",
        headers={"X-PrivacyTrace-Local": "1", "Origin": "http://localhost:5173"},
        json={"enabled": False},
    )
    assert post_resp.status_code in (200, 409)


# ==============================================================================
# Feature 13: Public Read-Only Transparency Endpoints (Tiers 1-3)
# ==============================================================================


@pytest.mark.parametrize("mode", ["local", "remote"], ids=["local-mode", "remote-mode"])
def test_health_publicly_accessible_both_modes(tmp_path, monkeypatch, mode):
    """Tier 1: /api/v1/health is public and returns 200 OK in both local and remote modes."""
    app = get_app(tmp_path, mode=mode, monkeypatch=monkeypatch)
    host = "localhost" if mode == "local" else "testserver"
    client = TestClient(app, base_url=f"http://{host}")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.parametrize("mode", ["local", "remote"], ids=["local-mode", "remote-mode"])
def test_taxonomy_publicly_accessible_both_modes(tmp_path, monkeypatch, mode):
    """Tier 1: /api/v1/taxonomy is public and returns 200 OK in both modes."""
    app = get_app(tmp_path, mode=mode, monkeypatch=monkeypatch)
    host = "localhost" if mode == "local" else "testserver"
    client = TestClient(app, base_url=f"http://{host}")
    resp = client.get("/api/v1/taxonomy")
    assert resp.status_code == 200
    assert "categories" in resp.json() or "rules" in resp.json() or "api_mappings" in resp.json()


@pytest.mark.parametrize("mode", ["local", "remote"], ids=["local-mode", "remote-mode"])
def test_demo_report_publicly_accessible_both_modes(tmp_path, monkeypatch, mode):
    """Tier 1: /api/v1/demo/report is public and returns 200 OK with demo=True in both modes."""
    app = get_app(tmp_path, mode=mode, monkeypatch=monkeypatch)
    host = "localhost" if mode == "local" else "testserver"
    client = TestClient(app, base_url=f"http://{host}")
    resp = client.get("/api/v1/demo/report")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("demo") is True
    assert "result" in data


@pytest.mark.parametrize("mode", ["local", "remote"], ids=["local-mode", "remote-mode"])
def test_demo_evidence_publicly_accessible_both_modes(tmp_path, monkeypatch, mode):
    """Tier 2: /api/v1/demo/evidence/{id} returns 200 for valid ID and 404 for nonexistent ID."""
    app = get_app(tmp_path, mode=mode, monkeypatch=monkeypatch)
    host = "localhost" if mode == "local" else "testserver"
    client = TestClient(app, base_url=f"http://{host}")

    # Valid ID check from demo report
    demo_report = client.get("/api/v1/demo/report").json()
    valid_id = demo_report["evidence"][0]["id"]
    valid_resp = client.get(f"/api/v1/demo/evidence/{valid_id}")
    assert valid_resp.status_code == 200
    assert valid_resp.json()["id"] == valid_id

    # Nonexistent ID check
    invalid_resp = client.get("/api/v1/demo/evidence/nonexistent-evidence-id")
    assert invalid_resp.status_code == 404


# ==============================================================================
# Feature 14: Consistency Evaluation Guard (Tiers 1-3)
# ==============================================================================


@pytest.mark.parametrize("mode", ["local", "remote"], ids=["local-mode", "remote-mode"])
def test_consistency_evaluate_publicly_accessible(tmp_path, monkeypatch, mode):
    """Tier 1: POST /api/v1/consistency/evaluate evaluates synthetic bundles in both modes."""
    app = get_app(tmp_path, mode=mode, monkeypatch=monkeypatch)
    host = "localhost" if mode == "local" else "testserver"
    client = TestClient(app, base_url=f"http://{host}")

    bundle_dict = read_json("samples/demo/evaluation-input.json")
    resp = client.post("/api/v1/consistency/evaluate", json=bundle_dict)
    assert resp.status_code == 200
    data = resp.json()
    assert "issues" in data


@pytest.mark.parametrize("mode", ["local", "remote"], ids=["local-mode", "remote-mode"])
def test_consistency_evaluate_rejects_controlled_apk(tmp_path, monkeypatch, mode):
    """Tier 2: Rejects CONTROLLED_APK input with 422 in both modes."""
    app = get_app(tmp_path, mode=mode, monkeypatch=monkeypatch)
    host = "localhost" if mode == "local" else "testserver"
    client = TestClient(app, base_url=f"http://{host}")

    bundle_dict = read_json("samples/demo/evaluation-input.json")
    bundle_dict["job"]["input_mode"] = "CONTROLLED_APK"
    resp = client.post("/api/v1/consistency/evaluate", json=bundle_dict)
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {},
        {"job": {}},
        {"job": {"id": "j1"}, "evidence": "not-a-list"},
    ],
    ids=["empty-dict", "missing-fields", "wrong-types"],
)
def test_consistency_evaluate_rejects_invalid_schema(tmp_path, monkeypatch, invalid_payload):
    """Tier 2: Rejects malformed payload with 422 Unprocessable Entity."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    resp = client.post("/api/v1/consistency/evaluate", json=invalid_payload)
    assert resp.status_code == 422


# ==============================================================================
# Tier 3: Endpoint Access Matrix Combinatorial & Cross-Endpoint Verification
# ==============================================================================


@pytest.mark.parametrize(
    "path,method,expected_remote_status",
    [
        ("/api/v1/health", "GET", 200),
        ("/api/v1/taxonomy", "GET", 200),
        ("/api/v1/demo/report", "GET", 200),
        ("/api/v1/jobs", "GET", 403),
        ("/api/v1/web/settings", "GET", 403),
        ("/api/v1/jobs/target-job-id", "GET", 401),
        ("/api/v1/jobs/target-job-id/report", "GET", 401),
        ("/api/v1/jobs/target-job-id/cancel", "POST", 401),
        ("/api/v1/jobs/target-job-id", "DELETE", 401),
    ],
    ids=[
        "health-get",
        "taxonomy-get",
        "demo-report-get",
        "jobs-list-forbidden",
        "web-settings-forbidden",
        "job-detail-unauth",
        "job-report-unauth",
        "job-cancel-unauth",
        "job-delete-unauth",
    ],
)
def test_remote_mode_endpoint_matrix_unauthenticated(
    tmp_path, monkeypatch, path, method, expected_remote_status
):
    """Tier 3: Unauthenticated remote requests adhere strictly to the endpoint security matrix."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    if method == "GET":
        resp = client.get(path)
    elif method == "POST":
        resp = client.post(path)
    elif method == "DELETE":
        resp = client.delete(path)
    else:
        pytest.fail(f"Unsupported method: {method}")

    assert resp.status_code == expected_remote_status


def test_cross_endpoint_remote_workflow(tmp_path, monkeypatch):
    """Tier 3: Multi-step user journey verifying the entire endpoint matrix in sequence."""
    app = get_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    # Step 1: Probe unauthenticated enumeration -> blocked (403)
    assert client.get("/api/v1/jobs").status_code == 403

    # Step 2: Read transparency endpoints -> allowed (200)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/taxonomy").status_code == 200
    assert client.get("/api/v1/demo/report").status_code == 200

    # Step 3: Attempt admin settings -> blocked (403)
    assert client.get("/api/v1/web/settings").status_code == 403
    assert client.post("/api/v1/web/settings", json={"enabled": True}).status_code == 403

    # Step 4: Create job anonymously -> returns job_id and capability token
    create_resp = client.post(
        "/api/v1/jobs",
        json={"input_mode": "SYNTHETIC", "sample_id": "journey-sample"},
    )
    assert create_resp.status_code in (200, 201)
    data = create_resp.json()
    job_id = data["job_id"]
    token = data["capability_token"]

    # Step 5: Access own job with token -> 200 OK
    own_resp = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert own_resp.status_code == 200
    assert own_resp.json()["id"] == job_id

    # Step 6: Global enumeration /api/v1/jobs remains blocked even for token holder -> 403
    assert (
        client.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 403
    )
