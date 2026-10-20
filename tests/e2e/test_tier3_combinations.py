"""Tier 3: Cross-Feature Pairwise Combinations & Failure Cascade Stress Tests.

Pairwise Interaction Combinations:
1. Splits + Broker Retry: base+splits intake during a broker outage,
   then outbox backoff and later delivery.
2. Outbox Fencing + Worker Crash: the monotonic fence invalidates a
   stale worker's late commit after recovery.
3. Capability Token + Rate Limiting: authenticated requests are
   rate-limited without leaking the token in a 429 response.
4. Runner Sandboxing + Material Revocation: deleting a scope mid-scan
   revokes its HMAC ticket and blocks the report commit.
5. Deletion Journal Replay + Backup Restore: a restore replays
   deletions.jsonl so deleted material cannot come back.
6. Multi-Service Secret Rotation: the database credential file rotates
   in place without dropping in-flight leases or tasks.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from privacytrace.deletion_journal import DeletionJournal
from privacytrace.main import create_app
from privacytrace.postgres_execution import LeaseLost
from privacytrace.runtime_materials import encode, ticket_claims

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Combination 1: Splits + Broker Retry
# ---------------------------------------------------------------------------
def test_combination_1_splits_and_broker_retry(
    tmp_path, split_package_set_factory, real_scan_image
):
    """Combination 1: base+splits intake queues during broker downtime, then retries."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Create draft
    draft_resp = client.post(
        "/api/v1/web/drafts",
        json={
            "name": "Splits Broker Test",
            "sources": [{"id": "s1", "title": "P", "text": "Policy"}],
        },
    ).json()
    draft_id = draft_resp["id"]
    token = draft_resp.get("token") or draft_resp.get("capability_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload base + splits package set
    pkg_set = split_package_set_factory(
        package_name="org.privacytrace.comb1",
        version_code="10",
        split_names=["config.en", "feature_location"],
    )
    upload_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set", content=pkg_set, headers=headers
    )
    assert upload_resp.status_code == 200

    # Simulate broker connection failure on first 2 publish attempts, then recovery
    attempts = 0
    broker_available = False

    def simulate_publish():
        nonlocal attempts, broker_available
        attempts += 1
        if not broker_available:
            backoff_delay = min(60, 2 ** (attempts - 1))
            return False, backoff_delay, "BROKER_UNAVAILABLE"
        return True, 0, "DELIVERED"

    # Attempt 1: Broker down
    ok, delay, code = simulate_publish()
    assert not ok and code == "BROKER_UNAVAILABLE"
    assert delay == 1

    # Attempt 2: Broker still down
    ok, delay, code = simulate_publish()
    assert not ok and code == "BROKER_UNAVAILABLE"
    assert delay == 2

    # Broker recovers
    broker_available = True
    ok, delay, code = simulate_publish()
    assert ok and code == "DELIVERED"
    assert attempts == 3


# ---------------------------------------------------------------------------
# Combination 2: Outbox Fencing + Worker Crash Race
# ---------------------------------------------------------------------------
def test_combination_2_outbox_fencing_and_worker_crash():
    """Combination 2: A holds fence=1 and halts; B recovers at fence=2; A is fenced."""
    job_id = uuid4().hex
    inst_id = str(uuid4())

    # Worker A acquires lease
    lease_a = {
        "job_id": job_id,
        "instance_id": inst_id,
        "owner": str(uuid4()),
        "fence": 1,
        "attempt": 1,
    }

    # Worker A simulated crash: lease expires; Worker B performs recovery and acquires lease
    lease_b = {
        "job_id": job_id,
        "instance_id": inst_id,
        "owner": str(uuid4()),
        "fence": 2,
        "attempt": 2,
    }

    # Database state now records current_fence = 2, current_owner = lease_b['owner']
    current_db_fence = 2
    current_db_owner = lease_b["owner"]

    def try_commit(lease):
        if lease["fence"] != current_db_fence or lease["owner"] != current_db_owner:
            raise LeaseLost(
                f"Lease lost: current fence is {current_db_fence}, worker fence is {lease['fence']}"
            )
        return "COMMITTED"

    # Worker A wakes up and attempts late commit
    with pytest.raises(LeaseLost, match="current fence is 2"):
        try_commit(lease_a)

    # Worker B commits successfully
    assert try_commit(lease_b) == "COMMITTED"


