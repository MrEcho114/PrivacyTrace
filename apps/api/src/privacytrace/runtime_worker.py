"""Fixed Celery consumer: PostgreSQL lease, original pipeline, private runner."""

import json
import logging
import os
from pathlib import Path
from threading import Event, Thread

from .durable_intake import DurableWebIntake, ensure_control_plane
from .postgres_execution import LeaseLost, PostgresExecution
from .postgres_outbox import _bounded, decode_message
from .postgres_store import PostgresOperationUnavailable
from .queue_runtime import TASK_NAME, BrokerConfig, create_celery_app
from .runtime_tls import RuntimeUnavailable
from .storage_factory import create_store


_LOG = logging.getLogger(__name__)
# Diagnostics use fixed labels; never include exception strings, IDs or task input.
_DIAGNOSTIC_CODES = frozenset(
    {
        "EXECUTION_NOT_ACQUIRED",
        "LEASE_LOST",
        "STORAGE_UNAVAILABLE",
        "RUNTIME_IO_UNAVAILABLE",
        "RUNTIME_INPUT_INVALID",
        "RUNNER_UNAVAILABLE",
        "LEASE_HEARTBEAT_UNAVAILABLE",
        "TERMINAL_EVENT_UNAVAILABLE",
    }
)


def _diagnostic(code):
    if code not in _DIAGNOSTIC_CODES:
        raise ValueError("Unknown runtime diagnostic code")
    _LOG.warning("privacytrace.worker.%s", code)


def execute(message, config):
    message = decode_message(message)
    if message["instance_id"] != config.instance_id:
        return
    ensure_control_plane()
    store = intake = lease = None
    stopping, heartbeat_failed = Event(), Event()
    thread = None
    try:
        store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
        if not getattr(store, "uses_postgres", False) or store.instance_id != config.instance_id:
            raise ValueError("Runtime worker instance configuration rejected")
        execution = PostgresExecution(store)
        lease_seconds = _bounded(int(os.environ.get("PRIVACYTRACE_LEASE_SECONDS", "60")), 5, 300)
        lease = execution.acquire(message, lease_seconds=lease_seconds)
        if lease is None:
            _diagnostic("EXECUTION_NOT_ACQUIRED")
            return

        def heartbeat():
            while not stopping.wait(min(5, lease_seconds / 3)):
                try:
                    execution.heartbeat(lease, lease_seconds=lease_seconds)
                except LeaseLost:
                    _diagnostic("LEASE_LOST")
                    heartbeat_failed.set()
                    return
                except PostgresOperationUnavailable:
                    _diagnostic("STORAGE_UNAVAILABLE")
                    heartbeat_failed.set()
                    return
                except (ValueError, OSError):
                    _diagnostic("LEASE_HEARTBEAT_UNAVAILABLE")
                    heartbeat_failed.set()
                    return

        thread = Thread(target=heartbeat, name="privacytrace-lease", daemon=True)
        thread.start()
        intake = DurableWebIntake(store)
        try:
            intake.execute(lease)
        except LeaseLost:
            _diagnostic("LEASE_LOST")
            return
        except RuntimeUnavailable:
            _diagnostic("RUNNER_UNAVAILABLE")
            if not heartbeat_failed.is_set():
                execution.retry(lease, code="RUNNER_UNAVAILABLE")
        except (ValueError, OSError, KeyError, TypeError):
            _diagnostic("RUNTIME_INPUT_INVALID")
            if not heartbeat_failed.is_set():
                job = store.get(lease.job_id)
                job.state = "FAILED"
                job.error = json.dumps(
                    {"code": "RUNTIME_INPUT_INVALID", "message": "Runtime input rejected"}
                )
                execution.fenced_store(lease).save_job(job)
    except PostgresOperationUnavailable:
        # Uncertain DB commits are recovered from the ledger, not exception text.
        _diagnostic("STORAGE_UNAVAILABLE")
        return
    except LeaseLost:
        _diagnostic("LEASE_LOST")
        return
    except OSError:
        _diagnostic("RUNTIME_IO_UNAVAILABLE")
        return
    except (ValueError, KeyError):
        _diagnostic("RUNTIME_INPUT_INVALID")
        return
    finally:
        stopping.set()
        if thread:
            thread.join(timeout=20)
        if intake:
            try:
                intake.terminal_event(lease)
            except PostgresOperationUnavailable:
                _diagnostic("STORAGE_UNAVAILABLE")
            except LeaseLost:
                _diagnostic("LEASE_LOST")
            except (ValueError, KeyError, OSError):
                _diagnostic("TERMINAL_EVENT_UNAVAILABLE")
            intake.close()
        if store:
            store.close()


def create_worker_app(config):
    app = create_celery_app(config)

    @app.task(
        name=TASK_NAME,
        bind=True,
        acks_late=True,
        reject_on_worker_lost=True,
        ignore_result=True,
        max_retries=0,
    )
    def task(self, *args, **kwargs):
        request = self.request
        canvas = any(
            getattr(request, name, None) for name in ("callbacks", "errbacks", "chain", "chord")
        )
        # Clear before return: Celery must not run embedded canvas instructions
        # even when a broker-authorized client crafts an invalid message.
        for name in ("callbacks", "errbacks", "chain", "chord"):
            setattr(request, name, None)
        if canvas or len(args) != 1 or kwargs:
            return
        try:
            message = decode_message(args[0])
            if request.id != message["event_id"]:
                return
            execute(message, config)
        except (ValueError, TypeError, KeyError):
            return

    app.finalize()
    for name in list(app.tasks):
        if name != TASK_NAME:
            del app.tasks[name]
    app.conf.update(
        worker_hijack_root_logger=False,
        worker_redirect_stdouts=False,
        worker_task_log_format="[privacytrace runtime task %(levelname)s]",
        worker_log_format="[privacytrace runtime %(levelname)s]",
    )
    return app


def main():
    app = None
    try:
        ensure_control_plane()
        if os.environ.get("PRIVACYTRACE_STORAGE") != "postgres":
            raise ValueError
        config = BrokerConfig(
            os.environ["PRIVACYTRACE_BROKER_URL"], os.environ["PRIVACYTRACE_INSTANCE_ID"]
        )
        store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
        try:
            if store.instance_id != config.instance_id:
                raise ValueError("Runtime worker instance configuration rejected")
            intake = DurableWebIntake(store)
            intake.close()
        finally:
            store.close()
        app = create_worker_app(config)
        worker = app.Worker(
            pool="solo",
            concurrency=1,
            queues=[config.queue],
            quiet=True,
            without_mingle=True,
            without_gossip=True,
            without_heartbeat=True,
            loglevel="CRITICAL",
        )
        worker.start()
        return 0
    except KeyboardInterrupt:
        return 0
    except (KeyError, ValueError, OSError):
        print('{"error":"RUNTIME_WORKER_UNAVAILABLE"}')
        return 1
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
