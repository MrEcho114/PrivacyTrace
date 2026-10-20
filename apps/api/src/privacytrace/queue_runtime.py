"""Fixed Celery/Redis publication after a committed PostgreSQL outbox claim.

Redis is transport, never the job ledger. This module publishes identifiers only;
an execution consumer must acquire a database lease before doing any work.
"""

import argparse
import json
import os
import re
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

from .postgres_outbox import PostgresOutbox, decode_message

TASK_NAME = "privacytrace.execute.v1"
PROBE_TASK_NAME = "privacytrace.health.v1"


class QueueUnavailable(RuntimeError):
    """Fixed, non-secret transport failure; never chain a credential-bearing DSN."""


@dataclass(frozen=True)
class BrokerConfig:
    url: str = field(repr=False)
    instance_id: str
    visibility_seconds: int = 300

    def __post_init__(self):
        try:
            if type(self.instance_id) is not str or str(UUID(self.instance_id)) != self.instance_id:
                raise ValueError
            if type(self.url) is not str or len(self.url) > 2048:
                raise ValueError
            parsed = urlsplit(self.url)
            port = parsed.port if parsed.port is not None else 6379
            if (
                parsed.scheme not in {"redis", "rediss"}
                or not parsed.hostname
                or not parsed.username
                or not parsed.password
                or not unquote(parsed.username).strip()
                or not unquote(parsed.password).strip()
                or not 1 <= port <= 65535
                or parsed.query
                or parsed.fragment
                or not re.fullmatch(r"/(?:[0-9]|1[0-5])", parsed.path)
                or type(self.visibility_seconds) is not int
                or not 10 <= self.visibility_seconds <= 3600
            ):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid authenticated Redis runtime configuration") from None

    @property
    def queue(self):
        return f"privacytrace.{self.instance_id}"

    @property
    def key_prefix(self):
        return f"pt80:{self.instance_id}:"


def create_celery_app(config):
    """Internal application factory; credentials are boot configuration only."""
    try:
        from celery import Celery
        from kombu import Exchange, Queue
    except ImportError:
        raise ValueError("The runtime optional dependency group is required") from None

    app = Celery("privacytrace_runtime", broker=config.url, set_as_current=False)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        result_accept_content=["json"],
        result_backend=None,
        task_ignore_result=True,
        task_store_errors_even_if_ignored=False,
        task_default_queue=config.queue,
        task_default_exchange=config.queue,
        task_default_routing_key=config.queue,
        task_queues=(
            Queue(
                config.queue,
                exchange=Exchange(config.queue, type="direct", durable=True),
                routing_key=config.queue,
                durable=True,
            ),
        ),
        task_routes={
            n: {"queue": config.queue, "routing_key": config.queue}
            for n in (TASK_NAME, PROBE_TASK_NAME)
        },
        task_create_missing_queues=False,
        task_protocol=2,
        task_publish_retry=False,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_enable_remote_control=False,
        worker_send_task_events=False,
        task_send_sent_event=False,
        broker_connection_timeout=2,
        broker_connection_retry_on_startup=True,
        broker_pool_limit=1,
        broker_transport_options={
            "global_keyprefix": config.key_prefix,
            "visibility_timeout": config.visibility_seconds,
            "socket_timeout": 2,
            "socket_connect_timeout": 2,
            "retry_on_timeout": False,
            "max_connections": 4,
        },
        visibility_timeout=config.visibility_seconds,
        result_backend_transport_options={"visibility_timeout": config.visibility_seconds},
        enable_utc=True,
        broker_use_ssl=(
            {"ssl_cert_reqs": ssl.CERT_REQUIRED, "ssl_check_hostname": True}
            if urlsplit(config.url).scheme == "rediss"
            else None
        ),
    )
    return app


