"""Opaque-box E2E test suite for Scoped Capability Tokens & Auth Seam (R2).

Requirements covered:
- Feature 5: Anonymous Job / Draft Creation (Tiers 1-3)
- Feature 6: One-Way Token Digest Storage (Tiers 1-3)
- Feature 7: Zero Plaintext in Secondary Channels (Tiers 1-3)
- Feature 8: Job-Scoped Access Verification (Tiers 1-3)
- Feature 9: Revocation & Deletion Tombstone (Tiers 1-3)
- Feature 10: Storage/Auth Seam Contract (Tiers 1-3)
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from privacytrace.auth import SecuritySeam, generate_capability_token
from privacytrace.config import ServerConfig
from privacytrace.main import create_app
from privacytrace.models import AnalysisJob, EvaluationInput, SourceOrigin
from privacytrace.resources import read_json, taxonomy
from privacytrace.storage_seam import JobStorageProtocol


def get_remote_app(tmp_path, monkeypatch=None):
    """Instantiate application in remote mode."""
    if monkeypatch:
        monkeypatch.setenv("PRIVACYTRACE_MODE", "remote")
    try:
        return create_app(store_root=tmp_path, mode="remote")
    except TypeError:
        return create_app(store_root=tmp_path)


def controlled_bundle():
    """Build controlled contract facts bundle."""
    data = read_json("samples/demo/evaluation-input.json")
    synthetic_rules = {r["rule_id"] for r in taxonomy()["api_mappings"] if r.get("synthetic_only")}
    removed = {
        e["id"] for e in data["evidence"] if e.get("api_call", {}).get("rule_id") in synthetic_rules
    }
    data["evidence"] = [e for e in data["evidence"] if e["id"] not in removed]
    data["behaviors"] = [
        b for b in data["behaviors"] if not removed.intersection(b["evidence_ids"])
    ]
    data["job"]["input_mode"] = "APK"
    data["job"]["source_origin"] = "CONTROLLED"
    return EvaluationInput.model_validate(data)


def seed_job(store, token_digest=None):
    """Seed completed job with report into store, supporting token_digest if accepted."""
    bundle = controlled_bundle()
    metadata = dict(
        name="controlled APK contract fixture only",
        package_name="org.privacytrace.demo",
        version_name="1",
        version_code=1,
        apk_sha256="a" * 64,
        permissions=[],
        dex_entries=["classes.dex"],
    )
    coverage = dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[])
    tools = {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"}
    try:
        return store.save(bundle, metadata, coverage, tools, token_digest=token_digest)
    except TypeError:
        report = store.save(bundle, metadata, coverage, tools)
        if token_digest and hasattr(store, "set_token_digest"):
            store.set_token_digest(report.job.id, token_digest)
        return report


def create_remote_job_via_api(client, sample_id="sample-alpha"):
    """Helper to create a job anonymously in remote mode via API."""
    resp = client.post(
        "/api/v1/jobs",
        json={"input_mode": "SYNTHETIC", "sample_id": sample_id},
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        job_id = data.get("job_id") or data.get("id")
        token = data.get("capability_token") or data.get("token") or data.get("secret_token")
        return job_id, token, resp

    # Fallback to POST /api/v1/web/drafts
    draft_resp = client.post("/api/v1/web/drafts", json={"name": f"draft-{sample_id}"})
    if draft_resp.status_code in (200, 201):
        data = draft_resp.json()
        draft_id = data.get("draft_id") or data.get("id")
        token = data.get("capability_token") or data.get("token") or data.get("secret_token")
        return draft_id, token, draft_resp

    return None, None, resp


# ==============================================================================
# Feature 5: Anonymous Job / Draft Creation (Tiers 1-3)
# ==============================================================================


def test_anonymous_job_creation_returns_token(tmp_path, monkeypatch):
    """Tier 1: Anonymous remote client creates job/draft, receives capability token."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, resp = create_remote_job_via_api(client)

    assert resp.status_code in (200, 201)
    assert job_id is not None, "Expected job_id or id in creation response"
    assert token is not None, "Expected capability token in creation response"
    assert token.startswith("pt_cap_"), f"Token {token} should start with pt_cap_"


