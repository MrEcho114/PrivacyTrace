"""Actual PostgreSQL registration/restart; no scanner or broker acceptance claim."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import store as store

from privacytrace.durable_intake import DurableWebIntake
from privacytrace.postgres_execution import PostgresExecution
from privacytrace.postgres_intake import PostgresWebIntake
from privacytrace.postgres_outbox import PostgresOutbox
from privacytrace.postgres_schema import outbox, runtime_inputs
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.web_models import DraftInput, StartInput


@pytest.fixture
def intake(store):
    # Registration-only fixture: it never invokes an inspector or scanner.
    value = DurableWebIntake(store, runner=object())
    yield value
    value.close()


def uploaded(intake):
    draft = intake.create(
        DraftInput(
            name="registration fixture",
            sources=[{"id": "host", "title": "policy", "text": "We do not collect contacts."}],
        ),
        "a" * 64,
    )
    path = intake.directory(draft["id"]) / "input.apk"
    path.write_bytes(b"registration bytes only, no APK parser")
    with intake.store._transaction():
        current = intake._get(draft["id"])
        current.update(
            uploaded=True, apk_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), revision=2
        )
        return intake._save(current)


def test_cutover_requires_stopped_legacy_owner_and_prevents_accidental_legacy_restart(store):
    legacy = PostgresWebIntake(store)
    legacy.start_service()
    try:
        with pytest.raises(ValueError, match="Stop the legacy"):
            DurableWebIntake(store, runner=object())
    finally:
        legacy.close()
    from test_postgres_storage import queued

    old = queued()
    store.create_if_absent(old)
    durable = DurableWebIntake(store, runner=object())
    try:
        assert store.get(old.id).state == "FAILED"
        assert "SERVICE_INTERRUPTED" in store.get(old.id).error
        with pytest.raises(ValueError, match="durable runtime"):
            legacy.start_service()
        draft = uploaded(durable)
        managed = durable.start(
            draft["id"], StartInput(revision=draft["revision"], request_id=uuid4().hex)
        )
        another = DurableWebIntake(store, runner=object())
        try:
            assert store.get(managed.id).state == "QUEUED"
        finally:
            another.close()
    finally:
        durable.close()


def test_registration_snapshot_event_and_job_survive_new_api_instance_without_local_submission(
    intake, store, monkeypatch
):
    draft = uploaded(intake)

    def forbidden(*args, **kwargs):
        raise AssertionError("Durable API must not submit a local analysis worker")

    monkeypatch.setattr(intake.executor, "submit", forbidden)
    payload = StartInput(revision=draft["revision"], request_id=uuid4().hex)
    job = intake.start(draft["id"], payload)
    assert intake.start(draft["id"], payload).id == job.id
    assert intake.futures == {}
    with store._transaction() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(outbox)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(runtime_inputs)) == 1
    event = PostgresOutbox(store).claim()[0]
    lease = PostgresExecution(store).acquire(event.message)
    running = store.get(job.id)
    running.state = "STATIC_ANALYSIS"
    PostgresExecution(store).fenced_store(lease).save_job(running)
    other = PostgresJobStore(store.engine.url, store.instance_id, store.root.parent.parent)
    restarted = DurableWebIntake(other, runner=object())
    try:
        restarted.start_service()
        assert other.get(job.id).state == "STATIC_ANALYSIS"
        snapshot = restarted.input_snapshot(job.id)
        assert snapshot["draft"]["apk_sha256"] == draft["apk_sha256"]
        assert snapshot["captures"][0]["document"]["review_status"] == "UNREVIEWED"
        assert snapshot["captures"][0]["document"]["completeness"] == "PARTIAL"
        restarted.close()
        PostgresExecution(store).checkpoint(lease)
    finally:
        restarted.close()
        other.close()


def test_failed_fenced_pipeline_records_authoritative_draft_terminal_event_once(intake, store):
    draft = uploaded(intake)
    job = intake.start(draft["id"], StartInput(revision=draft["revision"], request_id=uuid4().hex))
    event = PostgresOutbox(store).claim()[0]
    execution = PostgresExecution(store)
    lease = execution.acquire(event.message)
    failed = store.get(job.id)
    failed.state = "FAILED"
    execution.fenced_store(lease).save_job(failed)
    intake.terminal_event(lease)
    history = intake.get(draft["id"])["jobs"][0]["events"]
    assert history[-1]["state"] == "FAILED"
    intake.terminal_event(lease)
    assert intake.get(draft["id"])["jobs"][0]["events"] == history


def test_concurrent_same_submission_registers_exactly_one_event_and_snapshot(store, intake):
    draft = uploaded(intake)
    payload = StartInput(revision=draft["revision"], request_id=uuid4().hex)

    def start(_):
        other = PostgresJobStore(store.engine.url, store.instance_id, store.root.parent.parent)
        worker = DurableWebIntake(other, runner=object())
        try:
            return worker.start(draft["id"], payload).id
        finally:
            worker.close()
            other.close()

    with ThreadPoolExecutor(3) as pool:
        assert len(set(pool.map(start, range(3)))) == 1
    with store._transaction() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(outbox)) == 1
        assert conn.scalar(sa.select(sa.func.count()).select_from(runtime_inputs)) == 1


def test_failed_snapshot_admission_rolls_back_job_event_and_submission(intake, store, monkeypatch):
    draft = uploaded(intake)
    monkeypatch.setattr(intake, "MAX_ACTIVE_JOBS", 0)
    payload = StartInput(revision=draft["revision"], request_id=uuid4().hex)
    with pytest.raises(ValueError, match="admission"):
        intake.start(draft["id"], payload)
    assert store.list() == [] and intake.get(draft["id"])["jobs"] == []
    assert intake.futures == {}
    with store._transaction() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(outbox)) == 0
        assert conn.scalar(sa.select(sa.func.count()).select_from(runtime_inputs)) == 0
    monkeypatch.setattr(intake, "MAX_ACTIVE_JOBS", 4)
    assert intake.start(draft["id"], payload).state == "QUEUED"


def test_live_snapshot_is_digest_checked_and_deleted_job_cannot_recover_inputs(intake, store):
    draft = uploaded(intake)
    job = intake.start(draft["id"], StartInput(revision=draft["revision"], request_id=uuid4().hex))
    document = intake.directory(draft["id"]) / ("run-" + job.id + ".json")
    reference = store.document(intake._key(document))
    material = intake.materials / reference["material_ref"]
    before = material.read_bytes()
    material.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        intake.input_snapshot(job.id)
    material.write_bytes(before)
    store.delete(job.id)
    with pytest.raises(KeyError):
        intake.input_snapshot(job.id)
