"""Celery library protocol checks; actual consumption is in test_runtime_e2e."""

import subprocess
import sys
from uuid import uuid4

import pytest

pytest.importorskip("celery", reason="Install runtime extra for Celery protocol checks")

from privacytrace.queue_runtime import TASK_NAME, BrokerConfig  # noqa: E402
from privacytrace.runtime_worker import create_worker_app  # noqa: E402


def test_worker_registry_contains_only_fixed_json_task_and_rejects_embedded_canvas(monkeypatch):
    from privacytrace import runtime_worker

    instance = str(uuid4())
    app = create_worker_app(BrokerConfig("redis://u:p@127.0.0.1:1/15", instance))
    calls = []
    monkeypatch.setattr(runtime_worker, "execute", lambda *args: calls.append(args))
    task = app.tasks[TASK_NAME]
    event = {
        "version": 1,
        "event_type": "privacytrace.job.ready",
        "instance_id": instance,
        "job_id": "protocol-only",
        "event_id": str(uuid4()),
    }
    try:
        assert set(app.tasks) == {TASK_NAME}
        assert app.conf.accept_content == ["json"] and not app.conf.worker_enable_remote_control
        assert app.conf.result_backend is None
        task.push_request(id=event["event_id"], callbacks=[{"task": "untrusted.task"}])
        try:
            task.run(event)
            assert task.request.callbacks is None
        finally:
            task.pop_request()
        task.push_request(id=event["event_id"])
        try:
            task.run(event, command="untrusted")
            task.run({**event, "path": "/host"})
            assert calls == []
            task.run(event)
            assert len(calls) == 1
        finally:
            task.pop_request()
    finally:
        app.close()


def test_actual_celery_worker_constructor_accepts_redacted_logging_without_broker_io():
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
from uuid import uuid4
from privacytrace.runtime_worker import create_worker_app
from privacytrace.queue_runtime import BrokerConfig
app=create_worker_app(BrokerConfig('redis://u:p@127.0.0.1:1/15',str(uuid4())))
worker=app.Worker(pool='solo',concurrency=1,queues=[app.conf.task_default_queue],quiet=True,
                 without_mingle=True,without_gossip=True,without_heartbeat=True,loglevel='CRITICAL')
assert set(app.tasks)=={'privacytrace.execute.v1'}
app.close()
print('CONSTRUCTED')
""",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert child.returncode == 0, "Actual Celery constructor rejected runtime settings"
    assert child.stdout.strip() == "CONSTRUCTED"
