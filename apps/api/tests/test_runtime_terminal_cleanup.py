"""Terminal telemetry must never skip runtime resource cleanup (#225).

These cases run without celery and without PostgreSQL: they exercise the
cleanup guard and the missing-job-row branches directly, so CI (which installs
only the worker extra) actually executes them.
"""

import contextlib

import pytest

from privacytrace import durable_intake, runtime_worker
from privacytrace.durable_intake import DurableWebIntake
from privacytrace.web_intake import WebIntake


class Recorder:
    def __init__(self, name, calls, terminal_error=None):
        self.name = name
        self.calls = calls
        self.terminal_error = terminal_error

    def terminal_event(self, lease):
        self.calls.append("terminal_event")
        if self.terminal_error is not None:
            raise self.terminal_error

    def close(self):
        self.calls.append(self.name + ".close")


class FakeThread:
    def __init__(self):
        self.joins = []

    def join(self, timeout=None):
        self.joins.append(timeout)


def run_finish(terminal_error=None, *, calls=None, thread=None):
    calls = [] if calls is None else calls
    thread = FakeThread() if thread is None else thread
    runtime_worker._finish_runtime(
        object(),
        intake=Recorder("intake", calls, terminal_error),
        busy=Recorder("busy", calls),
        store=Recorder("store", calls),
        stopping=runtime_worker.Event(),
        thread=thread,
    )
    return calls, thread


def test_stop_iteration_from_terminal_event_still_releases_every_resource(monkeypatch):
    codes = []
    monkeypatch.setattr(runtime_worker, "_diagnostic", codes.append)
    calls, thread = run_finish(StopIteration("draft job row missing"))
    assert calls == ["terminal_event", "intake.close", "busy.close", "store.close"]
    assert codes == ["TERMINAL_EVENT_UNAVAILABLE"]
    assert thread.joins == [20]


def test_unexpected_terminal_error_releases_every_resource_before_propagating(monkeypatch):
    codes = []
    monkeypatch.setattr(runtime_worker, "_diagnostic", codes.append)
    calls = []
    with pytest.raises(RuntimeError):
        run_finish(RuntimeError("unexpected"), calls=calls)
    assert calls == ["terminal_event", "intake.close", "busy.close", "store.close"]
    assert codes == []


def test_known_terminal_failures_map_to_their_fixed_diagnostics(monkeypatch):
    codes = []
    monkeypatch.setattr(runtime_worker, "_diagnostic", codes.append)
    run_finish(runtime_worker.PostgresOperationUnavailable("db"))
    run_finish(runtime_worker.LeaseLost("lease"))
    assert codes == ["STORAGE_UNAVAILABLE", "LEASE_LOST"]


class _Lease:
    job_id = "job-missing"
    fence = 3


class _Execution:
    def __init__(self, store):
        self.store = store

    def status(self, job_id):
        return {"fence": _Lease.fence, "state": "SUCCEEDED"}


class _Store:
    def _transaction(self):
        return contextlib.nullcontext()


class _StubIntake:
    store = _Store()

    def input_snapshot(self, job_id):
        return {"draft": {"id": "draft-1"}}

    def _get(self, draft_id):
        return {"jobs": [{"job_id": "another-job", "events": []}]}

    def _event(self, *args):
        raise AssertionError("a missing job row must not be recorded")


def test_terminal_event_raises_a_controlled_key_error_for_a_lost_draft_job(monkeypatch):
    monkeypatch.setattr(durable_intake, "PostgresExecution", _Execution)
    with pytest.raises(KeyError, match="is not part of draft draft-1"):
        DurableWebIntake.terminal_event(_StubIntake(), _Lease())


class _DataStore:
    def _transaction(self):
        return contextlib.nullcontext()


def test_web_intake_event_raises_a_controlled_key_error_for_a_lost_job():
    stub = type(
        "WebStub",
        (),
        {"data_store": _DataStore(), "_get": lambda self, draft_id: {"jobs": []}},
    )()
    with pytest.raises(KeyError, match="is not part of draft draft-1"):
        WebIntake._event(stub, "draft-1", "job-missing", "QUEUED")