def test_capability_token_format_and_entropy(tmp_path, monkeypatch):
    """Tier 2: Token format pt_cap_<urlsafe_base64> with >= 32 characters entropy."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    _, token, _ = create_remote_job_via_api(client)

    if token:
        assert re.match(r"^pt_cap_[A-Za-z0-9_-]{20,}$", token), (
            f"Token '{token}' does not match expected urlsafe capability format"
        )
        assert len(token) >= 32, "Token should be sufficiently high entropy"


def test_consecutive_created_tokens_are_unique(tmp_path, monkeypatch):
    """Tier 2: Consecutively created jobs produce unique, unpredictable tokens."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    tokens = set()
    for i in range(5):
        _, token, _ = create_remote_job_via_api(client, sample_id=f"sample-{i}")
        if token:
            assert token not in tokens, f"Duplicate token detected: {token}"
            tokens.add(token)


def test_anonymous_creation_without_login_headers(tmp_path, monkeypatch):
    """Tier 1: Creation request does NOT require Authorization or Cookie headers."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, resp = create_remote_job_via_api(client)
    assert resp.status_code in (200, 201)


def test_remote_web_draft_creation_returns_token(tmp_path, monkeypatch):
    """Tier 1: Creating web draft in remote mode also returns capability token."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    resp = client.post(
        "/api/v1/web/drafts",
        json={
            "name": "draft-remote-test",
            "sources": [
                {
                    "id": "official-web",
                    "title": "Official Privacy Policy",
                    "source_type": "OFFICIAL_WEB_POLICY",
                }
            ],
        },
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    token = data.get("capability_token") or data.get("token") or data.get("secret_token")
    assert token is not None
    assert token.startswith("pt_cap_")


# ==============================================================================
# Feature 6: One-Way Token Digest Storage (Tiers 1-3)
# ==============================================================================


def test_plaintext_token_never_persisted_to_disk(tmp_path, monkeypatch):
    """Tier 1: Read raw disk bytes in tmp_path to verify plaintext token is NEVER stored."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if token:
        found_plaintext = False
        token_bytes = token.encode("utf-8")
        secret_part = token.replace("pt_cap_", "").encode("utf-8")

        for file_path in Path(tmp_path).rglob("*"):
            if file_path.is_file():
                raw_bytes = file_path.read_bytes()
                if token_bytes in raw_bytes or (len(secret_part) > 10 and secret_part in raw_bytes):
                    found_plaintext = True
                    break

        assert not found_plaintext, (
            f"SECURITY VIOLATION: Plaintext token '{token}' found in stored files!"
        )


def test_sha256_digest_is_stored_on_disk(tmp_path, monkeypatch):
    """Tier 1: The SHA-256 digest of the capability token IS stored on disk."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if token:
        expected_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        digest_bytes = expected_digest.encode("utf-8")

        found_digest = False
        for file_path in Path(tmp_path).rglob("*"):
            if file_path.is_file():
                raw_bytes = file_path.read_bytes()
                if digest_bytes in raw_bytes:
                    found_digest = True
                    break

        assert found_digest, f"Expected SHA-256 digest '{expected_digest}' to be persisted on disk."


def test_corrupted_digest_on_disk_invalidates_token(tmp_path, monkeypatch):
    """Tier 2: Corrupting the stored digest on disk invalidates access (returns 401/403/404)."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if token and job_id:
        expected_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for file_path in Path(tmp_path).rglob(f"*{job_id}*"):
            if file_path.is_file():
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if expected_digest in content:
                    corrupted = content.replace(expected_digest, "0" * 64)
                    file_path.write_text(corrupted, encoding="utf-8")
                    break

        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert resp.status_code in (401, 403, 404)


# ==============================================================================
# Feature 7: Zero Plaintext in Secondary Channels (Tiers 1-3)
# ==============================================================================


def test_plaintext_token_not_in_job_metadata_response(tmp_path, monkeypatch):
    """Tier 1: Querying job details never includes the plaintext token in the response."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if token and job_id:
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        if resp.status_code == 200:
            assert token not in resp.text
            assert "token" not in resp.json() or resp.json().get("token") is None


