"""Deployment behavior and regressions; no APK or external model inputs."""

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import yaml

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))
from audit_context import audit  # noqa: E402
from bootstrap import (  # noqa: E402
    EXPECTED_TABLES,
    resolve_migration_url,
    run_bootstrap,
    validate_migrator_role,
)
from preflight import _build_synthetic_config, validate  # noqa: E402
from privacytrace.storage_factory import (  # noqa: E402
    create_store,
    resolve_redis_url,
)
from probe import probe  # noqa: E402
from serve import ProductionSurface, SmokeSurface, configure, create_app  # noqa: E402


class PackagedResourceTests(unittest.TestCase):
    def test_real_api_resources_and_transport_guards(self):
        from starlette.testclient import TestClient

        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(
                os.environ,
                {"PT_DEPLOY_MODE": "smoke", "PRIVACYTRACE_STORE_ROOT": root},
                clear=True,
            ),
        ):
            with TestClient(create_app(), base_url="https://privacytrace.test") as client:
                self.assertEqual(client.get("/api/v1/health").json()["mode"], "remote")
                self.assertEqual(client.get("/api/v1/taxonomy").status_code, 200)
                self.assertIs(client.get("/api/v1/demo/report").json()["demo"], True)
                self.assertEqual(
                    client.get("/api/v1/health", headers={"Host": "evil.test"}).status_code, 400
                )
                self.assertEqual(
                    client.get(
                        "/api/v1/health", headers={"X-Forwarded-For": "203.0.113.1"}
                    ).status_code,
                    400,
                )
                self.assertEqual(
                    client.get("/api/v1/health", headers={"X-PrivacyTrace-Local": "1"}).status_code,
                    403,
                )


