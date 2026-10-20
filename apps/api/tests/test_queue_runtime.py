"""Actual Redis processes and actual PostgreSQL; protocol-only cases are separate."""

import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import queued
from test_postgres_storage import store as store

from privacytrace.postgres_outbox import PostgresOutbox
from privacytrace.postgres_schema import outbox
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.queue_runtime import (
    PROBE_TASK_NAME,
    TASK_NAME,
    BrokerConfig,
    CeleryPublisher,
    OutboxDispatcher,
    QueueUnavailable,
)


def test_consumer_challenge_publishes_expiring_fixed_payload_on_same_queue(monkeypatch):
    from unittest.mock import MagicMock

    from privacytrace import queue_runtime, runtime_health

    instance = str(uuid4())
    config = BrokerConfig("redis://u:p@127.0.0.1:1/15", instance)
    app = MagicMock()
    challenge = {"version": 1, "instance_id": instance,
                 "challenge_id": str(uuid4()), "issued_at": 12345}
    monkeypatch.setattr(queue_runtime, "create_celery_app", lambda _: app)
    monkeypatch.setattr(runtime_health, "issue_challenge", lambda *args: challenge)
    publisher = CeleryPublisher(config)
    assert publisher.probe() is True
    call = app.send_task.call_args
    assert call.args == (PROBE_TASK_NAME,)
    assert call.kwargs["args"] == [challenge] and call.kwargs["kwargs"] == {}
    assert call.kwargs["task_id"] == challenge["challenge_id"]
    assert call.kwargs["queue"] == config.queue
    assert call.kwargs["routing_key"] == config.queue
    assert call.kwargs["ignore_result"] is True
    assert call.kwargs["expires"] == 15
    assert call.kwargs["retry"] is False
    publisher.close()


