"""Runner operation lifecycle: a failed mkdir or cleanup must stay recoverable.

#277: an OSError between the RUNNING insert and the mkdir pair left a row that
prune excludes forever, charging one of the 128 operation slots until restart.
#278: a DONE row deleted ahead of a failed directory cleanup left a directory
that startup recovery could not attribute, so the runner refused to start.
"""

import sqlite3
import time
from pathlib import Path
from threading import BoundedSemaphore
from unittest.mock import patch
from uuid import uuid4

import pytest

from privacytrace.runner_service import Runner
from privacytrace.runtime_tls import RuntimeUnavailable


def build_runner(tmp_path: Path) -> Runner:
    """Minimal ledger/filesystem object; no Docker, gateway, TLS or APK."""
    runner = Runner.__new__(Runner)
    runner.root = tmp_path
    runner.operations = tmp_path / "operations"
    runner.operations.mkdir()
    runner.database = tmp_path / "requests.sqlite"
    runner.faulted = False
    runner.slots = BoundedSemaphore(1)
    with runner._database() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
            "state TEXT NOT NULL, result BLOB, expires INTEGER NOT NULL)"
        )
    return runner


def seed(runner: Runner, request_id: str, state: str, expires: int, result=None) -> None:
    with runner._database() as conn:
        conn.execute(
            "INSERT INTO operations VALUES (?,?,?,?,?)",
            (request_id, "d" * 64, state, result, expires),
        )


def row(runner: Runner, request_id: str):
    with runner._database() as conn:
        return conn.execute(
            "SELECT state,result,expires FROM operations WHERE id=?", (request_id,)
        ).fetchone()


def request_value(request_id: str) -> dict:
    return {"request_id": request_id, "files": [{"name": "input.apk", "size": 0, "sha256": "e" * 64,
                                                 "ticket": "unused"}], "operation": "scan",
            "instance_id": "unused", "scope_id": "unused", "owner": "unused", "fence": 1}


def test_failed_operation_mkdir_releases_the_running_row(tmp_path):
    """#277: the RUNNING row must not survive a failed initialization."""
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    real_mkdir = Path.mkdir

    def fail_operation_mkdir(self, *args, **kwargs):
        if self == runner.operations / request_id:
            raise OSError(28, "No space left on device")
        return real_mkdir(self, *args, **kwargs)

    with patch.object(Path, "mkdir", new=fail_operation_mkdir):
        with pytest.raises(OSError):
            runner._run_owned(request_value(request_id))

    assert not (runner.operations / request_id).exists(), "the partial directory is removed"
    state, result, expires = row(runner, request_id)
    assert state == "ABORTED", "a failed initialization becomes a terminal row"
    assert result is None

    with runner._database() as conn:
        conn.execute("UPDATE operations SET expires=0 WHERE id=?", (request_id,))
    runner.prune()
    assert row(runner, request_id) is None, "the abort row is reclaimable once it expires"


def test_failed_inputs_mkdir_also_releases_the_running_row(tmp_path):
    """#277 second variant: the second mkdir can fail after the first succeeded."""
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    real_mkdir = Path.mkdir

    def fail_inputs_mkdir(self, *args, **kwargs):
        if self == runner.operations / request_id / "inputs":
            raise OSError(13, "Permission denied")
        return real_mkdir(self, *args, **kwargs)

    with patch.object(Path, "mkdir", new=fail_inputs_mkdir):
        with pytest.raises(OSError):
            runner._run_owned(request_value(request_id))

    assert not (runner.operations / request_id).exists()
    assert row(runner, request_id)[0] == "ABORTED"


def test_prune_keeps_a_done_row_whose_directory_survives_a_failed_cleanup(tmp_path):
    """#278: the DONE row is the directory's only ownership proof."""
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    (runner.operations / request_id).mkdir()
    seed(runner, request_id, "DONE", 0, b'{"version":1}')

    with patch("privacytrace.runner_service.shutil.rmtree", side_effect=OSError(13, "in use")):
        runner.prune()

    assert row(runner, request_id) is not None, "the row must outlive an unremoved directory"
    assert (runner.operations / request_id).exists()
    assert row(runner, request_id)[0] == "DONE", "state is unchanged, so recovery can attribute it"

    # Once the filesystem heals, the same sweep reclaims both.
    runner.prune()
    assert row(runner, request_id) is None
    assert not (runner.operations / request_id).exists()


def test_prune_removes_an_expired_row_whose_directory_is_already_gone(tmp_path):
    """An already-clean row must not be kept forever by the FileNotFoundError path."""
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    seed(runner, request_id, "DONE", 0, b"{}")

    runner.prune()

    assert row(runner, request_id) is None


def test_prune_never_deletes_a_running_row(tmp_path):
    """A live operation is protected even when its expires field has passed."""
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    seed(runner, request_id, "RUNNING", 0)

    runner.prune()

    assert row(runner, request_id) is not None


def test_recovery_starts_on_a_done_residue_that_prune_kept(tmp_path):
    """#278 end state: a kept DONE row makes the residue attributable at startup."""
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    (runner.operations / request_id).mkdir()
    seed(runner, request_id, "DONE", 0, b"{}")

    with patch("privacytrace.runner_service.shutil.rmtree", side_effect=OSError(13, "in use")):
        runner.prune()
    assert row(runner, request_id) is not None

    # Startup recovery reaps a known operation instead of refusing to start.
    runner._recover()
    assert not (runner.operations / request_id).exists()
    assert row(runner, request_id) is None
