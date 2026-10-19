"""Real PostgreSQL in two databases + authenticated material restore; no DB doubles."""

import hashlib
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_durable_intake import uploaded
from test_postgres_storage import migration
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import store as store

from privacytrace.deletion_journal import DeletionJournal
from privacytrace.durable_intake import DurableWebIntake
from privacytrace.postgres_execution import LeaseLost, PostgresExecution
from privacytrace.postgres_intake import PostgresWebIntake
from privacytrace.postgres_outbox import PostgresOutbox
from privacytrace.postgres_schema import executions, jobs, scopes
from privacytrace.postgres_store import PostgresJobStore, PostgresOperationUnavailable
from privacytrace.runtime_backup import RuntimeBackup
from privacytrace.web_models import StartInput


@pytest.fixture(scope="module")
def restore_urls(postgres_urls):
    rt = os.environ.get("PRIVACYTRACE_TEST_RESTORE_DATABASE_URL")
    mg = os.environ.get("PRIVACYTRACE_TEST_RESTORE_MIGRATION_DATABASE_URL")
    if not rt or not mg:
        pytest.skip("Explicit second disposable PostgreSQL restore database required")
    runtime, migrator = sa.engine.make_url(rt), sa.engine.make_url(mg)
    assert runtime.database.endswith("_test")
    assert runtime.database != sa.engine.make_url(postgres_urls[0]).database
    assert (runtime.host, runtime.port, runtime.database) == (
        migrator.host,
        migrator.port,
        migrator.database,
    )
    assert runtime.username != migrator.username
    migration(mg)
    return rt, mg


@pytest.fixture
def recovery(store, restore_urls, tmp_path):
    key = os.urandom(32)
    journal = DeletionJournal(tmp_path / "independent-journal", store.instance_id, key)
    store.deletion_journal = journal
    source = DurableWebIntake(store, runner=object())
    target_store = PostgresJobStore(restore_urls[0], store.instance_id, tmp_path / "restore")
    target = PostgresWebIntake(target_store)
    yield (
        RuntimeBackup(store, source, journal, key),
        RuntimeBackup(target_store, target, journal, key),
        tmp_path / "data.ptbackup",
    )
    source.close()
    target.close()
    target_store.close()


def start(source):
    draft = uploaded(source.intake)
    job = source.intake.start(
        draft["id"], StartInput(revision=draft["revision"], request_id=uuid4().hex)
    )
    return draft, job


def test_restore_retains_official_materials_replays_new_deletions_and_rejects_old_lease(recovery):
    source, target, path = recovery
    draft, job = start(source)
    dead_draft, dead_job = start(source)
    source.intake._write_private(
        source.intake.root / "model.json", {"api_key": "never-backup-this-key"}
    )
    receipt = source.backup(path)
    assert receipt["files"] > 0
    assert b"never-backup-this-key" not in path.read_bytes()
    event = PostgresOutbox(source.store).claim()[0]
    lease = PostgresExecution(source.store).acquire(event.message)
    source.lifecycle.delete_draft(dead_draft["id"])
    # Restore an older snapshot, with the latest independent deletion history.
    assert target.restore(path)["restored"]
    assert target.intake.get(draft["id"])["uploaded"]
    assert (
        target.intake.directory(draft["id"]) / "input.apk"
    ).read_bytes() == b"registration bytes only, no APK parser"
    assert target.store.get(job.id).state == "QUEUED"
    assert target.store.is_tombstoned(dead_job.id)
    assert not target.intake.directory(dead_draft["id"]).exists()
    with pytest.raises(KeyError):
        target.store.draft_digest(dead_draft["id"])
    with pytest.raises(LeaseLost):
        PostgresExecution(target.store).checkpoint(lease)
    with target.store._transaction() as conn:
        row = (
            conn.execute(sa.select(executions).where(executions.c.job_id == job.id))
            .mappings()
            .one()
        )
        assert row["owner"] is None and row["fence"] > 0 and row["attempt"] == 0
    assert not (target.store.root / ".restore-in-progress").exists()
    with pytest.raises(ValueError, match="empty database"):
        target.restore(path)


@pytest.mark.parametrize("damage", ["signature", "material", "truncate", "trailing"])
def test_corrupt_backup_never_commits_rows_and_interrupted_restore_blocks_other_connections(
    recovery, damage
):
    source, target, path = recovery
    _, job = start(source)
    source.backup(path)
    data = bytearray(path.read_bytes())
    if damage == "signature":
        data[30] ^= 1
    elif damage == "material":
        data[-1] ^= 1
    elif damage == "truncate":
        del data[-1:]
    else:
        data += b"untrusted trailing bytes"
    broken = path.with_name("broken.ptbackup")
    broken.write_bytes(data)
    broken.chmod(0o600)
    with pytest.raises(ValueError):
        target.restore(broken)
    target.store._allow_restore = True
    try:
        with target.store._transaction() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(jobs)) == 0
    finally:
        target.store._allow_restore = False
    if damage != "signature":
        with pytest.raises(PostgresOperationUnavailable, match="recovery"):
            target.store.get(job.id)
        # Only the same authenticated manifest can own a resume. Material
        # corruption does not alter the authenticated manifest identity.
        assert target.restore(path, resume=True)["restored"]
        assert target.store.get(job.id).id == job.id


def test_missing_independent_history_rejects_restore_before_publication(recovery):
    source, target, path = recovery
    _, job = start(source)
    source.store.delete(job.id)
    source.backup(path)
    source.journal.path.write_bytes(b"")
    with pytest.raises(ValueError, match="independent deletion"):
        target.restore(path)
    assert not (target.store.root / ".restore-in-progress").exists()


