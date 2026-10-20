"""Opt-in real ENOSPC on a tiny owned Linux tmpfs; never fill the host volume."""

import errno
import os
import subprocess
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import queued

from privacytrace.deletion_journal import DeletionJournal
from privacytrace.material_lifecycle import MaterialLifecycle
from privacytrace.postgres_intake import PostgresWebIntake
from privacytrace.postgres_outbox import PostgresOutbox
from privacytrace.postgres_schema import outbox
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.web_models import DraftInput


def test_actual_enospc_rolls_back_registration_and_keeps_delete_journal_writable(
    postgres_urls, tmp_path
):
    if os.environ.get("PRIVACYTRACE_ENOSPC_TESTS") != "1":
        pytest.skip("Explicit disposable root Linux tmpfs ENOSPC acceptance required")
    assert os.name == "posix" and os.geteuid() == 0
    mount = tmp_path / "owned-tiny-volume"
    mount.mkdir(mode=0o700)
    assert mount.resolve().parent == tmp_path.resolve() and not mount.is_symlink()
    subprocess.run(
        [
            "mount",
            "-t",
            "tmpfs",
            "-o",
            "size=8m,mode=0700,nosuid,nodev,noexec",
            "privacytrace-enospc-test",
            str(mount),
        ],
        check=True,
        capture_output=True,
    )
    store = intake = None
    try:
        store = PostgresJobStore(postgres_urls[0], str(uuid4()), mount)
        intake = PostgresWebIntake(store)
        journal = DeletionJournal(
            tmp_path / "independent-journal", store.instance_id, os.urandom(32)
        )
        store.deletion_journal = journal
        lifecycle = MaterialLifecycle(store, intake, journal)
        draft = intake.create(
            DraftInput(name="retained before ENOSPC", sources=[{"id": "s", "title": "policy"}]),
            "a" * 64,
        )
        expected = intake.get(draft["id"])
        retained = queued()
        store.create_if_absent(retained, "b" * 64)
        filler = mount / "owned-filler"
        with filler.open("xb", buffering=0) as output:
            with pytest.raises(OSError) as full:
                while True:
                    output.write(b"x" * 65536)
                    output.flush()
            assert full.value.errno == errno.ENOSPC
        job = queued()
        with pytest.raises(OSError) as rejected:
            with store._transaction():
                PostgresOutbox(store).register(job)
                intake._write_private(
                    intake.directory(draft["id"]) / "failed.json", {"text": "x" * 65536}
                )
        assert rejected.value.errno == errno.ENOSPC
        with pytest.raises(KeyError):
            store.get(job.id)
        with store._transaction() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(outbox)) == 0
        assert intake.get(draft["id"]) == expected
        # Revocation has an independent durable home even with a full material
        # filesystem. It cannot depend on deleting the retained official draft.
        store.delete(retained.id)
        assert store.is_tombstoned(retained.id) and len(journal.entries()) == 1
        filler.unlink()
        assert lifecycle.collect()["objects"] >= 1
        assert intake.get(draft["id"]) == expected
    finally:
        if intake:
            intake.close()
        if store:
            store.close()
        subprocess.run(["umount", str(mount)], check=True, capture_output=True)