def test_health_challenge_with_real_redis_and_solo_celery_consumer(tmp_path):
    """Real subprocess Redis + Celery, isolated from application PostgreSQL.

    This is opt-in and exercises actual queue consumption, not task.run().
    """
    if os.environ.get("PRIVACYTRACE_REDIS_TESTS") != "1":
        pytest.skip("Opt in to isolated real Redis and Celery runtime tests")
    assert shutil.which("redis-server"), "redis-server required"
    instance = str(uuid4())
    broker = RedisProcess(tmp_path / "health_redis", instance)
    worker = publisher = None
    try:
        broker.start()
        publisher = CeleryPublisher(broker.config)
        assert publisher.probe() is True
        # No consumer: only one task may accumulate on the real business queue.
        assert publisher.probe() is False
        assert len(broker.entries()) == 1
        from privacytrace.runtime_health import health_key

        worker_code = """
import sys
from privacytrace.queue_runtime import BrokerConfig
from privacytrace.runtime_worker import create_worker_app
app=create_worker_app(BrokerConfig(sys.argv[1],sys.argv[2]))
worker=app.Worker(pool="solo",concurrency=1,queues=[app.conf.task_default_queue],
                  quiet=True,without_mingle=True,without_gossip=True,
                  without_heartbeat=True,loglevel="CRITICAL")
worker.start()
"""
        env = dict(os.environ, PRIVACYTRACE_PUBLISH_HEALTH="1")
        worker = subprocess.Popen(
            [sys.executable, "-B", "-c", worker_code, broker.config.url, instance],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if worker.poll() is not None:
                pytest.fail("Real solo Celery consumer exited before processing challenge")
            if broker.client.ttl(health_key(instance, "consumer")) > 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("Real solo Celery consumer did not confirm queued challenge")
        assert broker.client.ttl(health_key(instance, "consumer")) > 0
        # A second probe can be issued only after the first has been consumed.
        assert publisher.probe() is True
    finally:
        if worker is not None:
            worker.terminate()
            try:
                worker.wait(timeout=8)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        if publisher is not None:
            publisher.close()
        broker.close()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RedisProcess:
    """Test-owned process/config; no shared daemon or FLUSHDB/FLUSHALL."""

    def __init__(self, root, instance):
        import redis

        self.root, self.instance, self.port = root, instance, free_port()
        self.password = secrets.token_hex(24)
        self.admin_password = secrets.token_hex(24)
        self.username = "app_" + instance.replace("-", "")
        self.prefix = f"pt80:{instance}:"
        self.config = BrokerConfig(
            f"redis://{self.username}:{quote(self.password)}@127.0.0.1:{self.port}/15", instance
        )
        self.process = None
        root.mkdir(mode=0o700)
        self.path = root / "redis.conf"
        text = (
            f"bind 127.0.0.1\nport {self.port}\nprotected-mode yes\n"
            f'dir {root}\nsave ""\nappendonly yes\nappendfsync always\n'
            "maxmemory 64mb\nmaxmemory-policy noeviction\nloglevel warning\n"
            "user default off\n"
            f"user admin on >{self.admin_password} ~* &* +@all\n"
            f"user {self.username} on >{self.password} ~{self.prefix}* &{self.prefix}* "
            "+@read +@write +@connection +@pubsub +@scripting +@transaction -@admin -@dangerous "
            "+eval +evalsha +script|load +client|setname\n"
        )
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        self.admin = redis.Redis(
            host="127.0.0.1",
            port=self.port,
            db=15,
            username="admin",
            password=self.admin_password,
            socket_timeout=1,
            socket_connect_timeout=1,
        )
        self.client = redis.Redis.from_url(self.config.url, socket_timeout=2)

    def start(self):
        fd = os.open(self.root / "redis.log", os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "ab") as log:
            self.process = subprocess.Popen(
                [shutil.which("redis-server"), str(self.path)],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError("Owned Redis process failed to start")
            try:
                if self.admin.ping():
                    return
            except Exception:
                time.sleep(0.05)
        raise AssertionError("Owned Redis process did not become ready")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.admin.shutdown(nosave=True)
            self.process.wait(timeout=10)
        self.admin.connection_pool.disconnect()
        self.client.connection_pool.disconnect()

    def close(self):
        try:
            self.stop()
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.client.close()
            self.admin.close()

    def entries(self):
        raw = self.client.lrange(self.prefix + self.config.queue, 0, -1)
        result = []
        for item in raw:
            transport = json.loads(item)
            body = json.loads(base64.b64decode(transport["body"]))
            result.append((transport, body, item))
        return result


@pytest.fixture
def broker(store, tmp_path):
    if os.environ.get("PRIVACYTRACE_REDIS_TESTS") != "1":
        pytest.skip("Opt-in real Redis process + PostgreSQL runtime acceptance")
    assert shutil.which("redis-server"), "Real redis-server is required, not a broker double"
    try:
        import celery  # noqa: F401
        import redis  # noqa: F401
    except ImportError:
        pytest.fail("Install the runtime extra before real queue acceptance")
    value = RedisProcess(tmp_path / "redis_test", store.instance_id)
    try:
        value.start()
        yield value
    finally:
        value.close()


@pytest.fixture
def publisher(broker):
    value = CeleryPublisher(broker.config)
    yield value
    value.close()


def due(store, event_id):
    with store._transaction() as conn:
        conn.execute(
            outbox.update()
            .where(outbox.c.instance_id == store.instance_id, outbox.c.event_id == event_id)
            .values(available_at=sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'"))
        )


def test_real_publish_is_fixed_json_and_committed_delivery(store, broker, publisher):
    job = queued()
    job.sample_id = "private-policy-title-must-not-be-in-redis"
    event = PostgresOutbox(store).register(job, "a" * 64)
    assert OutboxDispatcher(store, publisher).once() == {
        "published": 1,
        "failed": 0,
        "unconfirmed": 0,
    }
    [(headers, body, raw)] = broker.entries()
    assert headers["content-type"] == "application/json"
    assert headers["headers"]["task"] == TASK_NAME
    assert headers["headers"]["id"] == str(event.event_id)
    assert body[0] == [event.message] and body[1] == {}
    assert all(value is None for value in body[2].values())
    for private in [job.sample_id, "a" * 64, broker.password, str(Path.cwd())]:
        assert private.encode() not in raw
    other = PostgresJobStore(store.engine.url, store.instance_id, store.root.parent.parent)
    try:
        assert PostgresOutbox(other).get(str(event.event_id)).state == "DELIVERED"
    finally:
        other.close()


def test_no_publication_from_an_uncommitted_or_rolled_back_job(store, broker, publisher):
    job = queued()
    with pytest.raises(RuntimeError, match="abort"):
        with store._transaction():
            PostgresOutbox(store).register(job)
            with pytest.raises(ValueError, match="standalone"):
                OutboxDispatcher(store, publisher).once()
            assert broker.entries() == []
            raise RuntimeError("abort")
    assert OutboxDispatcher(store, publisher).once()["published"] == 0
    assert broker.entries() == []


def test_real_broker_outage_preserves_event_then_recovers(store, broker, publisher, caplog):
    events = PostgresOutbox(store)
    event = events.register(queued())
    broker.stop()
    assert OutboxDispatcher(store, publisher).once()["failed"] == 1
    failed = events.get(str(event.event_id))
    assert failed.state == "PENDING" and failed.attempts == 1
    assert failed.last_error_code == "BROKER_UNAVAILABLE"
    assert broker.password not in caplog.text and broker.admin_password not in caplog.text
    broker.start()
    due(store, event.event_id)
    assert OutboxDispatcher(store, publisher).once()["published"] == 1
    assert events.get(str(event.event_id)).state == "DELIVERED"
    assert broker.entries()[0][1][0] == [event.message]


def test_real_aof_restart_retains_published_message(store, broker, publisher):
    event = PostgresOutbox(store).register(queued())
    assert OutboxDispatcher(store, publisher).once()["published"] == 1
    before = broker.entries()

    def setting(name):
        def text(value):
            return value.decode() if isinstance(value, bytes) else value

        return {text(k): text(v) for k, v in broker.admin.config_get(name).items()}[name]

    assert setting("appendonly") == "yes"
    assert setting("appendfsync") == "always"
    assert setting("maxmemory-policy") == "noeviction"
    broker.stop()
    broker.start()
    assert broker.entries() == before
    assert before[0][1][0] == [event.message]


def test_publish_without_ack_replays_after_claim_expiry(store, broker, publisher):
    events = PostgresOutbox(store)
    event = events.register(queued())
    first = events.claim()[0]
    publisher.publish(first.message)  # Deliberately omit the database acknowledgement.
    with store._transaction() as conn:
        conn.execute(
            outbox.update()
            .where(outbox.c.instance_id == store.instance_id, outbox.c.event_id == event.event_id)
            .values(claimed_until=sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'"))
        )
    assert OutboxDispatcher(store, publisher).once()["published"] == 1
    assert [body[0] for _, body, _ in broker.entries()] == [[event.message], [event.message]]
    assert not events.acknowledge(str(event.event_id), str(first.claim_token))
    # This proves at-least-once publication; no consumer/execution claim is made here.


@pytest.mark.parametrize("deleted", [False, True])
def test_cancelled_or_deleted_job_never_reaches_broker(store, broker, publisher, deleted):
    job = queued()
    event = PostgresOutbox(store).register(job)
    (store.delete if deleted else store.cancel)(job.id)
    assert OutboxDispatcher(store, publisher).once()["published"] == 0
    assert broker.entries() == []
    assert PostgresOutbox(store).get(str(event.event_id)).state == "DISCARDED"


def test_parallel_dispatchers_publish_one_copy_per_claim(store, broker):
    events = PostgresOutbox(store)
    expected = {str(events.register(queued()).event_id) for _ in range(8)}

    def dispatch(_):
        other = PostgresJobStore(store.engine.url, store.instance_id, store.root.parent.parent)
        transport = CeleryPublisher(broker.config)
        try:
            return OutboxDispatcher(other, transport).once(limit=4)
        finally:
            transport.close()
            other.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(dispatch, range(2)))
    assert sum(r["published"] for r in result) == 8
    ids = [h["headers"]["id"] for h, _, _ in broker.entries()]
    assert len(ids) == len(set(ids)) == 8 and set(ids) == expected


def test_real_acl_denies_other_instances_and_admin_commands(store, broker, publisher):
    import redis

    with pytest.raises(redis.exceptions.NoPermissionError):
        broker.client.set(f"pt80:{uuid4()}:private", "no")
    for command in [("CONFIG", "GET", "*"), ("FLUSHALL",), ("ACL", "LIST")]:
        with pytest.raises(redis.exceptions.NoPermissionError):
            broker.client.execute_command(*command)
    event = PostgresOutbox(store).register(queued())
    wrong = {**event.message, "instance_id": str(uuid4())}
    with pytest.raises(ValueError, match="instance"):
        publisher.publish(wrong)
    assert broker.entries() == []


def test_transport_has_no_backend_remote_control_or_non_json_content(broker, publisher):
    conf = publisher.app.conf
    assert conf.result_backend is None and conf.task_ignore_result
    assert conf.accept_content == ["json"] and conf.task_serializer == "json"
    assert not conf.worker_enable_remote_control and conf.worker_prefetch_multiplier == 1
    assert not conf.task_create_missing_queues and conf.task_acks_late
    assert conf.broker_transport_options["global_keyprefix"] == broker.prefix


def test_producer_errors_do_not_echo_broker_credentials(store, broker):
    broker.stop()
    publisher = CeleryPublisher(broker.config)
    try:
        event = PostgresOutbox(store).register(queued())
        with pytest.raises(QueueUnavailable) as failure:
            publisher.publish(event.message)
        assert str(failure.value) == "Runtime broker unavailable"
        assert failure.value.__cause__ is None
        assert broker.password not in repr(broker.config)
    finally:
        publisher.close()


@pytest.mark.parametrize(
    "url",
    [
        "amqp://u:p@localhost/0",
        "redis://localhost/0",
        "redis://u@localhost/0",
        "redis://u:p@localhost/16",
        "redis://u:p@localhost/not-a-db",
        "redis://u:p@localhost/0?credential_provider=untrusted.function",
        "redis://u:p@localhost:0/0",
        "redis://u:p@localhost/0#secret",
        None,
    ],
)
def test_protocol_only_rejects_unsafe_broker_configuration(url):
    with pytest.raises(ValueError, match="Invalid authenticated Redis"):
        BrokerConfig(url, str(uuid4()))


def test_protocol_only_canonical_instance_and_visibility_bounds():
    instance = str(uuid4())
    for value in [True, 0, 9, 3601, "30"]:
        with pytest.raises(ValueError):
            BrokerConfig("redis://u:p@localhost/0", instance, value)
    with pytest.raises(ValueError):
        BrokerConfig("redis://u:p@localhost/0", "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA")
    assert "p@" not in repr(BrokerConfig("rediss://u:p@localhost/0", instance))