def test_token_in_url_query_param_strictly_prohibited(tmp_path, monkeypatch):
    """Tier 1: Passing token in query parameter (?token=... or ?capability_token=...)
    returns 400 Bad Request.
    """
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if token and job_id:
        resp = client.get(f"/api/v1/jobs/{job_id}?token={token}")
        assert resp.status_code == 400, (
            "Token passed in URL query param must be rejected with 400 Bad Request"
        )
        resp2 = client.get(f"/api/v1/jobs/{job_id}?capability_token={token}")
        assert resp2.status_code == 400, (
            "capability_token in URL query param must be rejected with 400 Bad Request"
        )


def test_zero_token_leakage_in_logging(tmp_path, monkeypatch, caplog):
    """Tier 1: Plaintext token is never logged by the application."""
    caplog.set_level(logging.DEBUG)
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if token and job_id:
        headers = {"Authorization": f"Bearer {token}"}
        client.get(f"/api/v1/jobs/{job_id}", headers=headers)

        secret_part = token.replace("pt_cap_", "")
        assert secret_part not in caplog.text, "Plaintext token was logged in application logs!"


def test_zero_token_leakage_in_error_responses(tmp_path, monkeypatch):
    """Tier 2: Error responses (401, 403, 404, 422) never echo the plaintext token."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    fake_token = "pt_cap_attacker_supplied_secret_12345"

    resp = client.get(
        "/api/v1/jobs/target-job",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert resp.status_code in (401, 403, 404)
    assert fake_token not in resp.text


# ==============================================================================
# Feature 8: Job-Scoped Access Verification (Tiers 1-3)
# ==============================================================================


def test_access_without_token_returns_401(tmp_path, monkeypatch):
    """Tier 1: Accessing remote job without capability token returns 401 Unauthorized."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, _, _ = create_remote_job_via_api(client)

    if job_id:
        resp = client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 401


def test_access_with_malformed_token_returns_401(tmp_path, monkeypatch):
    """Tier 2: Malformed or non-Bearer authorization header returns 401."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, _, _ = create_remote_job_via_api(client)

    if job_id:
        # Invalid prefix / malformed characters
        resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": "Bearer not_a_valid_token_format"},
        )
        assert resp.status_code in (401, 403)

        # Basic auth instead of Bearer
        resp_basic = client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp_basic.status_code in (401, 403)


def test_access_with_wrong_token_for_different_job_returns_403(tmp_path, monkeypatch):
    """Tier 1: Cross-task access: Using Token A to access Job B returns 403 Forbidden."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    job_a_id, token_a, _ = create_remote_job_via_api(client, sample_id="job-a")
    job_b_id, token_b, _ = create_remote_job_via_api(client, sample_id="job-b")

    if job_a_id and job_b_id and token_a and token_b:
        # User A attempts to access Job B with Token A -> 403
        resp = client.get(
            f"/api/v1/jobs/{job_b_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 403

        # User B attempts to access Job A with Token B -> 403
        resp_reverse = client.get(
            f"/api/v1/jobs/{job_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_reverse.status_code == 403


def test_access_with_valid_bearer_token_succeeds(tmp_path, monkeypatch):
    """Tier 1: Accessing job with matching capability token succeeds (200 OK)."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if job_id and token:
        resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


def test_access_with_custom_header_token_succeeds(tmp_path, monkeypatch):
    """Tier 1: Passing token via X-PrivacyTrace-Token header succeeds."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if job_id and token:
        resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"X-PrivacyTrace-Token": token},
        )
        assert resp.status_code == 200


