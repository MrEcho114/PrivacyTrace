"""Real PostgreSQL manifests and real mTLS material transfer; no APK analysis claimed."""

import hashlib
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import queued
from test_postgres_storage import store as store
from test_runtime_tls import serving
from test_runtime_tls import tls_materials as tls_materials

from privacytrace.material_gateway import create_gateway
from privacytrace.postgres_execution import PostgresExecution
from privacytrace.postgres_intake import PostgresWebIntake
from privacytrace.postgres_outbox import PostgresOutbox
from privacytrace.postgres_schema import runner_materials, runtime_inputs
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.runtime_materials import RuntimeMaterials, decode, encode, ticket_claims
from privacytrace.runtime_tls import PrivateClient
from privacytrace.web_models import DraftInput


@pytest.fixture
def materials(store, tmp_path):
    intake = PostgresWebIntake(store)
    draft = intake.create(
        DraftInput(name="synthetic bytes only", sources=[{"id": "s", "title": "test"}]), "a" * 64
    )
    path = intake.directory(draft["id"]) / "input.apk"
    path.write_bytes(b"private-transfer-canary-NOT-AN-APK")
    key = tmp_path / "material.key"
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    value = RuntimeMaterials(store, key)
    try:
        yield value, intake, draft, path, key
    finally:
        intake.close()


def execution(store, intake, draft):
    event = PostgresOutbox(store).register(queued(), "a" * 64)
    PostgresOutbox(store).claim()
    with store._transaction() as conn:
        document = intake.directory(draft["id"]) / ("run-" + event.job_id + ".json")
        intake._write_private(document, {"version": 1, "job_id": event.job_id})
        conn.execute(
            runtime_inputs.insert().values(
                instance_id=store.instance_id,
                job_id=event.job_id,
                draft_id=draft["id"],
                document_key=intake._key(document),
            )
        )
    return PostgresExecution(store).acquire(event.message)


@pytest.mark.parametrize("scanning", [False, True])
def test_actual_mtls_download_is_bound_to_draft_or_execution_and_digest(
    store, materials, tls_materials, scanning
):
    api, intake, draft, path, _ = materials
    lease = execution(store, intake, draft) if scanning else None
    file = api.register(path, draft_id=draft["id"], lease=lease)
    claims = ticket_claims(file["ticket"])
    assert claims["scope_id"] == (lease.job_id if scanning else draft["id"])
    assert file["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert str(path) not in str(claims) and "private-transfer-canary" not in str(claims)
    tls = tls_materials
    server = create_gateway(
        store, ("127.0.0.1", 0), tls["server"], [tls["client_fingerprint"]], api
    )
    with serving(server):
        client = PrivateClient(
            "https://127.0.0.1:" + str(server.server_port), tls["client"], timeout=3
        )
        assert client.json("/v1/permit", ticket=file["ticket"])["permitted"]
        with client.open("/v1/material", ticket=file["ticket"]) as response:
            assert response.read() == path.read_bytes()
        path.write_bytes(b"changed")
        with pytest.raises(PermissionError, match="operation rejected"):
            client.open("/v1/material", ticket=file["ticket"])


@pytest.mark.parametrize("action", ["cancel", "delete", "retry"])
def test_live_ticket_is_revoked_by_job_cancellation_deletion_or_new_fence(store, materials, action):
    api, intake, draft, path, _ = materials
    lease = execution(store, intake, draft)
    file = api.register(path, draft_id=draft["id"], lease=lease)
    assert api.verify(file["ticket"])["scope_id"] == lease.job_id
    if action == "retry":
        PostgresExecution(store).retry(lease, code="WORKER_LOST", delay_seconds=0)
    else:
        getattr(store, action)(lease.job_id)
    with pytest.raises(PermissionError, match="permit unavailable"):
        api.verify(file["ticket"])


def test_ticket_cannot_be_resigned_tampered_or_used_in_another_instance(store, materials, tmp_path):
    api, _, draft, path, key = materials
    file = api.register(path, draft_id=draft["id"])
    payload, signature = file["ticket"].split(".")
    changed = bytearray(decode(payload))
    changed[-2] ^= 1
    for token in [
        encode(bytes(changed)) + "." + signature,
        payload + "." + encode(b"a" * 32),
        "not-a-ticket",
    ]:
        with pytest.raises(PermissionError):
            api.verify(token)
    other = PostgresJobStore(store.engine.url, str(uuid4()), tmp_path / "other")
    try:
        with pytest.raises(PermissionError):
            RuntimeMaterials(other, key).verify(file["ticket"])
        with other._transaction() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(runner_materials)) == 0
    finally:
        other.close()


def test_expired_registry_reference_is_denied_even_with_valid_signature(
    store, materials, postgres_urls
):
    api, _, draft, path, _ = materials
    file = api.register(path, draft_id=draft["id"])
    owner = sa.create_engine(postgres_urls[1], hide_parameters=True)
    try:
        with owner.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('privacytrace.instance_id', :i, true)"),
                {"i": store.instance_id},
            )
            conn.execute(
                runner_materials.update().values(
                    expires_at=sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'")
                )
            )
        with pytest.raises(PermissionError):
            api.verify(file["ticket"])
    finally:
        owner.dispose()


def test_transfer_registration_rejects_other_draft_host_path_wrong_digest_and_capacity(
    materials, tmp_path, monkeypatch
):
    api, _, draft, path, _ = materials
    foreign = tmp_path / "foreign.apk"
    foreign.write_bytes(b"outside")
    for candidate, draft_id in [(foreign, draft["id"]), (path, uuid4().hex)]:
        with pytest.raises((ValueError, PermissionError)):
            api.register(candidate, draft_id=draft_id)
    with pytest.raises(ValueError, match="digest changed"):
        api.register(path, draft_id=draft["id"], expected_sha256="a" * 64)
    monkeypatch.setattr(api, "MAX_REFERENCES", 1)
    api.register(path, draft_id=draft["id"])
    with pytest.raises(ValueError, match="capacity"):
        api.register(path, draft_id=draft["id"])
    assert path.read_bytes() == b"private-transfer-canary-NOT-AN-APK"


def test_uncommitted_material_permit_cannot_escape_transaction(store, materials):
    api, _, draft, path, _ = materials
    with store._transaction(), pytest.raises(ValueError, match="standalone"):
        api.register(path, draft_id=draft["id"])
