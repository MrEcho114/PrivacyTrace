"""Short-lived Redis role heartbeats and bounded dedicated mTLS runner health."""
import os
import time
from threading import Lock
from uuid import UUID, uuid4

from .runtime_tls import PrivateClient, RuntimeTLS
from .storage_factory import resolve_secret

TTL_SECONDS = 20
CHALLENGE_SECONDS = 15
PENDING_SECONDS = 20


def _connect(url):
    # Deployment/smoke unit tests do not install Celery's optional Redis transport.
    # The actual worker/runtime image installs the locked runtime extra.
    from redis import Redis

    return Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def health_key(instance_id, role):
    instance = str(UUID(instance_id))
    if instance != instance_id or role not in {"dispatcher", "consumer", "busy"}:
        raise ValueError("Invalid runtime health identity")
    return f"privacytrace:health:{instance}:{role}"



def pending_key(instance_id):
    instance = str(UUID(instance_id))
    if instance != instance_id:
        raise ValueError("Invalid health challenge identity")
    return f"pt80:{instance}:health:pending"


def issue_challenge(broker_url, instance_id, broker_queue_key):
    """At most one probe can wait on the same real queue; never flood offline Redis."""
    client = _connect(broker_url)
    try:
        # Kombu uses the fixed global_keyprefix; never inspect/delete job bodies.
        if client.llen(broker_queue_key) != 0:
            return None
        issued_at, challenge_id = int(time.time()), str(uuid4())
        value = f"{challenge_id}:{issued_at}"
        if client.set(pending_key(instance_id), value, ex=PENDING_SECONDS, nx=True) is not True:
            return None
        return {"version": 1, "instance_id": instance_id,
                "challenge_id": challenge_id, "issued_at": issued_at}
    finally:
        client.close()


_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
"""
_ACK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('DEL', KEYS[1])
  redis.call('SET', KEYS[2], 'alive', 'EX', ARGV[2])
  return 1
end
return 0
"""


def release_challenge(broker_url, challenge):
    client = _connect(broker_url)
    try:
        return client.eval(
            _RELEASE, 1, pending_key(challenge["instance_id"]),
            f"{challenge['challenge_id']}:{challenge['issued_at']}",
        ) == 1
    finally:
        client.close()


def acknowledge_challenge(broker_url, instance_id, challenge):
    """Aged, replayed, cross-instance, or unsolicited challenges cannot refresh Ready."""
    try:
        if (
            type(challenge) is not dict
            or set(challenge) != {"version", "instance_id", "challenge_id", "issued_at"}
            or type(challenge["version"]) is not int
            or challenge["version"] != 1
            or challenge["instance_id"] != instance_id
            or type(challenge["issued_at"]) is not int
            or str(UUID(challenge["challenge_id"])) != challenge["challenge_id"]
            or not 0 <= time.time() - challenge["issued_at"] <= CHALLENGE_SECONDS
        ):
            return False
        client = _connect(broker_url)
        try:
            return client.eval(
                _ACK, 2, pending_key(instance_id), health_key(instance_id, "consumer"),
                f"{challenge['challenge_id']}:{challenge['issued_at']}", TTL_SECONDS,
            ) == 1
        finally:
            client.close()
    except (ValueError, KeyError, TypeError, OSError):
        return False



class BusyProgress:
    """Only fenced, committed business-stage transitions extend busy readiness.

    The runner scan has a bounded execution timeout; a stuck pipeline cannot
    indefinitely extend this proof using only independent lease renewals.
    """

    MAX_STAGE_AGE = 180

    def __init__(self):
        self._lock = Lock()
        self._last = None

    def stage_committed(self):
        with self._lock:
            self._last = time.monotonic()

    def fresh(self):
        with self._lock:
            return self._last is not None and 0 <= time.monotonic() - self._last <= (
                self.MAX_STAGE_AGE
            )


class HealthPublisher:
    def __init__(self, broker_url, instance_id, role):
        self.key = health_key(instance_id, role)
        self.client = _connect(broker_url)

    def beat(self):
        try:
            return self.client.set(self.key, b"alive", ex=TTL_SECONDS) is True
        except Exception:  # Fail closed; no exception may reveal a Redis credential.
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
        for role in ("dispatcher", "consumer", "busy"):
            health_key(instance_id, role)
        client = _connect(url)
        try:
            dispatcher_ttl = client.ttl(health_key(instance_id, "dispatcher"))
            if type(dispatcher_ttl) is not int or not 0 < dispatcher_ttl <= TTL_SECONDS:
                return False
            # Consumption is proven by the fixed task on the actual queue.
            # A live PostgreSQL lease proves the solo worker is legitimately busy.
            consumed = client.ttl(health_key(instance_id, "consumer"))
            busy = client.ttl(health_key(instance_id, "busy"))
            if not any(type(v) is int and 0 < v <= TTL_SECONDS for v in (consumed, busy)):
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
    except Exception:  # Readiness never propagates secret-bearing connection errors.
        return False