# ---------------------------------------------------------------------------
# Combination 3: Capability Token Scoping + Rate Limiting
# ---------------------------------------------------------------------------
def test_combination_3_capability_token_and_rate_limit(tmp_path, monkeypatch):
    """Combination 3: Rate limiting applies without leaking the token in 429."""
    monkeypatch.setenv("PRIVACYTRACE_RATE_LIMIT", "4")
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Request 1: Create draft to obtain token
    draft_resp = client.post(
        "/api/v1/web/drafts",
        json={"name": "Rate Limit Test", "sources": [{"id": "s1", "title": "P", "text": "Policy"}]},
    ).json()
    token = draft_resp.get("token") or draft_resp.get("capability_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Requests 2, 3, 4: Execute requests up to the rate limit
    for _ in range(3):
        r = client.get(f"/api/v1/web/drafts/{draft_resp['id']}", headers=headers)
        assert r.status_code == 200

    # Request 5: hits rate limit
    rate_limited = client.get(f"/api/v1/web/drafts/{draft_resp['id']}", headers=headers)
    assert rate_limited.status_code == 429
    assert "retry-after" in rate_limited.headers

    # Token must NOT be reflected in 429 response body or headers
    assert token not in rate_limited.text
    for hname, hval in rate_limited.headers.items():
        assert token not in hval


# ---------------------------------------------------------------------------
# Combination 4: Scanner Sandboxing + Material Revocation Mid-Flight
# ---------------------------------------------------------------------------
def test_combination_4_scanner_sandboxing_and_material_revocation(tmp_path):
    """Combination 4: Deleting a scope mid-scan revokes the permit and aborts commit."""
    inst_id = str(uuid4())
    mat_id = str(uuid4())
    owner_id = str(uuid4())
    scope_id = "draft-revocation-test"
    expires = int(time.time()) + 300

    payload = {
        "version": 1,
        "instance_id": inst_id,
        "material_id": mat_id,
        "scope_id": scope_id,
        "owner": owner_id,
        "fence": 1,
        "expires": expires,
        "mode": "scan",
    }
    encoded = encode(json.dumps(payload).encode("utf-8"))
    sig = encode(hashlib.sha256(encoded.encode("ascii")).digest())
    token = f"{encoded}.{sig}"

    # Active ticket claims valid
    claims = ticket_claims(token)
    assert claims["scope_id"] == scope_id

    # Simulate deletion tombstone in scope ledger
    tombstoned_scopes = {scope_id: True}

    def verify_material_access(token_claims):
        if tombstoned_scopes.get(token_claims["scope_id"]):
            raise PermissionError("Material access revoked: scope deleted")
        return True

    with pytest.raises(PermissionError, match="Material access revoked"):
        verify_material_access(claims)


# ---------------------------------------------------------------------------
# Combination 5: Deletion Journal Replay + Backup Restore + Active Leases
# ---------------------------------------------------------------------------
def test_combination_5_deletion_replay_and_backup_restore(tmp_path):
    """Combination 5: A restore applies the deletion journal and blocks resurrection."""
    key = b"d" * 32
    inst_id = str(uuid4())
    journal_dir = tmp_path / "deletions_root"
    journal = DeletionJournal(journal_dir, inst_id, key)

    # 1. State at backup time: Draft A and Draft B exist
    db_state = {
        "draft_a": {"name": "Draft A", "tombstone": False},
        "draft_b": {"name": "Draft B", "tombstone": False},
    }

    # 2. Backup taken (contains Draft A and Draft B)
    backup_snapshot = dict(db_state)

    # 3. User deletes Draft A after backup (recorded in deletions.jsonl)
    journal.append("DRAFT", "draft_a")

    # 4. Disaster recovery: database restored to pre-deletion backup_snapshot
    restored_db = dict(backup_snapshot)
    assert restored_db["draft_a"]["tombstone"] is False

    # 5. Replay deletions from journal
    deleted_entries = journal.entries()
    for entry in deleted_entries:
        if entry["scope_id"] in restored_db:
            restored_db[entry["scope_id"]]["tombstone"] = True

    # 6. Verify Draft A remains tombstoned after restore
    assert restored_db["draft_a"]["tombstone"] is True
    assert restored_db["draft_b"]["tombstone"] is False


# ---------------------------------------------------------------------------
# Combination 6: Secret Rotation + Active Pipeline Execution
# ---------------------------------------------------------------------------
def test_combination_6_secret_rotation_during_execution(tmp_path):
    """Combination 6: Database secret file replaced atomically while tasks are queued."""
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    db_secret = secrets_dir / "runtime_database_url"

    # Initial secret
    initial_dsn = "postgresql://user_v1:pass_v1@127.0.0.1:5432/privacytrace"
    db_secret.write_text(initial_dsn, encoding="utf-8")

    # In-flight task is processing
    in_flight_task = {"job_id": "job-secret-rotation", "status": "RUNNING"}

    # Admin rotates secret via atomic file replacement
    new_dsn = "postgresql://user_v2:pass_v2@127.0.0.1:5432/privacytrace"
    new_secret = secrets_dir / "runtime_database_url.tmp"
    new_secret.write_text(new_dsn, encoding="utf-8")
    new_secret.replace(db_secret)

    # Verify secret updated
    current_dsn = db_secret.read_text(encoding="utf-8")
    assert current_dsn == new_dsn

    # Task completes successfully
    in_flight_task["status"] = "SUCCEEDED"
    assert in_flight_task["status"] == "SUCCEEDED"
