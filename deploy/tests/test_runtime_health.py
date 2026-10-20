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

    def test_gateway_unreachable_fails_closed_on_runner(self):
        from privacytrace.runner_service import RunnerHandler
        from privacytrace.runtime_tls import RuntimeUnavailable

        handler = object.__new__(RunnerHandler)
        handler.path = "/v1/health"
        gateway = MagicMock()
        gateway.json.side_effect = RuntimeUnavailable("private network unavailable")
        handler.server = SimpleNamespace(
            runner=SimpleNamespace(
                gateway=gateway,
                faulted=False,
                config=SimpleNamespace(image_id="sha256:" + "a" * 64),
            )
        )
        handler.authorized = MagicMock(return_value=True)
        handler.reply = MagicMock()
        handler.do_GET()
        handler.reply.assert_called_once_with(503, {"error": "RUNNER_UNAVAILABLE"})

    def test_challenge_replay_expiration_and_instance_binding(self):
        import time
        from uuid import uuid4

        from privacytrace.runtime_health import acknowledge_challenge

        challenge = {
            "version": 1, "instance_id": INSTANCE, "challenge_id": str(uuid4()),
            "issued_at": int(time.time()),
        }
        with patch("privacytrace.runtime_health._connect") as factory:
            factory.return_value.eval.side_effect = [1, 0]
            self.assertTrue(acknowledge_challenge("redis://unused", INSTANCE, challenge))
            self.assertFalse(acknowledge_challenge("redis://unused", INSTANCE, challenge))
            self.assertEqual(factory.return_value.eval.call_count, 2)
            self.assertFalse(acknowledge_challenge(
                "redis://unused", INSTANCE, {**challenge, "issued_at": challenge["issued_at"] - 30}
            ))
            self.assertFalse(acknowledge_challenge(
                "redis://unused", str(uuid4()), challenge
            ))
            self.assertEqual(factory.return_value.eval.call_count, 2)

    def test_offline_backlog_blocks_new_challenge(self):
        from privacytrace.runtime_health import issue_challenge

        with patch("privacytrace.runtime_health._connect") as factory:
            factory.return_value.llen.return_value = 1
            self.assertIsNone(issue_challenge("redis://unused", INSTANCE, "queue"))
            factory.return_value.set.assert_not_called()

    def test_busy_progress_requires_real_fenced_stage_and_expires_when_stalled(self):
        from privacytrace.runtime_health import BusyProgress

        progress = BusyProgress()
        self.assertFalse(progress.fresh())
        with patch("privacytrace.runtime_health.time.monotonic", return_value=100):
            progress.stage_committed()
            self.assertTrue(progress.fresh())
        with patch("privacytrace.runtime_health.time.monotonic", return_value=279):
            self.assertTrue(progress.fresh())
        with patch("privacytrace.runtime_health.time.monotonic", return_value=281):
            self.assertFalse(progress.fresh())
        # Background lease heartbeats do not call stage_committed().
        with patch("privacytrace.runtime_health.time.monotonic", return_value=282):
            self.assertFalse(progress.fresh())

    def test_expired_end_to_end_deadline_rejects_without_io(self):
        import time

        with patch("privacytrace.runtime_health._connect") as factory:
            self.assertFalse(check_runtime_readiness(INSTANCE, deadline=time.monotonic() - 1))
            factory.assert_not_called()

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