class StartupTests(unittest.TestCase):
    def test_smoke_only_proxy_has_an_edge_network_and_loopback_port(self):
        config = yaml.safe_load((DEPLOY / "compose.smoke.yaml").read_text(encoding="utf-8"))
        self.assertTrue(config["networks"]["private"]["internal"])
        self.assertFalse(config["networks"]["edge"].get("internal", False))
        self.assertEqual(config["services"]["api"]["networks"], ["private"])
        self.assertEqual(set(config["services"]["web"]["networks"]), {"edge", "private"})
        self.assertEqual(config["services"]["web"]["ports"], ["127.0.0.1:18081:8080"])

    def test_compose_tmpfs_options_stay_in_one_absolute_mount(self):
        for name in ("compose.yaml", "compose.smoke.yaml"):
            config = yaml.safe_load((DEPLOY / name).read_text(encoding="utf-8"))
            for service in config["services"].values():
                for mount in service.get("tmpfs", []):
                    self.assertTrue(mount.startswith("/"), mount)
                    self.assertIn(",noexec,nosuid,", mount)
                    self.assertIn(",uid=", mount)
                    self.assertIn(",gid=", mount)

    def test_isolated_configure_success_with_secret_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_file = Path(temp_dir) / "runtime_database_url"
            secret_file.write_text(
                "postgresql+psycopg://privacytrace_runtime:pass@127.0.0.1:5432/privacytrace_test\n"
            )

            with patch.dict(
                os.environ,
                {
                    "PT_DEPLOY_MODE": "isolated",
                    "PT_PUBLIC_BIND_IP": "127.0.0.1",
                    "PT_PUBLIC_HOST": "privacytrace.test",
                    "PRIVACYTRACE_STORAGE": "postgres",
                    "PRIVACYTRACE_INSTANCE_ID": "0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
                    "PRIVACYTRACE_DATABASE_URL_FILE": str(secret_file),
                },
                clear=True,
            ):
                host = configure()
                self.assertEqual(host, "privacytrace.test")
                self.assertEqual(os.environ["PRIVACYTRACE_MODE"], "remote")
                self.assertEqual(os.environ["PRIVACYTRACE_STORAGE"], "postgres")
                self.assertEqual(os.environ["PRIVACYTRACE_ALLOWED_HOSTS"], "privacytrace.test")

    def test_public_production_is_blocked_at_real_server_entry(self):
        with patch.dict(
            os.environ,
            {"PT_DEPLOY_MODE": "production", "PT_PUBLIC_HOST": "privacytrace.test"},
            clear=True,
        ), self.assertRaisesRegex(RuntimeError, "not authorized"):
            configure()

    def test_isolated_requires_actual_loopback_interface(self):
        for bad in ("0.0.0.0", "10.7.0.9", "::1", "bad"):
            with patch.dict(
                os.environ,
                {"PT_DEPLOY_MODE": "isolated", "PT_PUBLIC_BIND_IP": bad},
                clear=True,
            ), self.assertRaisesRegex(RuntimeError, "loopback"):
                configure()

    def test_production_configure_rejects_missing_instance_id_or_invalid_host(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_file = Path(temp_dir) / "runtime_database_url"
            secret_file.write_text(
                "postgresql+psycopg://privacytrace_runtime:pass@127.0.0.1:5432/privacytrace_test\n"
            )

            with patch.dict(
                os.environ,
                {
                    "PT_DEPLOY_MODE": "production",
                    "PT_PUBLIC_HOST": "privacytrace.test",
                    "PRIVACYTRACE_STORAGE": "postgres",
                    "PRIVACYTRACE_DATABASE_URL_FILE": str(secret_file),
                },
                clear=True,
            ), self.assertRaises(RuntimeError):
                configure()

            for bad_host in ("*", "privacytrace.test:8000", "evil\nnewline"):
                with patch.dict(
                    os.environ,
                    {
                        "PT_DEPLOY_MODE": "production",
                        "PT_PUBLIC_HOST": bad_host,
                        "PRIVACYTRACE_STORAGE": "postgres",
                        "PRIVACYTRACE_INSTANCE_ID": "0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
                        "PRIVACYTRACE_DATABASE_URL_FILE": str(secret_file),
                    },
                    clear=True,
                ):
                    with self.assertRaises(RuntimeError):
                        configure()

    def test_production_configure_rejects_inlined_plaintext_database_url(self):
        with patch.dict(
            os.environ,
            {
                "PT_DEPLOY_MODE": "isolated",
                "PT_PUBLIC_BIND_IP": "127.0.0.1",
                "PT_PUBLIC_HOST": "privacytrace.test",
                "PRIVACYTRACE_STORAGE": "postgres",
                "PRIVACYTRACE_INSTANCE_ID": "0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
                "PRIVACYTRACE_DATABASE_URL": "postgresql+psycopg://user:pass@host/db",
            },
            clear=True,
        ), self.assertRaisesRegex(RuntimeError, "Do not inline secret database URLs"):
            configure()

    def test_missing_or_misspelled_mode_cannot_enable_smoke(self):
        for env in ({}, {"PT_DEPLOY_MODE": "smkoe"}):
            with patch.dict(os.environ, env, clear=True), self.assertRaises(RuntimeError):
                configure()

    def test_smoke_rejects_real_storage_or_secrets_without_echoing_them(self):
        for key in (
            "PRIVACYTRACE_DATABASE_URL",
            "PRIVACYTRACE_MIGRATION_DATABASE_URL",
            "PRIVACYTRACE_DATABASE_URL_FILE",
            "PRIVACYTRACE_LLM_API_KEY",
        ):
            with patch.dict(
                os.environ, {"PT_DEPLOY_MODE": "smoke", key: "private-canary"}, clear=True
            ):
                with self.assertRaises(RuntimeError) as error:
                    configure()
                self.assertNotIn("private-canary", str(error.exception))
        with patch.dict(
            os.environ, {"PT_DEPLOY_MODE": "smoke", "PRIVACYTRACE_STORAGE": "postgres"}, clear=True
        ):
            with self.assertRaises(RuntimeError):
                configure()

    def test_smoke_overrides_local_and_proxy_trust(self):
        with patch.dict(
            os.environ,
            {
                "PT_DEPLOY_MODE": "smoke",
                "PRIVACYTRACE_MODE": "local",
                "PRIVACYTRACE_TRUSTED_PROXIES": "0.0.0.0/0",
            },
            clear=True,
        ):
            configure()
            self.assertEqual(os.environ["PRIVACYTRACE_MODE"], "remote")
            self.assertEqual(os.environ["PRIVACYTRACE_TRUSTED_PROXIES"], "")

    def test_wildcard_or_caddy_injection_host_rejected(self):
        for host in ("*", "foo:443", "foo\nrespond ok", "a{b}", "a/b"):
            with (
                patch.dict(
                    os.environ, {"PT_DEPLOY_MODE": "smoke", "PT_PUBLIC_HOST": host}, clear=True
                ),
                self.assertRaises(RuntimeError),
            ):
                configure()


class SmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []

        async def downstream(scope, receive, send):
            self.calls.append(scope["path"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        surface = SmokeSurface(downstream, "privacytrace.test")
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=surface, client=("127.0.0.1", 1234)),
            base_url="https://privacytrace.test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_writes_and_unknown_reads_never_reach_business_app(self):
        for method, path in (
            ("POST", "/api/v1/jobs"),
            ("DELETE", "/api/v1/jobs/a"),
            ("GET", "/api/v1/jobs"),
            ("GET", "/docs"),
            ("POST", "/api/v1/demo/report"),
        ):
            self.assertEqual((await self.client.request(method, path)).status_code, 503)
        self.assertEqual(self.calls, [])

    async def test_full_origin_checked_for_reads(self):
        for origin in (
            "https://evil.test",
            "http://privacytrace.test",
            "https://privacytrace.test:8443",
            "null",
        ):
            response = await self.client.get("/api/v1/taxonomy", headers={"Origin": origin})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])
        self.assertEqual(
            (
                await self.client.get(
                    "/api/v1/taxonomy", headers={"Origin": "https://privacytrace.test"}
                )
            ).status_code,
            200,
        )
        self.assertEqual(self.calls, ["/api/v1/taxonomy"])

    async def test_liveness_is_distinct_from_readiness(self):
        self.assertEqual((await self.client.get("/_health/live")).status_code, 200)
        self.assertEqual((await self.client.get("/_health/ready")).status_code, 503)
        self.assertEqual(self.calls, [])

    async def test_remote_peer_cannot_probe(self):
        transport = httpx.ASGITransport(app=self.client._transport.app, client=("10.0.0.2", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            self.assertEqual((await client.get("/_health/live")).status_code, 404)


class ContextTests(unittest.TestCase):
    def test_private_inputs_and_symlinks_rejected_without_names(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "private-canary.apk").write_bytes(b"synthetic, not an APK")
            with self.assertRaisesRegex(ValueError, "Unexpected file") as error:
                audit(root)
            self.assertNotIn("private-canary", str(error.exception))

    def test_registered_resource_is_an_allowed_build_input(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "rules").mkdir()
            (root / "rules/taxonomy.v0.3.json").write_text("{}")
            self.assertEqual(audit(root), 1)


class SevenServiceTopologyTests(unittest.TestCase):
    def setUp(self):
        self.compose_path = DEPLOY / "compose.yaml"
        self.raw_config = yaml.safe_load(self.compose_path.read_text(encoding="utf-8"))

    def test_compose_defines_exact_seven_services(self):
        services = self.raw_config["services"]
        expected = {"web", "api", "postgres", "redis", "worker", "dispatcher", "gateway"}
        long_lived = {name for name, spec in services.items() if not spec.get("profiles")}
        self.assertEqual(long_lived, expected)
        self.assertEqual(set(services) - long_lived, {"migrate", "reclaim"})
        self.assertEqual(services["migrate"]["profiles"], ["migration"])
        self.assertEqual(services["reclaim"]["profiles"], ["reclamation"])
        self.assertEqual(services["migrate"]["restart"], "no")
        self.assertEqual(services["reclaim"]["restart"], "no")

    def test_all_seven_services_enforce_hardened_isolation(self):
        for name, service in self.raw_config["services"].items():
            self.assertTrue(service.get("read_only"), f"Service '{name}' must have read_only: true")
            self.assertEqual(
                service.get("cap_drop"), ["ALL"], f"Service '{name}' must have cap_drop: [ALL]"
            )
            self.assertIn(
                "no-new-privileges:true",
                service.get("security_opt", []),
                f"Service '{name}' must enforce no-new-privileges",
            )
            self.assertTrue(service.get("init"), f"Service '{name}' must enable init process")
            self.assertLessEqual(
                service.get("pids_limit", 999), 128, f"Service '{name}' pids_limit must be <= 128"
            )

            user = str(service.get("user", ""))
            self.assertTrue(user, f"Service '{name}' must declare explicit non-root user")
            self.assertNotIn(
                user.split(":")[0], {"0", "root"}, f"Service '{name}' must not run as root"
            )

    def test_only_public_web_and_private_mtls_gateway_publish_ports(self):
        for name, service in self.raw_config["services"].items():
            ports = service.get("ports", [])
            if name == "web":
                published = set(
                    p if isinstance(p, str) else f"{p.get('published')}:{p.get('target')}"
                    for p in ports
                )
                self.assertTrue(
                    any("80" in p for p in published) and any("443" in p for p in published)
                )
            elif name == "gateway":
                self.assertEqual(len(ports), 1)
                self.assertIn("PT_GATEWAY_HOST_IP", str(ports[0]))
                self.assertIn(":8443:8443", str(ports[0]))
            else:
                self.assertEqual(ports, [], f"Internal service '{name}' must not publish ports")

    def test_zero_docker_socket_and_no_host_binds(self):
        for name, service in self.raw_config["services"].items():
            for v in service.get("volumes", []):
                v_str = v if isinstance(v, str) else f"{v.get('source')}:{v.get('target')}"
                self.assertNotIn(
                    "docker.sock", v_str, f"Service '{name}' must not mount docker.sock"
                )
                if isinstance(v, dict):
                    self.assertEqual(
                        v.get("type", "volume"),
                        "volume",
                        f"Service '{name}' must not use host bind mounts",
                    )
                elif isinstance(v, str):
                    self.assertFalse(
                        v.startswith(("/", ".")),
                        f"Service '{name}' volume {v} must be a named volume, not host path",
                    )

    def test_materials_volume_shared_correctly(self):
        services = self.raw_config["services"]
        for role in ("api", "worker", "dispatcher", "gateway"):
            vols = [
                v if isinstance(v, str) else v.get("source")
                for v in services[role].get("volumes", [])
            ]
            self.assertTrue(
                any("materials" in str(v) for v in vols),
                f"Service '{role}' must mount shared materials volume",
            )

    def test_reclaim_timer_is_one_shot_and_alerts_on_failure(self):
        units = DEPLOY.parent / "docs/deployment/systemd"
        service = (units / "privacytrace-reclaim.service").read_text(encoding="utf-8")
        timer = (units / "privacytrace-reclaim.timer").read_text(encoding="utf-8")
        self.assertIn("--profile reclamation run --rm --no-deps reclaim", service)
        self.assertIn("OnFailure=privacytrace-reclaim-failed.service", service)
        self.assertIn("OnCalendar=*:0/30", timer)
        self.assertNotIn("PRIVACYTRACE_DATABASE_URL=", service)

    def test_deletion_journal_uses_separate_named_volume(self):
        services = self.raw_config["services"]
        for role in ("api", "worker"):
            spec = services[role]
            self.assertIn(
                "deletion_journal:/var/lib/privacytrace-deletions",
                spec.get("volumes", []),
            )
            self.assertEqual(
                spec["environment"]["PRIVACYTRACE_DELETION_JOURNAL_ROOT"],
                "/var/lib/privacytrace-deletions",
            )
        self.assertIn("deletion_journal", self.raw_config["volumes"])

    def test_network_isolation_boundaries(self):
        networks = self.raw_config["networks"]
        self.assertTrue(networks["api"].get("internal"), "Network 'api' must be internal: true")
        self.assertTrue(
            networks["database"].get("internal"), "Network 'database' must be internal: true"
        )
        self.assertFalse(
            networks["edge"].get("internal", False), "Network 'edge' must be external bridge"
        )
        self.assertTrue(networks["control"].get("internal"))
        self.assertFalse(networks["control"].get("enable_ipv6", True))
        self.assertIn("PT_CONTROL_GATEWAY_IP", str(networks["control"]["ipam"]))

        services = self.raw_config["services"]
        self.assertNotIn(
            "database", services["web"]["networks"], "Web proxy must NEVER join database network"
        )
        self.assertIn("database", services["postgres"]["networks"])
        self.assertIn("database", services["redis"]["networks"])
        self.assertIn("database", services["worker"]["networks"])
        self.assertIn("database", services["dispatcher"]["networks"])
        self.assertIn("database", services["gateway"]["networks"])


class ProductionProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_ready_probe_does_not_block_ordinary_api_traffic(self):
        import asyncio
        import threading
        import time

        began = threading.Event()
        release = threading.Event()

        def slow_database(*_args):
            began.set()
            release.wait(timeout=1)
            return True, "0080_05"

        async def downstream(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        surface = ProductionSurface(downstream, "privacytrace.test")
        try:
            with (
                patch("serve.check_database_readiness", side_effect=slow_database),
                patch("privacytrace.runtime_health.check_runtime_readiness", return_value=True),
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=surface, client=("127.0.0.1", 1234)),
                    base_url="https://privacytrace.test",
                ) as client:
                    pending = asyncio.create_task(client.get("/_health/ready"))
                    self.assertTrue(await asyncio.to_thread(began.wait, 1))
                    start = time.monotonic()
                    self.assertEqual((await client.get("/api/v1/health")).status_code, 200)
                    self.assertLess(time.monotonic() - start, 0.5)
                    # A second concurrent probe refuses admission without
                    # creating a second blocking database probe.
                    self.assertEqual((await client.get("/_health/ready")).status_code, 503)
                    release.set()
                    self.assertEqual((await pending).status_code, 200)
        finally:
            release.set()

    async def test_health_timeout_fails_closed_without_unbounded_threads(self):
        import asyncio
        import threading

        entered = threading.Event()
        released = threading.Event()

        def blocked_db(*_args):
            entered.set()
            released.wait(timeout=6)
            return True, "0080_05"

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        surface = ProductionSurface(app, "privacytrace.test")
        try:
            with (
                patch("serve.check_database_readiness", side_effect=blocked_db),
                patch("privacytrace.runtime_health.check_runtime_readiness", return_value=True),
            ):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=surface, client=("127.0.0.1", 1234)),
                    base_url="https://privacytrace.test",
                ) as client:
                    probe = asyncio.create_task(client.get("/_health/ready"))
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    self.assertEqual((await probe).status_code, 503)
                    self.assertTrue(surface._ready_slot.locked())
                    self.assertEqual((await client.get("/_health/ready")).status_code, 503)
                    released.set()
                    for _ in range(50):
                        if not surface._ready_slot.locked():
                            break
                        await asyncio.sleep(0.01)
                    self.assertFalse(surface._ready_slot.locked())
                    self.assertEqual((await client.get("/_health/ready")).status_code, 200)
        finally:
            released.set()

    async def test_production_readiness_probe_success_with_revision_0080_05(self):
        async def downstream(scope, receive, send):
            pass

        with (
            patch("serve.check_database_readiness", return_value=(True, "0080_05")),
            patch("privacytrace.runtime_health.check_runtime_readiness", return_value=True),
        ):
            surface = ProductionSurface(downstream, "privacytrace.test")
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=surface, client=("127.0.0.1", 1234)),
                base_url="https://privacytrace.test",
            )
            async with client:
                res_live = await client.get("/_health/live")
                self.assertEqual(res_live.status_code, 200)
                self.assertEqual(res_live.json(), {"status": "live"})

                res_ready = await client.get("/_health/ready")
                self.assertEqual(res_ready.status_code, 200)
                self.assertEqual(res_ready.json(), {"status": "ready"})

    async def test_readiness_degrades_without_live_worker_and_runner(self):
        async def downstream(scope, receive, send):
            pass

        with (
            patch("serve.check_database_readiness", return_value=(True, "0080_05")),
            patch("privacytrace.runtime_health.check_runtime_readiness", return_value=False),
        ):
            surface = ProductionSurface(downstream, "privacytrace.test")
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=surface, client=("127.0.0.1", 1234)),
                base_url="https://privacytrace.test",
            ) as client:
                self.assertEqual((await client.get("/_health/ready")).status_code, 503)
                self.assertEqual((await client.get("/_health/live")).status_code, 200)

    async def test_production_readiness_probe_fails_when_db_down_or_unmigrated(self):
        async def downstream(scope, receive, send):
            pass

        with patch("serve.check_database_readiness", return_value=(False, "DB_CONNECTION_ERROR")):
            surface = ProductionSurface(downstream, "privacytrace.test")
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=surface, client=("127.0.0.1", 1234)),
                base_url="https://privacytrace.test",
            )
            async with client:
                res = await client.get("/_health/ready")
                self.assertEqual(res.status_code, 503)
                self.assertEqual(res.json(), {"status": "unavailable"})

        with patch("serve.check_database_readiness", return_value=(False, "REVISION_MISMATCH")):
            surface = ProductionSurface(downstream, "privacytrace.test")
            client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=surface, client=("127.0.0.1", 1234)),
                base_url="https://privacytrace.test",
            )
            async with client:
                res = await client.get("/_health/ready")
                self.assertEqual(res.status_code, 503)
                self.assertEqual(res.json(), {"status": "unavailable"})

    async def test_probe_denied_for_remote_peer_ip(self):
        async def downstream(scope, receive, send):
            pass

        surface = ProductionSurface(downstream, "privacytrace.test")
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=surface, client=("192.168.10.5", 1234)),
            base_url="https://privacytrace.test",
        )
        async with client:
            self.assertEqual((await client.get("/_health/live")).status_code, 404)
            self.assertEqual((await client.get("/_health/ready")).status_code, 404)

    def test_probe_cli_script_returns_appropriate_exit_codes(self):
        self.assertEqual(probe("unknown_kind"), 2)
        with patch.dict(os.environ, {"PT_API_PORT": "59999"}):
            self.assertEqual(probe("live"), 1)
            self.assertEqual(probe("ready"), 1)


