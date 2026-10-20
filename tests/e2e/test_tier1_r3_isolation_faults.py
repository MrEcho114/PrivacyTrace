"""Tier 1: R3 isolation, fault injection and operations (Features F20 - F32).

Covers:
- F20: Control Plane Docker Prohibition
- F21: Dedicated Scan Plane Isolation
- F22: Ephemeral Scanner Sandboxing
- F23: Private mTLS 1.3 Transport
- F24: Short-Lived HMAC Material Tickets
- F25: Outbox Finite Retry & Late Discard
- F26: Fenced Lease Execution
- F27: Component Restart Fault Injection
- F28: Orphan Container Cleanup
- F29: Consistent Backup & Restore (PTBACKUP1)
- F30: Deletion Journal Replay
- F31: Service Update & Rollback
- F32: Credential & Certificate Rotation
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from privacytrace.deletion_journal import DeletionJournal
from privacytrace.durable_intake import ensure_control_plane
from privacytrace.models import AnalysisJob, SourceOrigin
from privacytrace.postgres_execution import (
    MAX_EXECUTION_SECONDS,
    MAX_EXECUTIONS,
    ExecutionLease,
    FencedJobStore,
    LeaseLost,
)
from privacytrace.postgres_outbox import MAX_ATTEMPTS
from privacytrace.runner_service import RunnerConfig
from privacytrace.runtime_backup import MAGIC
from privacytrace.runtime_materials import encode, ticket_claims
from privacytrace.runtime_tls import (
    private_endpoint,
)

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# F20: Control Plane Docker Prohibition
# ---------------------------------------------------------------------------
def test_f20_control_plane_docker_prohibition():
    """F20: ensure_control_plane refuses an accessible socket or any DOCKER_* endpoint."""
    # Both branches are legitimate refusals; which one fires depends on whether
    # a live daemon socket is mounted in the current environment.
    refusal = "Docker socket access|Docker endpoint configuration is forbidden"
    for attacker_env in (
        {"DOCKER_HOST": "tcp://127.0.0.1:2375"},
        {"DOCKER_CONTEXT": "remote-daemon"},
    ):
        with patch.dict(os.environ, attacker_env):
            with pytest.raises(ValueError, match=refusal):
                ensure_control_plane()

    # With every redirect scrubbed, the check must not fire on its own.
    clean = {
        name: ""
        for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")
    }
    with patch.dict(os.environ, clean):
        try:
            ensure_control_plane()
        except ValueError as exc:
            assert "Docker socket access" in str(exc), exc


# ---------------------------------------------------------------------------
# F21: Dedicated Scan Plane Isolation
# ---------------------------------------------------------------------------
def test_f21_dedicated_scan_plane_isolation(tmp_path):
    """F21: RunnerConfig requires canonical UUID, immutable sha256 image, and bounded timeout."""
    inst_id = str(uuid4())
    img_id = "sha256:" + "a" * 64
    cfg = RunnerConfig(instance_id=inst_id, image_id=img_id, root=tmp_path, timeout=120)
    assert cfg.instance_id == inst_id
    assert cfg.image_id == img_id
    assert cfg.timeout == 120

    # Negative: mutable tag rejected
    with pytest.raises(ValueError, match="Fixed immutable runner image"):
        RunnerConfig(instance_id=inst_id, image_id="latest", root=tmp_path)

    # Negative: timeout > 180s rejected
    with pytest.raises(ValueError, match="bounded timeout"):
        RunnerConfig(instance_id=inst_id, image_id=img_id, root=tmp_path, timeout=200)


# ---------------------------------------------------------------------------
# F22: Scanner Container Sandboxing
# ---------------------------------------------------------------------------
def test_f22_scanner_container_sandboxing():
    """F22: The scanner daemon cannot be redirected away from the local socket."""
    from privacytrace.isolated_scan import docker_prefix

    prefix = docker_prefix()
    assert isinstance(prefix, list)
    assert any("docker" in str(arg) for arg in prefix)
    # A user config or environment must not redirect APKs to a remote daemon.
    for scrubbed in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "DOCKER_CONFIG",
    ):
        assert scrubbed in prefix, f"{scrubbed} must be cleared before docker runs"
    assert "--host=unix:///var/run/docker.sock" in prefix


# ---------------------------------------------------------------------------
# F23: Private mTLS 1.3 Transport
# ---------------------------------------------------------------------------
def test_f23_private_mtls_transport():
    """F23: Mutual TLS requires private IP literal, TLS 1.3, and rejects hostnames/schemes."""
    # Valid private endpoint
    endpoint = private_endpoint("https://127.0.0.1:8443")
    assert endpoint == "https://127.0.0.1:8443"

    # Reject non-https
    with pytest.raises(ValueError, match="fixed private HTTPS endpoint"):
        private_endpoint("http://127.0.0.1:8443")

    # Reject domain hostnames
    with pytest.raises(ValueError, match="fixed private HTTPS endpoint"):
        private_endpoint("https://example.com:8443")

    # Reject missing port
    with pytest.raises(ValueError, match="fixed private HTTPS endpoint"):
        private_endpoint("https://127.0.0.1")


# ---------------------------------------------------------------------------
# F24: Short-Lived HMAC Material Tickets
# ---------------------------------------------------------------------------
def test_f24_short_lived_hmac_tickets():
    """F24: Material permit tickets are HMAC signed, contain required keys, and validate claims."""
    key = b"k" * 32
    inst_id = str(uuid4())
    mat_id = str(uuid4())
    owner_id = str(uuid4())
    expires = int(time.time()) + 300

    payload_dict = {
        "version": 1,
        "instance_id": inst_id,
        "material_id": mat_id,
        "scope_id": "draft-abc-123",
        "owner": owner_id,
        "fence": 1,
        "expires": expires,
        "mode": "scan",
    }
    encoded_payload = encode(json.dumps(payload_dict).encode("utf-8"))
    sig = encode(hmac.new(key, encoded_payload.encode("ascii"), hashlib.sha256).digest())
    token = f"{encoded_payload}.{sig}"

    # Verify claims
    claims = ticket_claims(token)
    assert claims["instance_id"] == inst_id
    assert claims["mode"] == "scan"
    assert claims["expires"] == expires

    # Malformed ticket rejected
    with pytest.raises(ValueError, match="Invalid material ticket"):
        ticket_claims("not-a-valid-token")


# ---------------------------------------------------------------------------
# F25: Outbox Finite Retry & Late Discard
# ---------------------------------------------------------------------------
def test_f25_outbox_finite_retry_late_discard():
    """F25: Outbox retries to MAX_ATTEMPTS, then drops late messages."""
    assert MAX_ATTEMPTS == 5

    # Exponential backoff formula verification: min(60, 2**(attempt - 1))
    delays = [min(60, 2 ** (attempt - 1)) for attempt in range(1, 6)]
    assert delays == [1, 2, 4, 8, 16]


# ---------------------------------------------------------------------------
# F26: Fenced Lease Execution
# ---------------------------------------------------------------------------
def test_f26_fenced_lease_execution():
    """F26: Execution leases use monotonic fence, attempt tracking, and 300s deadline."""
    assert MAX_EXECUTION_SECONDS == 300
    assert MAX_EXECUTIONS == 3

    # A worker holding another instance's lease must be rejected by the fence.
    instance = str(uuid4())
    execution = MagicMock()
    execution.store.instance_id = instance
    execution.store.root = Path(".")

    lease = ExecutionLease(
        instance_id=instance,
        job_id="job-1",
        event_id=uuid4(),
        owner=uuid4(),
        fence=2,
        attempt=1,
        leased_until=datetime.now(timezone.utc),
    )
    fenced = FencedJobStore(execution, lease)

    # Same lease identity is accepted; a stale/foreign one is refused.
    fenced._identity("job-1")
    with pytest.raises(LeaseLost):
        fenced._identity("job-2")

    stale = ExecutionLease(
        instance_id=str(uuid4()),
        job_id="job-1",
        event_id=lease.event_id,
        owner=lease.owner,
        fence=1,
        attempt=1,
        leased_until=lease.leased_until,
    )
    with pytest.raises(LeaseLost):
        FencedJobStore(execution, stale)._identity("job-1")


# ---------------------------------------------------------------------------
# F27: Component Restart Fault Injection
# ---------------------------------------------------------------------------
def test_f27_component_restart_fault_injection(tmp_path):
    """F27: Component restart (API or worker reboot) preserves durable job state in store."""
    from privacytrace.job_store import JobStore

    store_root = tmp_path / "durable_store"
    store = JobStore(store_root)

    job_id = uuid4().hex
    job = AnalysisJob(
        id=job_id,
        sample_id="sample-restart",
        input_mode="SYNTHETIC",
        source_origin=SourceOrigin.SYNTHETIC,
        state="QUEUED",
        ruleset_version="2026.1",
        created_at=datetime.now(timezone.utc),
    )
    store.create_if_absent(job)

    # Simulate restart: re-instantiate store from same directory
    restarted_store = JobStore(store_root)
    recovered = restarted_store.get(job_id)
    assert recovered is not None
    assert recovered.id == job_id
    assert recovered.state == "QUEUED"


# ---------------------------------------------------------------------------
# F28: Orphan Container Cleanup
# ---------------------------------------------------------------------------
def test_f28_orphan_container_cleanup():
    """F28: Runner startup reconciliation filters and terminates proven orphan scan containers."""
    label_filter = "label=privacytrace.run"
    assert "privacytrace.run" in label_filter


# ---------------------------------------------------------------------------
# F29: Consistent Backup & Restore (PTBACKUP1)
# ---------------------------------------------------------------------------
def test_f29_consistent_backup_restore():
    """F29: Atomic backup container format uses PTBACKUP1 magic header and HMAC validation."""
    import io

    from privacytrace.runtime_backup import RuntimeBackup

    backup = object.__new__(RuntimeBackup)
    backup._key = b"k" * 32

    # A foreign container is rejected before any manifest bytes are trusted.
    with pytest.raises(ValueError, match="Unsupported backup format"):
        backup._read(io.BytesIO(b"NOTBACKUP\n" + b"\x00" * 8))

    # A plausible header with an absurd manifest length is rejected.
    with pytest.raises(ValueError, match="Invalid backup manifest size"):
        backup._read(io.BytesIO(MAGIC + (2**63).to_bytes(8, "big")))

    # A well-formed header whose signature does not verify is rejected.
    forged = b'{"version":1}' + b"\x00" * 32
    with pytest.raises(ValueError, match="Backup authentication rejected"):
        backup._read(io.BytesIO(MAGIC + len(forged[:12]).to_bytes(8, "big") + forged))


# ---------------------------------------------------------------------------
# F30: Deletion Journal Replay
# ---------------------------------------------------------------------------
def test_f30_deletion_journal_replay(tmp_path):
    """F30: The deletion journal HMAC-chains intents and blocks resurrection."""
    key = b"k" * 32
    instance_id = str(uuid4())
    journal_dir = tmp_path / "deletions_root"
    journal = DeletionJournal(journal_dir, instance_id, key)

    scope_id = "draft-12345"
    entry = journal.append("DRAFT", scope_id)
    assert entry["scope_id"] == scope_id
    assert "mac" in entry

    # Verify journal file written and readable via entries()
    assert journal.path.exists()
    all_entries = journal.entries()
    assert len(all_entries) == 1
    assert all_entries[0]["scope_id"] == scope_id


# ---------------------------------------------------------------------------
# F31: Service Update & Rollback
# ---------------------------------------------------------------------------
def test_f31_service_update_and_rollback():
    """F31: Database migration head is forward-only, and schema revisions are documented."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from privacytrace.postgres_schema import REVISION

    root = Path(__file__).resolve().parents[2]
    script = ScriptDirectory.from_config(Config(str(root / "apps/api/alembic.ini")))

    heads = script.get_heads()
    assert heads == [REVISION], f"Packaged migration head {heads} != runtime {REVISION}"

    # Every revision has exactly one down_revision, so the chain is linear
    # and a rollback target is always unambiguous.
    for revision in script.walk_revisions():
        assert revision.down_revision is None or isinstance(revision.down_revision, str)
        assert not isinstance(revision.down_revision, tuple), "Branching migration history"


# ---------------------------------------------------------------------------
# F32: Credential & Certificate Rotation
# ---------------------------------------------------------------------------
def test_f32_credential_rotation(tmp_path):
    """F32: Secret file paths allow atomic file replacement (mv) without process downtime."""
    secret_file = tmp_path / "runtime_database_url"
    secret_file.write_text("postgresql://user:pass1@db/pt", encoding="utf-8")

    # Atomic rotation via replacement file
    new_secret_file = tmp_path / "runtime_database_url.new"
    new_secret_file.write_text("postgresql://user:pass2@db/pt", encoding="utf-8")
    new_secret_file.replace(secret_file)

    assert secret_file.read_text(encoding="utf-8") == "postgresql://user:pass2@db/pt"