def test_actual_deferred_commit_rejection_retains_gate_and_resume_recovers(recovery, restore_urls):
    source, target, path = recovery
    _, job = start(source)
    source.backup(path)
    engine = sa.create_engine(restore_urls[1], hide_parameters=True)
    # The migration role installs a narrow deferred constraint trigger. The
    # runtime really reaches COMMIT and PostgreSQL rejects the entire import.
    function = "privacytrace.test_restore_" + uuid4().hex
    trigger = "test_restore_" + uuid4().hex
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                    f"BEGIN IF NEW.instance_id = '{target.store.instance_id}' "
                    "AND NEW.action='RESTORE_COMMITTED' THEN "
                    "RAISE EXCEPTION 'controlled restore commit rejection'; "
                    "END IF; RETURN NEW; END $$"
                )
            )
            conn.execute(
                sa.text(
                    f"CREATE CONSTRAINT TRIGGER {trigger} "
                    "AFTER INSERT ON privacytrace.audit_events "
                    f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {function}()"
                )
            )
        with pytest.raises(PostgresOperationUnavailable):
            target.restore(path)
        assert (target.store.root / ".restore-in-progress").exists()
        with pytest.raises(PostgresOperationUnavailable):
            PostgresJobStore(
                restore_urls[0], target.store.instance_id, target.store.root.parent.parent
            )
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP TRIGGER {trigger} ON privacytrace.audit_events"))
        target.store._allow_restore = True
        try:
            with target.store._transaction() as conn:
                assert conn.scalar(sa.select(sa.func.count()).select_from(scopes)) == 0
        finally:
            target.store._allow_restore = False
        assert target.restore(path, resume=True)["restored"]
        assert target.store.get(job.id).id == job.id
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON privacytrace.audit_events"))
            conn.execute(sa.text(f"DROP FUNCTION IF EXISTS {function}()"))
        engine.dispose()


def test_backup_rejects_active_execution_without_partial_output(recovery):
    source, _, path = recovery
    start(source)
    event = PostgresOutbox(source.store).claim()[0]
    PostgresExecution(source.store).acquire(event.message)
    with pytest.raises(ValueError, match="Quiesce"):
        source.backup(path)
    assert not path.exists()


def test_real_large_material_archive_and_postcommit_resume_do_not_duplicate_or_revive(
    recovery, monkeypatch
):
    source, target, path = recovery
    draft = uploaded(source.intake)
    material = source.intake.directory(draft["id"]) / "input.apk"
    material.write_bytes(b"large retained fixture material " * 50000)
    with source.store._transaction():
        current = source.intake._get(draft["id"])
        current["apk_sha256"] = hashlib.sha256(material.read_bytes()).hexdigest()
        current["revision"] += 1
        draft = source.intake._save(current)
    job = source.intake.start(
        draft["id"], StartInput(revision=draft["revision"], request_id=uuid4().hex)
    )
    source.backup(path)
    assert path.stat().st_size > 1024 * 1024
    # Inject failure only in the filesystem cleanup boundary after real COMMIT.
    # The committed audit receipt distinguishes this from a rolled-back import.
    collect = target.lifecycle.collect
    with monkeypatch.context() as patch:

        def unavailable():
            raise OSError("controlled postcommit filesystem unavailability")

        patch.setattr(target.lifecycle, "collect", unavailable)
        with pytest.raises(OSError):
            target.restore(path)
    assert (target.store.root / ".restore-in-progress").exists()
    with pytest.raises(PostgresOperationUnavailable):
        target.store.get(job.id)
    source.lifecycle.delete_draft(draft["id"])
    assert target.restore(path, resume=True)["restored"]
    assert target.store.is_tombstoned(job.id)
    assert not target.intake.directory(draft["id"]).exists()
    assert not list(target.store.root.parent.glob(".restore-stage-*"))
    assert collect()["pending"] == 0


def test_backup_preserves_existing_owned_package_base_hardlink_and_rejects_extra_links(recovery):
    from privacytrace.package_set import PackageFile, PackageSet

    source, target, path = recovery
    draft = uploaded(source.intake)
    directory = source.intake.directory(draft["id"])
    packages = directory / "packages"
    packages.mkdir(mode=0o700)
    os.link(directory / "input.apk", packages / "base.apk")
    package = PackageSet(
        package_name="org.fixture",
        version_code=1,
        base=PackageFile(
            file_name="base.apk",
            part="BASE",
            sha256=draft["apk_sha256"],
            size_bytes=(directory / "input.apk").stat().st_size,
            package_name="org.fixture",
            version_code=1,
        ),
        total_size_bytes=(directory / "input.apk").stat().st_size,
    )
    with source.store._transaction():
        draft["package_set"] = package.model_dump(mode="json")
        draft["revision"] += 1
        source.intake._save(draft)
    outside = source.store.root / "unregistered-hardlink.apk"
    os.link(directory / "input.apk", outside)
    with pytest.raises(ValueError, match="Unsafe backup"):
        source.backup(path)
    outside.unlink()
    source.backup(path)
    assert target.restore(path)["restored"]
    restored = target.intake.directory(draft["id"])
    assert (restored / "input.apk").read_bytes() == (restored / "packages/base.apk").read_bytes()
    assert target.intake.get(draft["id"])["package_set"] == draft["package_set"]