class CeleryPublisher:
    def __init__(self, config):
        self.config = config
        self.app = create_celery_app(config)

    def publish(self, message):
        from kombu.exceptions import KombuError
        from redis.exceptions import RedisError

        message = decode_message(message)
        if message["instance_id"] != self.config.instance_id:
            raise ValueError("Queue instance does not match the event")
        try:
            self.app.send_task(
                TASK_NAME,
                args=[message],
                kwargs={},
                task_id=message["event_id"],
                queue=self.config.queue,
                routing_key=self.config.queue,
                serializer="json",
                retry=False,
                ignore_result=True,
                argsrepr="(job event identifiers)",
                kwargsrepr="{}",
            )
        except (KombuError, RedisError, OSError):
            raise QueueUnavailable("Runtime broker unavailable") from None

    def probe(self):
        from .runtime_health import issue_challenge, release_challenge

        try:
            challenge = issue_challenge(
                self.config.url, self.config.instance_id, self.config.key_prefix + self.config.queue
            )
            if challenge is None:
                return False
            self.app.send_task(
                PROBE_TASK_NAME,
                args=[challenge],
                kwargs={},
                task_id=challenge["challenge_id"],
                queue=self.config.queue,
                routing_key=self.config.queue,
                serializer="json",
                retry=False,
                ignore_result=True,
                expires=15,
                argsrepr="(fixed health challenge)",
                kwargsrepr="{}",
            )
            return True
        except Exception:
            if "challenge" in locals() and challenge:
                try:
                    release_challenge(self.config.url, challenge)
                except Exception:
                    pass
            raise QueueUnavailable("Runtime health probe unavailable") from None

    def close(self):
        self.app.close()


class OutboxDispatcher:
    def __init__(self, store, publisher):
        if store.instance_id != publisher.config.instance_id:
            raise ValueError("Outbox and queue instances differ")
        self.events = PostgresOutbox(store)
        self.publisher = publisher

    def once(self, *, limit=10):
        # claim() owns and commits its short transaction before any network I/O.
        claimed = self.events.claim(limit=limit, visibility_seconds=30)
        result = {"published": 0, "failed": 0, "unconfirmed": 0}
        for event in claimed:
            token = str(event.claim_token)
            try:
                self.publisher.publish(event.message)
            except QueueUnavailable:
                self.events.fail(
                    str(event.event_id),
                    token,
                    code="BROKER_UNAVAILABLE",
                    retry_delay_seconds=min(60, 2 ** (event.attempts - 1)),
                )
                result["failed"] += 1
            else:
                # Publication can succeed before a lost DB acknowledgement. Do
                # not delete that event or claim exactly-once execution.
                result["published"] += 1
                if not self.events.acknowledge(str(event.event_id), token):
                    result["unconfirmed"] += 1
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    store = publisher = heartbeat = None
    last_probe = 0.0
    try:
        from .durable_intake import ensure_control_plane
        from .postgres_execution import PostgresExecution
        from .runtime_health import HealthPublisher
        from .storage_factory import create_store, resolve_redis_url

        ensure_control_plane()
        if os.environ.get("PRIVACYTRACE_STORAGE") != "postgres":
            raise ValueError("Durable dispatch requires PostgreSQL")
        store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
        config = BrokerConfig(resolve_redis_url(), store.instance_id)
        publisher = CeleryPublisher(config)
        dispatcher = OutboxDispatcher(store, publisher)
        if os.environ.get("PRIVACYTRACE_PUBLISH_HEALTH") == "1":
            heartbeat = HealthPublisher(config.url, store.instance_id, "dispatcher")
        while True:
            if heartbeat:
                heartbeat.beat()
                if not args.once and time.monotonic() - last_probe >= 8:
                    try:
                        publisher.probe()
                    except QueueUnavailable:
                        pass
                    last_probe = time.monotonic()
            PostgresExecution(store).recover()
            result = dispatcher.once()
            if args.once:
                print(json.dumps(result))
                return 0
            time.sleep(1)
    except (ValueError, OSError, KeyError, QueueUnavailable):
        print(json.dumps({"error": "RUNTIME_DISPATCH_UNAVAILABLE"}))
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if heartbeat:
            heartbeat.close()
        if publisher:
            publisher.close()
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
