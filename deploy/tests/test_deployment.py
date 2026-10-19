"""Deployment behavior and regressions; no APK or external model inputs."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))
from audit_context import audit  # noqa: E402
from serve import SmokeSurface, configure, create_app  # noqa: E402


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
    def test_production_refuses_even_when_runtime_variables_are_present(self):
        with patch.dict(
            os.environ,
            {"PT_DEPLOY_MODE": "production", "PRIVACYTRACE_STORAGE": "postgres"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "pending #80"):
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


if __name__ == "__main__":
    unittest.main()
