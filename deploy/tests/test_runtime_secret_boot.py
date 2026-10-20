"""Regression tests for service entry points receiving broker credentials via Docker secrets."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class BrokerSecretEntrypoints(unittest.TestCase):
    def test_dispatcher_accepts_file_only_broker_url(self):
        from privacytrace import queue_runtime

        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "broker_url"
            url = "redis://runtime:example@broker:6379/0"
            secret.write_text(url + "\n", encoding="utf-8")
            store = MagicMock()
            store.instance_id = "0163a8b5-3eed-481a-bfb0-31fd3fe523dc"
            with (
                patch.dict(
                    os.environ,
                    {
                        "PRIVACYTRACE_STORAGE": "postgres",
                        "PRIVACYTRACE_STORE_ROOT": directory,
                        "PRIVACYTRACE_BROKER_URL_FILE": str(secret),
                    },
                    clear=True,
                ),
                patch.object(sys, "argv", ["queue_runtime", "--once"]),
                patch("privacytrace.durable_intake.ensure_control_plane"),
                patch("privacytrace.storage_factory.create_store", return_value=store),
                patch("privacytrace.postgres_execution.PostgresExecution"),
                patch.object(queue_runtime, "BrokerConfig") as broker_config,
                patch.object(queue_runtime, "CeleryPublisher"),
                patch.object(queue_runtime, "OutboxDispatcher") as dispatcher,
            ):
                dispatcher.return_value.once.return_value = {"published": 0}
                self.assertEqual(queue_runtime.main(), 0)
                broker_config.assert_called_once_with(url, store.instance_id)
                self.assertNotIn("PRIVACYTRACE_BROKER_URL", os.environ)

    def test_worker_accepts_file_only_broker_url(self):
        from privacytrace import runtime_worker

        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "broker_url"
            url = "redis://runtime:example@broker:6379/0"
            secret.write_text(url + "\n", encoding="utf-8")
            instance = "0163a8b5-3eed-481a-bfb0-31fd3fe523dc"
            store = MagicMock()
            store.instance_id = instance
            config = MagicMock(instance_id=instance, queue="privacytrace." + instance)
            with (
                patch.dict(
                    os.environ,
                    {
                        "PRIVACYTRACE_STORAGE": "postgres",
                        "PRIVACYTRACE_STORE_ROOT": directory,
                        "PRIVACYTRACE_INSTANCE_ID": instance,
                        "PRIVACYTRACE_BROKER_URL_FILE": str(secret),
                    },
                    clear=True,
                ),
                patch("privacytrace.runtime_worker.ensure_control_plane"),
                patch("privacytrace.runtime_worker.create_store", return_value=store),
                patch("privacytrace.runtime_worker.DurableWebIntake"),
                patch.object(runtime_worker, "BrokerConfig", return_value=config) as broker_config,
                patch.object(runtime_worker, "create_worker_app") as worker_app,
            ):
                self.assertEqual(runtime_worker.main(), 0)
                broker_config.assert_called_once_with(url, instance)
                worker_app.return_value.Worker.return_value.start.assert_called_once()
                self.assertNotIn("PRIVACYTRACE_BROKER_URL", os.environ)

    def test_missing_broker_file_is_rejected_without_secret_contents(self):
        from privacytrace.storage_factory import resolve_redis_url

        with patch.dict(
            os.environ, {"PRIVACYTRACE_BROKER_URL_FILE": "/missing/broker"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "PRIVACYTRACE_BROKER_URL_FILE"):
                resolve_redis_url()


if __name__ == "__main__":
    unittest.main()
