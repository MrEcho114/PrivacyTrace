"""Short-lived Redis role heartbeats and bounded dedicated mTLS runner health."""
import os
from uuid import UUID

from redis import Redis, RedisError

from .runtime_tls import PrivateClient, RuntimeTLS, RuntimeUnavailable
from .storage_factory import resolve_secret

TTL_SECONDS = 20


def health_key(instance_id, role):
    instance = str(UUID(instance_id))
    if instance != instance_id or role not in {"worker", "dispatcher"}:
        raise ValueError("Invalid runtime health identity")
    return f"privacytrace:health:{instance}:{role}"


class HealthPublisher:
    def __init__(self, broker_url, instance_id, role):
        self.key = health_key(instance_id, role)
        self.client = Redis.from_url(broker_url, socket_connect_timeout=2, socket_timeout=2)

    def beat(self):
        try:
            return self.client.set(self.key, b"alive", ex=TTL_SECONDS) is True
        except (RedisError, OSError, ValueError):
            return False

    def close(self):
        self.client.close()


def check_runtime_readiness(instance_id):
    try:
        # A dedicated GET/TTL-only Redis ACL account is used by the API.
        if os.environ.get("PRIVACYTRACE_HEALTH_REDIS_URL"):
            return False
        url = resolve_secret(
            "PRIVACYTRACE_HEALTH_REDIS_URL", "PRIVACYTRACE_HEALTH_REDIS_URL_FILE"
        )
        if not url:
            return False
        for role in ("worker", "dispatcher"):
            health_key(instance_id, role)
        client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        try:
            for role in ("worker", "dispatcher"):
                remaining = client.ttl(health_key(instance_id, role))
                if type(remaining) is not int or not 0 < remaining <= TTL_SECONDS:
                    return False
        finally:
            client.close()
        runner = PrivateClient(
            os.environ["PRIVACYTRACE_RUNNER_URL"],
            RuntimeTLS.from_env("PRIVACYTRACE_CONTROL_TLS"),
            timeout=2,
        )
        return runner.json("/v1/health") == {
            "version": 1,
            "status": "ready",
            "image_id": os.environ["PRIVACYTRACE_RUNNER_IMAGE_ID"],
        }
    except (
        RedisError, RuntimeUnavailable, OSError, KeyError, ValueError, TypeError,
        AttributeError,
    ):
        return False
