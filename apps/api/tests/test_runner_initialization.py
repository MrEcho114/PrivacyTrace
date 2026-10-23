"""Issue #277: a transient failure in the operation-initialization window must not
leave a permanently charged RUNNING ledger row.

Deterministic and Docker-free: the Runner is assembled with Runner.__new__ and
only the ledger plus the initialization window is exercised. The fault is a real
OSError(errno.ENOSPC) injected through Path.mkdir, the same failure a full disk
raises in _run_owned.
"""

import errno
import hashlib
import json
import sqlite3
import time
from base64 import urlsafe_b64encode
from pathlib import Path
from threading import BoundedSemaphore
from types import SimpleNamespace
from uuid import uuid4

import pytest

from privacytrace.runner_service import Runner, RunnerConfig
from privacytrace.runtime_tls import RuntimeUnavailable

INSTANCE = str(uuid4())
OWNER = str(uuid4())
IMAGE = "sha256:" + "a" * 64
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
    "state TEXT NOT NULL, result BLOB, expires INTEGER NOT NULL)"
)


class FakeGateway:
    """Only the two RPC surfaces _run_owned uses; material transfer always fails."""

    def __init__(self, material_error="Runner material gateway unavailable"):
        self.material_error = material_error
        self.permits = 0
        self.materials = 0

    def json(self, path, **kwargs):
        assert path == "/v1/permit"
        self.permits += 1
        return {"version": 1, "permitted": True}

    def open(self, path, **kwargs):
        assert path == "/v1/material"
        self.materials += 1
        raise RuntimeUnavailable(self.material_error)


def build_runner(tmp_path, gateway=None):
    runner = Runner.__new__(Runner)
    runner.config = RunnerConfig(INSTANCE, IMAGE, tmp_path / "runner")
    runner.root = Path(tmp_path) / "runner"
    runner.root.mkdir()
    runner.operations = runner.root / "operations"
    runner.operations.mkdir()
    runner.database = runner.root / "requests.sqlite"
    with sqlite3.connect(runner.database) as conn:
        conn.execute(SCHEMA)
    runner.slots = BoundedSemaphore(1)
    runner.faulted = False
    runner.gateway = gateway or FakeGateway()
    return runner


def ticket():
    claims = {
        "version": 1,
        "instance_id": INSTANCE,
        "material_id": str(uuid4()),
        "scope_id": "scope-1",
        "owner": OWNER,
        "fence": 1,
        "expires": int(time.time()) + 600,
        "mode": "scan",
    }
    raw = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
    payload = urlsafe_b64encode(raw).decode().rstrip("=")
    signature = urlsafe_b64encode(b"\x00" * 32).decode().rstrip("=")
    return payload + "." + signature


def request(request_id):
    return {
        "version": 1,
        "operation": "scan",
        "request_id": request_id,
        "instance_id": INSTANCE,
        "scope_id": "scope-1",
        "owner": OWNER,
        "fence": 1,
        "package_set": False,
        "files": [{"name": "sample.apk", "sha256": "b" * 64, "size": 1024, "ticket": ticket()}],
    }


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def ledger(runner, request_id):
    with sqlite3.connect(runner.database) as conn:
        return conn.execute(
            "SELECT state,result,expires FROM operations WHERE id=?", (request_id,)
        ).fetchone()


@pytest.fixture
def mkdir_fault(monkeypatch):
    """Real OSError from a full disk, scoped to one target directory."""

    fault = SimpleNamespace(target=None)
    original = Path.mkdir

    def fake(self, mode=0o777, parents=False, exist_ok=False):
        if fault.target is not None and self == fault.target:
            raise OSError(errno.ENOSPC, "No space left on device")
        return original(self, mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fake)
    return fault


def assert_retired(runner, request_id):
    stored = ledger(runner, request_id)
    assert stored is not None, "the charged row must be retired, not deleted"
    state, result, expires = stored
    assert state == "ABORTED"
    assert result is None
    assert expires <= int(time.time())


