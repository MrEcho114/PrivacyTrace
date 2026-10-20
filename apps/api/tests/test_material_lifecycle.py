"""Real PG + private files: retention, revocation, committed-reference GC and replay."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_durable_intake import uploaded
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import store as store

from privacytrace.deletion_journal import DeletionJournal
from privacytrace.durable_intake import UPLOAD_OWNER, DurableWebIntake
from privacytrace.postgres_schema import audit, deletions, documents, runtime_inputs, uploads
from privacytrace.web_intake import write_private
from privacytrace.web_models import StartInput


@pytest.fixture
def intake(store, tmp_path):
    store.deletion_journal = DeletionJournal(
        tmp_path / "independent-journal", store.instance_id, os.urandom(32)
    )
    value = DurableWebIntake(store, runner=object())
    yield value
    value.close()


def start(intake, draft):
    return intake.start(draft["id"], StartInput(revision=draft["revision"], request_id=uuid4().hex))


def test_gc_preserves_all_live_references_and_official_apk_until_explicit_draft_delete(
    intake, store
):
    draft = uploaded(intake)
    job = start(intake, draft)
    untouched = uploaded(intake)
    other_path = intake.directory(untouched["id"]) / "input.apk"
    orphan = intake.materials / uuid4().hex
    orphan.write_bytes(b"uncommitted orphan")
    intake.lifecycle.collect()
    assert not orphan.exists()
    with store._transaction() as conn:
        references = list(conn.scalars(sa.select(documents.c.material_ref)))
    assert all((intake.materials / name).exists() for name in references)
    store.delete(job.id)
    assert store.deletion_journal.entries()[0]["kind"] == "JOB"
    intake.lifecycle.collect()
    assert (intake.directory(draft["id"]) / "input.apk").exists()
    with store._transaction() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(runtime_inputs)) == 0
    assert intake.lifecycle.delete_draft(draft["id"]) == {"deleted": True, "cleanup_pending": False}
    assert not intake.directory(draft["id"]).exists()
    assert other_path.exists() and intake.get(untouched["id"])["uploaded"]
    with pytest.raises(KeyError):
        store.draft_digest(draft["id"])
    assert store.is_tombstoned(job.id)


def test_uncertain_delete_intent_survives_db_rollback_and_replays_without_audit_growth(
    intake, store
):
    job = start(intake, uploaded(intake))
    with pytest.raises(RuntimeError):
        with store._transaction():
            store.delete(job.id)
            raise RuntimeError("abort before DB commit")
    assert store.get(job.id).state == "QUEUED"
    assert len(store.deletion_journal.entries()) == 1
    assert intake.lifecycle.replay() == 1
    assert store.is_tombstoned(job.id)
    with store._transaction() as conn:
        before = conn.scalar(sa.select(sa.func.count()).select_from(audit))
    intake.lifecycle.replay()
    with store._transaction() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == before


def test_missing_committed_delete_journal_prevents_recovery_and_new_job_id_cannot_revive(
    intake, store
):
    job = start(intake, uploaded(intake))
    store.delete(job.id)
    journal = store.deletion_journal
    before = journal.path.read_bytes()
    journal.path.write_bytes(b"")
    with pytest.raises(ValueError, match="missing committed history"):
        intake.lifecycle.replay()
    journal.path.write_bytes(before)
    intake.lifecycle.replay()
    with pytest.raises(ValueError, match="already exists"):
        store.create_if_absent(job)


def test_gc_reclaims_only_owned_expired_uploads_and_preserves_live_and_unknown_files(intake, store):
    draft = uploaded(intake)
    directory = intake.directory(draft["id"])
    old, live = uuid4(), uuid4()
    for owner in (old, live):
        write_private(
            directory / (".upload-owner-" + owner.hex + ".json"),
            {"instance_id": store.instance_id, "draft_id": draft["id"], "owner": owner.hex},
        )
        (directory / ("upload.pending." + owner.hex)).write_bytes(b"pending")
        staging = directory / ("packages.pending." + owner.hex)
        staging.mkdir()
        (staging / "base.apk").write_bytes(b"pending")
    unknown = directory / "upload.pending.unknown"
    unknown.write_bytes(b"not owned by this mechanism")
    with store._transaction() as conn:
        conn.execute(
            uploads.insert().values(
                instance_id=store.instance_id,
                draft_id=draft["id"],
                owner=live,
                expires_at=conn.scalar(sa.select(sa.func.clock_timestamp()))
                + timedelta(seconds=900),
            )
        )
    result = intake.lifecycle.collect()
    assert result["temporary"] == 2
    assert not (directory / ("upload.pending." + old.hex)).exists()
    assert (directory / ("upload.pending." + live.hex)).exists() and unknown.exists()
    context = UPLOAD_OWNER.set(old)
    try:
        with store._transaction(), pytest.raises(ValueError, match="expired or revoked"):
            intake._before_publish_upload(draft["id"])
        write_private(
            directory / ".published-upload-owner",
            {"instance_id": store.instance_id, "draft_id": draft["id"], "owner": live.hex},
        )
        with store._transaction():
            assert not intake._may_remove_published(draft["id"])
    finally:
        UPLOAD_OWNER.reset(context)


def test_deletion_history_is_append_only_and_new_tables_force_instance_rls(intake, store):
    store.delete(start(intake, uploaded(intake)).id)
    for statement in [
        "DELETE FROM privacytrace.deletion_intents",
        "UPDATE privacytrace.deletion_intents SET sequence=100",
        "TRUNCATE privacytrace.upload_reservations",
    ]:
        with store.engine.begin() as conn, pytest.raises(sa.exc.DBAPIError) as error:
            conn.execute(sa.text(statement))
        assert error.value.orig.sqlstate == "42501"
    with store.engine.begin() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(deletions)) == 0
        for name in ("deletion_intents", "upload_reservations"):
            assert conn.execute(
                sa.text(
                    "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                    "WHERE oid=cast(:table as regclass)"
                ),
                {"table": "privacytrace." + name},
            ).one() == (True, True)
