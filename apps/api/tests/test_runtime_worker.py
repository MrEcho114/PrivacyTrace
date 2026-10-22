"""Celery library protocol checks; actual consumption is in test_runtime_e2e."""

import logging
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip("celery", reason="Install runtime extra for Celery protocol checks")

from privacytrace.postgres_execution import LeaseLost  # noqa: E402
from privacytrace.postgres_store import PostgresOperationUnavailable  # noqa: E402
from privacytrace.queue_runtime import PROBE_TASK_NAME, TASK_NAME, BrokerConfig  # noqa: E402
from privacytrace.runtime_worker import (  # noqa: E402
    WORKER_LOG_FORMAT,
    WORKER_TASK_LOG_FORMAT,
    create_worker_app,
)


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
        assert set(app.tasks) == {TASK_NAME, PROBE_TASK_NAME}
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


def test_consumer_proof_rejects_invalid_canvas_and_only_accepts_current_challenge(monkeypatch):
    from privacytrace import runtime_health

    instance = str(uuid4())
    app = create_worker_app(BrokerConfig("redis://u:p@127.0.0.1:1/15", instance))
    accepted = []

    def approve(url, instance_id, challenge):
        accepted.append((instance_id, challenge))
        return True

    monkeypatch.setenv("PRIVACYTRACE_PUBLISH_HEALTH", "1")
    monkeypatch.setattr(runtime_health, "acknowledge_challenge", approve)
    task = app.tasks[PROBE_TASK_NAME]
    challenge = {"version": 1, "instance_id": instance, "challenge_id": str(uuid4()),
                 "issued_at": 12345}
    try:
        task.push_request(id=challenge["challenge_id"], callbacks=[{"task": "unknown"}])
        try:
            task.run(challenge)
            assert accepted == []
            assert task.request.callbacks is None
        finally:
            task.pop_request()
        task.push_request(id=challenge["challenge_id"])
        try:
            task.run(challenge, payload="untrusted")
            task.run()
            assert accepted == []
            task.run(challenge)
            assert accepted == [(instance, challenge)]
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
assert set(app.tasks)=={'privacytrace.execute.v1','privacytrace.health.v1'}
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


def test_worker_app_binds_the_message_preserving_log_formats():
    """The formats handed to Celery must be the ones that keep %(message)s (#179).

    The rendering contract lives in test_runtime_worker_logging.py, which needs no
    celery; this case only pins the binding to app.conf.
    """

    instance = str(uuid4())
    app = create_worker_app(BrokerConfig("redis://u:p@127.0.0.1:1/15", instance))
    try:
        assert app.conf.worker_task_log_format == WORKER_TASK_LOG_FORMAT
        assert app.conf.worker_log_format == WORKER_LOG_FORMAT
    finally:
        app.close()


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (None, "EXECUTION_NOT_ACQUIRED"),
        (LeaseLost("secret capability payload"), "LEASE_LOST"),
        (PostgresOperationUnavailable("secret database URL"), "STORAGE_UNAVAILABLE"),
        (OSError("secret private path"), "RUNTIME_IO_UNAVAILABLE"),
        (ValueError("secret task input"), "RUNTIME_INPUT_INVALID"),
    ],
)
def test_consumer_emits_only_fixed_diagnostic_without_private_exception_text(
    monkeypatch, caplog, failure, code
):
    from privacytrace import runtime_worker

    instance = str(uuid4())
    event = {
        "version": 1,
        "event_type": "privacytrace.job.ready",
        "instance_id": instance,
        "job_id": "safe-job",
        "event_id": str(uuid4()),
    }
    closed = []
    store = SimpleNamespace(
        uses_postgres=True,
        instance_id=instance,
        close=lambda: closed.append(True),
    )

    class FakeExecution:
        def __init__(self, owner):
            assert owner is store

        def acquire(self, message, *, lease_seconds):
            assert message == event and lease_seconds == 60
            if failure is not None:
                raise failure
            return None

    monkeypatch.setenv("PRIVACYTRACE_STORE_ROOT", "/isolated-test-material")
    monkeypatch.delenv("PRIVACYTRACE_LEASE_SECONDS", raising=False)
    monkeypatch.setattr(runtime_worker, "ensure_control_plane", lambda: None)
    monkeypatch.setattr(runtime_worker, "create_store", lambda _: store)
    monkeypatch.setattr(runtime_worker, "PostgresExecution", FakeExecution)
    with caplog.at_level(logging.WARNING, logger="privacytrace.runtime_worker"):
        runtime_worker.execute(event, SimpleNamespace(instance_id=instance))
    assert closed == [True]
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.name == "privacytrace.runtime_worker"
    ]
    assert messages == ["privacytrace.worker." + code]
    assert "secret" not in caplog.text
    assert instance not in caplog.text and event["event_id"] not in caplog.text


def test_independent_worker_apps_do_not_share_captured_instance_config(monkeypatch):
    from privacytrace import runtime_health, runtime_worker

    executed, acknowledged = [], []
    monkeypatch.setattr(
        runtime_worker, "execute", lambda message, config: executed.append(config.instance_id)
    )
    monkeypatch.setenv("PRIVACYTRACE_PUBLISH_HEALTH", "1")
    monkeypatch.setattr(
        runtime_health,
        "acknowledge_challenge",
        lambda url, instance, challenge: acknowledged.append(instance),
    )
    apps = []
    try:
        for _ in range(6):
            instance = str(uuid4())
            app = runtime_worker.create_worker_app(
                BrokerConfig("redis://u:p@127.0.0.1:1/15", instance)
            )
            apps.append(app)
            event = {
                "version": 1,
                "event_type": "privacytrace.job.ready",
                "instance_id": instance,
                "job_id": "registration-only",
                "event_id": str(uuid4()),
            }
            challenge = {
                "version": 1,
                "instance_id": instance,
                "challenge_id": str(uuid4()),
                "issued_at": 12345,
            }
            for name, payload, request_id in (
                (TASK_NAME, event, event["event_id"]),
                (PROBE_TASK_NAME, challenge, challenge["challenge_id"]),
            ):
                task = app.tasks[name]
                task.push_request(id=request_id)
                try:
                    task.run(payload)
                finally:
                    task.pop_request()
            assert executed[-1:] == [instance], "Consumer captured another app's config"
            assert acknowledged[-1:] == [instance], "Health task captured another app's config"
    finally:
        for app in apps:
            app.close()