def test_operation_mkdir_failure_retires_the_charged_row(tmp_path, mkdir_fault):
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    mkdir_fault.target = runner.operations / request_id

    with pytest.raises(OSError) as caught:
        runner._run_owned(request(request_id))

    assert type(caught.value) is OSError
    assert caught.value.errno == errno.ENOSPC
    assert runner.faulted is False
    assert_retired(runner, request_id)
    assert not (runner.operations / request_id).exists()
    runner.prune()
    assert ledger(runner, request_id) is None


def test_inputs_mkdir_failure_removes_the_operation_tree(tmp_path, mkdir_fault):
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    mkdir_fault.target = runner.operations / request_id / "inputs"

    with pytest.raises(OSError) as caught:
        runner._run_owned(request(request_id))

    assert type(caught.value) is OSError
    assert caught.value.errno == errno.ENOSPC
    assert runner.faulted is False
    assert_retired(runner, request_id)
    assert not (runner.operations / request_id).exists()
    assert list(runner.operations.iterdir()) == []
    runner.prune()
    assert ledger(runner, request_id) is None


def test_new_request_passes_the_ledger_gate_after_a_transient_failure(tmp_path, mkdir_fault):
    gateway = FakeGateway()
    runner = build_runner(tmp_path, gateway)
    broken, fresh = str(uuid4()), str(uuid4())
    mkdir_fault.target = runner.operations / broken
    with pytest.raises(OSError):
        runner.run(request(broken))
    mkdir_fault.target = None

    result = runner.run(request(fresh))

    # Controlled failure, but provably later than initialization and the ledger gate.
    assert result["error"] == "RUNNER_UNAVAILABLE"
    assert gateway.materials == 1
    assert gateway.permits == 2
    assert ledger(runner, fresh)[0] == "DONE"
    assert ledger(runner, broken) is None
    assert list(runner.operations.iterdir()) == []


def test_interrupted_row_refuses_the_same_request_until_it_is_reclaimed(tmp_path, mkdir_fault):
    runner = build_runner(tmp_path)
    crashed = str(uuid4())
    interrupted = request(crashed)
    # A hard crash before the compensation ran leaves RUNNING, which prune never
    # reclaims: the same RPC is then refused forever (issue #277's amplifier).
    with sqlite3.connect(runner.database) as conn:
        conn.execute(
            "INSERT INTO operations VALUES (?,?,'RUNNING',NULL,?)",
            (crashed, digest(interrupted), int(time.time()) + 360),
        )
    with pytest.raises(RuntimeUnavailable, match="Runner operation interrupted"):
        runner._run_owned(interrupted)

    # The interrupted-and-expired row of a failed attempt is reclaimed, so the
    # same request_id may initialize again once prune has run.
    broken = str(uuid4())
    value = request(broken)
    mkdir_fault.target = runner.operations / broken
    with pytest.raises(OSError):
        runner._run_owned(value)
    assert_retired(runner, broken)
    mkdir_fault.target = None
    runner.prune()
    assert ledger(runner, broken) is None

    result = runner.run(value)

    assert result["error"] == "RUNNER_UNAVAILABLE"
    assert runner.gateway.materials == 1
    assert ledger(runner, broken)[0] == "DONE"


def test_unproven_compensation_faults_the_runner_and_keeps_the_error(tmp_path, monkeypatch):
    runner = build_runner(tmp_path)
    request_id = str(uuid4())
    original = Path.mkdir

    def hostile(self, mode=0o777, parents=False, exist_ok=False):
        if self == runner.operations / request_id:
            # The ledger itself becomes unwritable at the same moment.
            runner.database = runner.root / "missing" / "requests.sqlite"
            raise OSError(errno.ENOSPC, "No space left on device")
        return original(self, mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", hostile)

    with pytest.raises(OSError) as caught:
        runner._run_owned(request(request_id))

    assert caught.value.errno == errno.ENOSPC
    assert runner.faulted is True