class SecretFileResolutionTests(unittest.TestCase):
    def test_storage_factory_resolves_database_url_from_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_file = Path(temp_dir) / "runtime_db_secret"
            test_dsn = "postgresql+psycopg://privacytrace_runtime:supersecret@127.0.0.1:5432/privacytrace_test\n"
            secret_file.write_text(test_dsn, encoding="utf-8")

            with (
                patch.dict(
                    os.environ,
                    {
                        "PRIVACYTRACE_STORAGE": "postgres",
                        "PRIVACYTRACE_INSTANCE_ID": "0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
                        "PRIVACYTRACE_DATABASE_URL_FILE": str(secret_file),
                    },
                    clear=True,
                ),
                patch("privacytrace.postgres_store.PostgresJobStore") as mock_store,
            ):
                create_store(Path(temp_dir))
                mock_store.assert_called_once()
                args, _ = mock_store.call_args
                self.assertEqual(args[0], test_dsn.strip())
                self.assertEqual(args[1], "0163a8b5-3eed-481a-bfb0-31fd3fe523dc")

    def test_storage_factory_rejects_missing_or_empty_database_url_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "PRIVACYTRACE_STORAGE": "postgres",
                    "PRIVACYTRACE_INSTANCE_ID": "0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
                    "PRIVACYTRACE_DATABASE_URL_FILE": str(Path(temp_dir) / "nonexistent"),
                },
                clear=True,
            ):
                with self.assertRaises(ValueError):
                    create_store(Path(temp_dir))

            empty_file = Path(temp_dir) / "empty"
            empty_file.write_text("   \n\t", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "PRIVACYTRACE_STORAGE": "postgres",
                    "PRIVACYTRACE_INSTANCE_ID": "0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
                    "PRIVACYTRACE_DATABASE_URL_FILE": str(empty_file),
                },
                clear=True,
            ), self.assertRaises(ValueError):
                create_store(Path(temp_dir))

    def test_resolve_redis_url_from_file_and_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            secret_file = Path(temp_dir) / "redis_secret"
            secret_file.write_text("redis://:redispass@127.0.0.1:6379/1\n", encoding="utf-8")

            with patch.dict(
                os.environ, {"PRIVACYTRACE_REDIS_URL_FILE": str(secret_file)}, clear=True
            ):
                self.assertEqual(resolve_redis_url(), "redis://:redispass@127.0.0.1:6379/1")

            with patch.dict(
                os.environ, {"PRIVACYTRACE_BROKER_URL_FILE": str(secret_file)}, clear=True
            ):
                self.assertEqual(resolve_redis_url(), "redis://:redispass@127.0.0.1:6379/1")

            with patch.dict(
                os.environ,
                {"PRIVACYTRACE_REDIS_URL": "redis://:direct@127.0.0.1:6379/0"},
                clear=True,
            ):
                self.assertEqual(resolve_redis_url(), "redis://:direct@127.0.0.1:6379/0")

    def test_storage_factory_direct_env_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.dict(
                    os.environ,
                    {
                        "PRIVACYTRACE_STORAGE": "postgres",
                        "PRIVACYTRACE_INSTANCE_ID": "0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
                        "PRIVACYTRACE_DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
                    },
                    clear=True,
                ),
                patch("privacytrace.postgres_store.PostgresJobStore") as mock_store,
            ):
                create_store(Path(temp_dir))
                mock_store.assert_called_once()
                args, _ = mock_store.call_args
                self.assertEqual(args[0], "postgresql+psycopg://user:pass@localhost/db")