def test_get_report_requires_valid_job_token(tmp_path, monkeypatch):
    """Tier 1: Accessing /api/v1/jobs/{job_id}/report requires valid capability token."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    token, digest = generate_capability_token()
    seeded = seed_job(app.state.job_store, token_digest=digest)
    job_id = seeded.job.id

    # 1. Missing token -> 401
    assert client.get(f"/api/v1/jobs/{job_id}/report").status_code == 401

    # 2. Cross-task token -> 403
    cross_token, _ = generate_capability_token()
    assert (
        client.get(
            f"/api/v1/jobs/{job_id}/report",
            headers={"Authorization": f"Bearer {cross_token}"},
        ).status_code
        == 403
    )

    # 3. Query param -> 400
    assert client.get(f"/api/v1/jobs/{job_id}/report?token={token}").status_code == 400

    # 4. Valid Bearer token -> 200
    resp_valid = client.get(
        f"/api/v1/jobs/{job_id}/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_valid.status_code == 200
    assert resp_valid.json()["job"]["id"] == job_id

    # 5. Valid X-PrivacyTrace-Token header -> 200
    resp_custom = client.get(
        f"/api/v1/jobs/{job_id}/report",
        headers={"X-PrivacyTrace-Token": token},
    )
    assert resp_custom.status_code == 200


def test_post_reviews_requires_valid_job_token(tmp_path, monkeypatch):
    """Tier 1: Reviewing a job via POST /api/v1/jobs/{job_id}/reviews requires valid
    capability token.
    """
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    token, digest = generate_capability_token()
    seeded = seed_job(app.state.job_store, token_digest=digest)
    job_id = seeded.job.id

    review_payload = {
        "actor": "auditor",
        "reason": "Security review test",
        "note": "Validated policy compliance",
    }

    # 1. Missing token -> 401
    assert client.post(f"/api/v1/jobs/{job_id}/reviews", json=review_payload).status_code == 401

    # 2. Cross-task token -> 403
    cross_token, _ = generate_capability_token()
    assert (
        client.post(
            f"/api/v1/jobs/{job_id}/reviews",
            headers={"Authorization": f"Bearer {cross_token}"},
            json=review_payload,
        ).status_code
        == 403
    )

    # 3. Token in query param -> 400
    assert (
        client.post(
            f"/api/v1/jobs/{job_id}/reviews?token={token}",
            json=review_payload,
        ).status_code
        == 400
    )

    # 4. Valid token -> 200
    resp_valid = client.post(
        f"/api/v1/jobs/{job_id}/reviews",
        headers={"Authorization": f"Bearer {token}"},
        json=review_payload,
    )
    assert resp_valid.status_code == 200
    assert len(resp_valid.json().get("reviews", [])) > 0


def test_access_to_nonexistent_job_with_token_returns_404(tmp_path, monkeypatch):
    """Tier 2: Requesting nonexistent job ID with valid token format returns 404 Not Found."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    fake_token = "pt_cap_" + "x" * 32
    resp = client.get(
        "/api/v1/jobs/nonexistent-uuid-12345",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert resp.status_code == 404


def test_post_cancel_requires_valid_job_token(tmp_path, monkeypatch):
    """Tier 1: Cancelling job requires valid job token in remote mode."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if job_id and token:
        # Without token -> 401
        assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 401

        # With cross-job token -> 403
        cross_token = "pt_cap_" + "z" * 32
        assert client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            headers={"Authorization": f"Bearer {cross_token}"},
        ).status_code in (401, 403)

        # With valid token -> 200 OK
        resp = client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


# ==============================================================================
# Feature 9: Revocation & Deletion Tombstone (Tiers 1-3)
# ==============================================================================


def test_delete_job_with_valid_token_creates_tombstone(tmp_path, monkeypatch):
    """Tier 1: DELETE /api/v1/jobs/{id} with valid token deletes job and records tombstone."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if job_id and token:
        resp = client.delete(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (200, 204)

        # Subsequent GET request with same token returns 404 Not Found (or 410 Gone)
        get_resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code in (404, 410)


def test_delete_without_token_returns_401(tmp_path, monkeypatch):
    """Tier 1: DELETE /api/v1/jobs/{id} without token returns 401 Unauthorized."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, _, _ = create_remote_job_via_api(client)

    if job_id:
        resp = client.delete(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 401


def test_delete_with_cross_job_token_returns_403(tmp_path, monkeypatch):
    """Tier 1: DELETE /api/v1/jobs/{id} with another job's token returns 403 Forbidden."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_a_id, _, _ = create_remote_job_via_api(client, sample_id="job-a")
    _, token_b, _ = create_remote_job_via_api(client, sample_id="job-b")

    if job_a_id and token_b:
        resp = client.delete(
            f"/api/v1/jobs/{job_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 403


def test_tombstoned_job_replayed_review_rejected(tmp_path, monkeypatch):
    """Tier 2: Replay of write or review operations against tombstoned job is rejected (404/410)."""
    app = get_remote_app(tmp_path, monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")
    job_id, token, _ = create_remote_job_via_api(client)

    if job_id and token:
        # Delete first
        client.delete(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Attempt to post a review or cancel
        resp = client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (404, 409, 410)


# ==============================================================================
# Feature 10: Storage / Auth Seam Contract (Tiers 1-3)
# ==============================================================================


def test_storage_seam_and_security_seam_interfaces(tmp_path):
    """Tier 1: JobStorageProtocol and SecuritySeam adhere to interface contracts."""
    app = create_app(store_root=tmp_path)
    store = app.state.job_store
    config = ServerConfig.from_env()
    seam = SecuritySeam(config, store)

    assert isinstance(store, JobStorageProtocol)
    assert hasattr(seam, "authorize_job_access")
    assert hasattr(seam, "authorize_jobs_listing")
    assert hasattr(seam, "authorize_admin_settings")


# ==============================================================================
# Tier 3: Pairwise Combinations (Mode x Auth Method x Operation)
# ==============================================================================


@pytest.mark.parametrize("mode", ["local", "remote"])
@pytest.mark.parametrize("has_token", [True, False])
def test_pairwise_mode_and_token_read_access(tmp_path, monkeypatch, mode, has_token):
    """Tier 3: Pairwise combination of mode (local/remote) and token presence for reads."""
    monkeypatch.setenv("PRIVACYTRACE_MODE", mode)
    app = create_app(store_root=tmp_path, mode=mode)
    base_url = "http://localhost" if mode == "local" else "http://testserver"
    client = TestClient(app, base_url=base_url)

    token, digest = generate_capability_token()
    job = AnalysisJob(
        id=str(uuid4()),
        sample_id="test-job",
        package_name="org.privacytrace.test",
        version_code=1,
        input_mode="SYNTHETIC",
        source_origin=SourceOrigin.SYNTHETIC,
        state="QUEUED",
        ruleset_version="1.0.0",
        created_at=datetime.now(timezone.utc),
    )
    app.state.job_store.create_if_absent(job, token_digest=digest)

    headers = {"Authorization": f"Bearer {token}"} if has_token else {}
    resp = client.get(f"/api/v1/jobs/{job.id}", headers=headers)

    if mode == "local":
        assert resp.status_code == 200
    else:
        if has_token:
            assert resp.status_code == 200
        else:
            assert resp.status_code == 401


@pytest.mark.parametrize("mode", ["local", "remote"])
def test_pairwise_mode_write_requirements(tmp_path, monkeypatch, mode):
    """Tier 3: In local mode, writes require X-PrivacyTrace-Local: 1.
    In remote mode, writes require capability token.
    """
    monkeypatch.setenv("PRIVACYTRACE_MODE", mode)
    app = create_app(store_root=tmp_path, mode=mode)
    base_url = "http://localhost" if mode == "local" else "http://testserver"
    client = TestClient(app, base_url=base_url)

    token, digest = generate_capability_token()
    job = AnalysisJob(
        id=str(uuid4()),
        sample_id="test-job-write",
        package_name="org.privacytrace.test",
        version_code=1,
        input_mode="SYNTHETIC",
        source_origin=SourceOrigin.SYNTHETIC,
        state="QUEUED",
        ruleset_version="1.0.0",
        created_at=datetime.now(timezone.utc),
    )
    app.state.job_store.create_if_absent(job, token_digest=digest)

    if mode == "local":
        resp_no_hdr = client.post(f"/api/v1/jobs/{job.id}/cancel")
        assert resp_no_hdr.status_code == 403

        resp_with_hdr = client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"X-PrivacyTrace-Local": "1"},
        )
        assert resp_with_hdr.status_code == 200
    else:
        resp_no_token = client.post(f"/api/v1/jobs/{job.id}/cancel")
        assert resp_no_token.status_code == 401

        resp_spoofed = client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"X-PrivacyTrace-Local": "1"},
        )
        assert resp_spoofed.status_code in (401, 403)

        resp_with_token = client.post(
            f"/api/v1/jobs/{job.id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_with_token.status_code == 200
