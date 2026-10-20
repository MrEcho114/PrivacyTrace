"""Role heartbeat and mTLS health checks use synthetic clients, not a real runner."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from privacytrace.runtime_health import (
    HealthPublisher,
    check_runtime_readiness,
    health_key,
)

INSTANCE = "0163a8b5-3eed-481a-bfb0-31fd3fe523dc"


class RuntimeHealthTests(unittest.TestCase):
    def test_role_heartbeat_has_ttl_and_canonical_instance(self):
        with patch("privacytrace.runtime_health._connect") as creator:
            creator.return_value.set.return_value = True
            sender = HealthPublisher("redis://127.0.0.1:6379/0", INSTANCE, "dispatcher")
            self.assertTrue(sender.beat())
            creator.return_value.set.assert_called_once_with(
                health_key(INSTANCE, "dispatcher"), b"alive", ex=20,
            )
            sender.close()
        with self.assertRaises(ValueError):
            health_key(INSTANCE, "unapproved")

    def test_reader_missing_secret_or_stale_role_blocks(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(check_runtime_readiness(INSTANCE))
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("privacytrace.runtime_health.resolve_secret", return_value="redis://test"),
            patch("privacytrace.runtime_health._connect") as client,
        ):
            client.return_value.ttl.side_effect = [12, -2, -2]
            self.assertFalse(check_runtime_readiness(INSTANCE))

    def test_runner_gateway_failure_and_recovery_change_health(self):
        from privacytrace.runner_service import RunnerHandler

        gateway = MagicMock()
        runner = SimpleNamespace(
            gateway=gateway,
            faulted=False,
            config=SimpleNamespace(image_id="sha256:" + "a" * 64),
        )
        handler = object.__new__(RunnerHandler)
        handler.path = "/v1/health"
        handler.server = SimpleNamespace(runner=runner)
        handler.authorized = MagicMock(return_value=True)
        handler.reply = MagicMock()

        for failure in (
            PermissionError("wrong certificate"),
            {"version": 1, "status": "unavailable"},
        ):
            gateway.json.reset_mock()
            handler.reply.reset_mock()
            gateway.json.side_effect = failure if isinstance(failure, Exception) else None
            gateway.json.return_value = failure
            handler.do_GET()
            handler.reply.assert_called_once_with(503, {"error": "RUNNER_UNAVAILABLE"})
            gateway.json.assert_called_once_with("/v1/health", timeout=0.7)

        gateway.json.side_effect = None
        gateway.json.return_value = {"version": 1, "status": "ready"}
        handler.reply.reset_mock()
        handler.do_GET()
        handler.reply.assert_called_once_with(
            200, {"version": 1, "status": "ready", "image_id": runner.config.image_id}
        )

    def test_consumer_stall_blocks_even_if_broker_process_is_alive(self):
        env = {"PRIVACYTRACE_RUNNER_URL": "https://172.29.98.1:8444"}
        with (
            patch.dict(os.environ, env, clear=True),
            patch("privacytrace.runtime_health.resolve_secret", return_value="redis://test"),
            patch("privacytrace.runtime_health._connect") as redis,
            patch("privacytrace.runtime_health.PrivateClient") as runner,
        ):
            # Redis and Dispatcher are alive; no Consumer task or active lease.
            redis.return_value.ttl.side_effect = [12, -2, -2]
            self.assertFalse(check_runtime_readiness(INSTANCE))
            runner.assert_not_called()

    def test_busy_lease_remains_healthy_when_consumer_is_running_long_task(self):
        env = {
            "PRIVACYTRACE_RUNNER_URL": "https://172.29.98.1:8444",
            "PRIVACYTRACE_RUNNER_IMAGE_ID": "sha256:" + "a" * 64,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("privacytrace.runtime_health.resolve_secret", return_value="redis://test"),
            patch("privacytrace.runtime_health._connect") as redis,
            patch("privacytrace.runtime_health.RuntimeTLS.from_env"),
            patch("privacytrace.runtime_health.PrivateClient") as runner,
        ):
            redis.return_value.ttl.side_effect = [12, -2, 12]
            runner.return_value.json.return_value = {
                "version": 1,
                "status": "ready",
                "image_id": env["PRIVACYTRACE_RUNNER_IMAGE_ID"],
            }
            self.assertTrue(check_runtime_readiness(INSTANCE))

    def test_reader_requires_real_runner_status_and_image(self):
        env = {
            "PRIVACYTRACE_RUNNER_URL": "https://172.29.98.1:8444",
            "PRIVACYTRACE_RUNNER_IMAGE_ID": "sha256:" + "a" * 64,
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch("privacytrace.runtime_health.resolve_secret", return_value="redis://test"),
            patch("privacytrace.runtime_health._connect") as client,
            patch("privacytrace.runtime_health.RuntimeTLS.from_env"),
            patch("privacytrace.runtime_health.PrivateClient") as runner,
        ):
            client.return_value.ttl.side_effect = [12, 12, -2]
            runner.return_value.json.return_value = {
                "version": 1, "status": "ready", "image_id": env["PRIVACYTRACE_RUNNER_IMAGE_ID"],
            }
            self.assertTrue(check_runtime_readiness(INSTANCE))
            client.return_value.ttl.side_effect = [12, -2, 12]
            runner.return_value.json.return_value["image_id"] = "sha256:" + "b" * 64
            self.assertFalse(check_runtime_readiness(INSTANCE))


if __name__ == "__main__":
    unittest.main()