class ContextAndPreflightTests(unittest.TestCase):
    def test_audit_context_accepts_clean_layout_including_bootstrap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for path_str in (
                "package.json",
                "package-lock.json",
                "apps/api/pyproject.toml",
                "apps/api/uv.lock",
                "apps/api/alembic.ini",
                "apps/web/package.json",
                "apps/web/index.html",
                "apps/web/tsconfig.json",
                "apps/web/vite.config.ts",
                "rules/taxonomy.v0.3.json",
                "rules/sdk-signatures.v1.0.json",
                "samples/demo/evaluation-input.json",
                "deploy/Dockerfile",
                "deploy/serve.py",
                "deploy/probe.py",
                "deploy/bootstrap.py",
                "deploy/audit_context.py",
                "deploy/Caddyfile",
                "deploy/Caddyfile.common",
                "apps/web/public/fonts/NotoSansSC-Variable.woff2",
                "apps/web/public/fonts/NotoSerifSC-Variable.woff2",
                "apps/web/public/fonts/licenses/NotoSansSC-OFL.txt",
                "apps/web/public/fonts/licenses/NotoSerifSC-OFL.txt",
            ):
                p = root / path_str
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("{}", encoding="utf-8")

            (root / "apps/api/src/privacytrace").mkdir(parents=True, exist_ok=True)
            (root / "apps/api/src/privacytrace/main.py").write_text("# code", encoding="utf-8")
            (root / "apps/api/migrations").mkdir(parents=True, exist_ok=True)
            (root / "apps/api/migrations/env.py").write_text("# code", encoding="utf-8")
            (root / "apps/web/src").mkdir(parents=True, exist_ok=True)
            (root / "apps/web/src/App.vue").write_text("<template />", encoding="utf-8")

            count = audit(root)
            self.assertGreater(count, 20)

    def test_preflight_validates_seven_services_cleanly(self):
        config = _build_synthetic_config()
        validate(config)

    def test_preflight_rejects_public_ports_and_mode_override(self):
        base = _build_synthetic_config()
        for mode, bind in (("production", "127.0.0.1"), ("isolated", "0.0.0.0")):
            cfg = copy.deepcopy(base)
            cfg["services"]["api"]["environment"]["PT_DEPLOY_MODE"] = mode
            cfg["services"]["web"]["ports"][0]["host_ip"] = bind
            with self.assertRaises(ValueError):
                validate(cfg)

    def test_preflight_rejects_legacy_four_service_topology(self):
        config = _build_synthetic_config()
        for name in ("worker", "dispatcher", "gateway"):
            config["services"].pop(name)
        with self.assertRaisesRegex(ValueError, "Unexpected service topology"):
            validate(config)

    def test_preflight_rejects_unapproved_migration_service(self):
        config = _build_synthetic_config()
        config["services"]["migrate"] = copy.deepcopy(config["services"]["dispatcher"])
        with self.assertRaises(ValueError):
            validate(config)

    def test_runtime_roles_require_exact_control_network(self):
        base = _build_synthetic_config()
        for role in ("api", "worker"):
            for mutation in ("remove_control", "add_edge", "remove_database"):
                invalid = copy.deepcopy(base)
                networks = invalid["services"][role]["networks"]
                if mutation == "remove_control":
                    networks.remove("control")
                elif mutation == "add_edge":
                    networks.append("edge")
                else:
                    networks.remove("database")
                with self.subTest(role=role, mutation=mutation):
                    with self.assertRaisesRegex(ValueError, "network boundary changed"):
                        validate(invalid)

    def test_control_network_rejects_external_routing_and_nonrelay_runner(self):
        base = _build_synthetic_config()
        for mutation in (
            lambda c: c["networks"]["control"].update(internal=False),
            lambda c: c["networks"]["control"].update(enable_ipv6=True),
            lambda c: c["services"]["worker"]["environment"].update(
                PRIVACYTRACE_RUNNER_URL="https://10.77.0.9:8444"
            ),
        ):
            bad = copy.deepcopy(base)
            mutation(bad)
            with self.assertRaises(ValueError):
                validate(bad)

    def test_preflight_rejects_loopback_runner_and_placeholder_image(self):
        base = _build_synthetic_config()
        for target, invalid in (
            ("PRIVACYTRACE_RUNNER_URL", "https://127.0.0.1:8444"),
            ("PRIVACYTRACE_RUNNER_URL", "http://10.77.0.9:8444"),
            ("PRIVACYTRACE_RUNNER_IMAGE_ID", "sha256:" + "0" * 64),
            ("PRIVACYTRACE_RUNNER_IMAGE_ID", "sha256:invalid"),
        ):
            bad = copy.deepcopy(base)
            bad["services"]["worker"]["environment"][target] = invalid
            with self.assertRaises(ValueError):
                validate(bad)

    def test_preflight_rejects_public_gateway_or_bad_container_bind(self):
        base = _build_synthetic_config()
        for host, bind in (
            ("0.0.0.0", "172.29.98.10"),
            ("10.77.0.10", "0.0.0.0"),
            ("127.0.0.1", "172.29.98.10"),
        ):
            bad = copy.deepcopy(base)
            bad["services"]["gateway"]["ports"][0]["host_ip"] = host
            bad["services"]["gateway"]["environment"]["PRIVACYTRACE_GATEWAY_BIND"] = bind
            with self.assertRaises(ValueError):
                validate(bad)

    def test_preflight_requires_runner_identity_agreement(self):
        bad = _build_synthetic_config()
        bad["services"]["api"]["environment"]["PRIVACYTRACE_RUNNER_URL"] = (
            "https://172.29.98.2:8444"
        )
        with self.assertRaisesRegex(ValueError, "agree on fixed Runner"):
            validate(bad)

    def test_production_required_secrets_cannot_be_dropped(self):
        config = _build_synthetic_config()
        # Use the exact production secret contract, not historic smoke allowances.
        expected = {
            "api": {"runtime_database_url", "runtime_health_url", "material_key", "control_tls_ca",
                    "control_tls_cert", "control_tls_key"},
            "dispatcher": {"runtime_database_url", "runtime_broker_url"},
            "worker": {"runtime_database_url", "runtime_broker_url", "material_key",
                       "control_tls_ca", "control_tls_cert", "control_tls_key"},
            "gateway": {"runtime_database_url", "material_key", "gateway_tls_ca",
                        "gateway_tls_cert", "gateway_tls_key"},
        }
        for role, secrets in expected.items():
            config["services"][role]["secrets"] = [{"source": x} for x in sorted(secrets)]
        validate(config)
        for role, secrets in expected.items():
            for removed in secrets:
                mutated = copy.deepcopy(config)
                mutated["services"][role]["secrets"] = [
                    s for s in mutated["services"][role]["secrets"] if s["source"] != removed
                ]
                with self.subTest(role=role, missing=removed), self.assertRaises(ValueError):
                    validate(mutated)

    def test_reclamation_requires_one_shot_isolation(self):
        config = _build_synthetic_config()
        reclaim = copy.deepcopy(config["services"]["dispatcher"])
        reclaim.update(
            profiles=["reclamation"],
            command=["-m", "privacytrace.material_lifecycle", "--once"],
            environment={
                "PRIVACYTRACE_DATABASE_URL_FILE": "/run/secrets/runtime_database_url"
            },
            secrets=[{"source": "runtime_database_url"}],
        )
        config["services"]["reclaim"] = reclaim
        validate(config)
        for field, replacement in (
            ("profiles", []),
            ("networks", ["edge"]),
            ("command", ["-m", "privacytrace.queue_runtime"]),
        ):
            broken = copy.deepcopy(config)
            broken["services"]["reclaim"][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(broken)

    def test_preflight_mutation_attacks_are_rejected(self):
        base_config = _build_synthetic_config()

        mutations = [
            lambda c: c["services"]["api"].update(ports=[{"published": "8000", "target": 8000}]),
            lambda c: c["services"]["worker"].update(
                volumes=[
                    {
                        "type": "bind",
                        "source": "/var/run/docker.sock",
                        "target": "/var/run/docker.sock",
                    }
                ]
            ),
            lambda c: c["services"]["dispatcher"].update(user="0:0"),
            lambda c: c["services"]["gateway"].update(read_only=False),
            lambda c: c["services"]["api"].update(image="example.invalid/api:latest"),
            lambda c: c["networks"]["database"].update(internal=False),
            lambda c: c["services"]["web"]["networks"].append("database"),
            lambda c: c["services"]["api"]["environment"].update(
                PRIVACYTRACE_DATABASE_URL="postgresql://user:pass@host/db"
            ),
            lambda c: c["services"].pop("gateway"),
        ]

        for mutation in mutations:
            bad = copy.deepcopy(base_config)
            mutation(bad)
            with self.assertRaises(ValueError, msg="Unsafe deployment configuration was accepted"):
                validate(bad)


class DatabaseBootstrapTests(unittest.TestCase):
    def test_bootstrap_exempts_version_table_but_enforces_business_rls(self):
        def check_rows(rows):
            connection = MagicMock()

            def execute(sql, params=None):
                statement = str(sql)
                value = MagicMock()
                if "SELECT version_num" in statement:
                    value.scalar_one_or_none.return_value = "0080_05"
                elif "SELECT tablename" in statement:
                    value.scalars.return_value.all.return_value = list(EXPECTED_TABLES)
                elif "SELECT relname, relrowsecurity" in statement:
                    value.fetchall.return_value = rows
                elif "has_table_privilege" in statement:
                    value.scalar_one.return_value = True
                return value

            connection.execute.side_effect = execute
            connection.__enter__.return_value = connection
            engine = MagicMock()
            engine.connect.return_value = connection
            with (
                patch("bootstrap.sa.create_engine", return_value=engine),
                patch("bootstrap.command.upgrade"),
                patch("bootstrap.validate_migrator_role", return_value="privacytrace_migrator"),
                patch("privacytrace.durable_intake.ensure_control_plane"),
            ):
                return run_bootstrap("postgresql+psycopg://local-fixture")

        healthy = [(name, True, True) for name in EXPECTED_TABLES]
        self.assertEqual(
            check_rows(healthy + [("alembic_version", False, False)])["revision"], "0080_05"
        )
        name = sorted(EXPECTED_TABLES)[0]
        invalid = [(n, True, n != name) for n in EXPECTED_TABLES]
        with self.assertRaisesRegex(RuntimeError, "forced ROW LEVEL SECURITY"):
            check_rows(invalid + [("alembic_version", False, False)])

    def test_resolve_migration_url_from_file_and_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "migration_url"
            file_path.write_text(
                "postgresql+psycopg://privacytrace_migrator:pass@127.0.0.1:5432/privacytrace_test\n"
            )

            self.assertEqual(
                resolve_migration_url(file_path),
                "postgresql+psycopg://privacytrace_migrator:pass@127.0.0.1:5432/privacytrace_test",
            )

            with patch.dict(
                os.environ, {"PRIVACYTRACE_MIGRATION_DATABASE_URL_FILE": str(file_path)}, clear=True
            ):
                self.assertEqual(
                    resolve_migration_url(),
                    "postgresql+psycopg://privacytrace_migrator:pass@127.0.0.1:5432/privacytrace_test",
                )

            with patch.dict(
                os.environ,
                {
                    "PRIVACYTRACE_MIGRATION_DATABASE_URL": "postgresql+psycopg://privacytrace_migrator:pass2@127.0.0.1:5432/test"
                },
                clear=True,
            ):
                self.assertEqual(
                    resolve_migration_url(),
                    "postgresql+psycopg://privacytrace_migrator:pass2@127.0.0.1:5432/test",
                )

    def test_resolve_migration_url_rejects_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                resolve_migration_url()

    def test_validate_migrator_role_rejects_runtime_user(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar_one.return_value = "privacytrace_runtime"

        with self.assertRaisesRegex(ValueError, "not runtime credentials"):
            validate_migrator_role(mock_conn)

    def test_validate_migrator_role_rejects_superuser_or_bypassrls(self):
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = [
            MagicMock(scalar_one=MagicMock(return_value="privacytrace_migrator")),
            MagicMock(fetchone=MagicMock(return_value=(True, False, False, False))),
        ]

        with self.assertRaisesRegex(ValueError, "must not possess superuser"):
            validate_migrator_role(mock_conn)


if __name__ == "__main__":
    unittest.main()
