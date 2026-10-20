"""Deployment-only launcher; production stays closed until #80 is integrated.

The smoke surface serves synthetic, read-only resources. It cannot accept work
and must never be used as the production runtime or as a scanning receipt.
"""

import ipaddress
import json
import os
import re
from pathlib import Path

from privacytrace.storage_factory import resolve_database_url

READ_PATHS = {"/api/v1/health", "/api/v1/taxonomy", "/api/v1/demo/report"}


def configure():
    mode = os.environ.get("PT_DEPLOY_MODE", "production")
    host = os.environ.get("PT_PUBLIC_HOST", "privacytrace.test")
    # A single DNS hostname only; never accept wildcards, ports or Caddy syntax.
    if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9]+(?:[.-][a-z0-9]+)*", host):
        raise RuntimeError("PT-SRV-102: a single lowercase DNS hostname is required")

    if mode == "smoke":
        # Do not allow smoke to open a real database or consume real credentials.
        if os.environ.get("PRIVACYTRACE_STORAGE", "json") != "json":
            raise RuntimeError("PT-SRV-102: smoke requires disposable JSON storage")
        if any(
            os.environ.get(key)
            for key in (
                "PRIVACYTRACE_DATABASE_URL",
                "PRIVACYTRACE_MIGRATION_DATABASE_URL",
                "PRIVACYTRACE_DATABASE_URL_FILE",
                "PRIVACYTRACE_LLM_API_KEY",
            )
        ):
            raise RuntimeError("PT-SRV-102: smoke must not receive application secrets")
        os.environ.update(
            {
                "PRIVACYTRACE_MODE": "remote",
                "PRIVACYTRACE_STORAGE": "json",
                "PRIVACYTRACE_ALLOWED_HOSTS": host,
                "PRIVACYTRACE_TRUSTED_PROXIES": "",
                "PRIVACYTRACE_LLM_ENABLED": "0",
            }
        )
        return host

    if mode == "production":
        try:
            contract = json.loads(
                Path(__file__).with_name("runtime-contract.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError):
            raise RuntimeError("PT-SRV-102: release authorization unavailable") from None
        if (
            contract.get("production_enabled") is not True
            or contract.get("status") != "PUBLIC_RELEASE_AUTHORIZED"
        ):
            raise RuntimeError("PT-SRV-102: public production launch not authorized")
    elif mode == "isolated":
        try:
            bind = ipaddress.ip_address(os.environ["PT_PUBLIC_BIND_IP"])
        except (ValueError, KeyError):
            raise RuntimeError("PT-SRV-102: isolated mode requires loopback bind") from None
        if not bind.is_loopback or bind.version != 4:
            raise RuntimeError("PT-SRV-102: isolated mode requires loopback bind")
    if mode in {"production", "isolated"}:
        if any(
            os.environ.get(key)
            for key in (
                "PRIVACYTRACE_DATABASE_URL",
                "PRIVACYTRACE_MIGRATION_DATABASE_URL",
            )
        ):
            raise RuntimeError("PT-SRV-102: Do not inline secret database URLs")
        if os.environ.get("PRIVACYTRACE_STORAGE") != "postgres":
            raise RuntimeError("PT-SRV-102: production requires PostgreSQL storage")
        if not os.environ.get("PRIVACYTRACE_INSTANCE_ID"):
            raise RuntimeError("PT-SRV-102: production requires a stable instance UUID")
        db_url = resolve_database_url()
        if not db_url:
            raise RuntimeError("PT-SRV-102: production requires database URL or secret file")
        os.environ.update(
            {
                "PRIVACYTRACE_MODE": "remote",
                "PRIVACYTRACE_STORAGE": "postgres",
                "PRIVACYTRACE_EXECUTION": "durable",
                "PRIVACYTRACE_ALLOWED_HOSTS": host,
            }
        )
        os.environ.setdefault("PRIVACYTRACE_STORE_ROOT", "/var/lib/privacytrace")
        os.environ.setdefault("PRIVACYTRACE_LLM_ENABLED", "0")
        os.environ.setdefault("PRIVACYTRACE_TRUSTED_PROXIES", "")
        return host

    raise RuntimeError(f"PT-SRV-102: invalid PT_DEPLOY_MODE '{mode}'")


class SmokeSurface:
    def __init__(self, application, host):
        self.application = application
        self.host = host

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return
        path = scope["path"]
        if path in {"/_health/live", "/_health/ready"}:
            # Probes disclose no dependency details and are reachable only inside
            # the API container (also denied by Caddy).
            peer = (scope.get("client") or ("", 0))[0]
            code = 200 if path.endswith("/live") else 503
            if peer not in {"127.0.0.1", "::1"}:
                code = 404
            body = {"status": "live" if code == 200 else "unavailable"}
        elif scope["method"] not in {"GET", "HEAD"} or path not in READ_PATHS:
            code, body = 503, {"detail": "Deployment smoke is read-only; runtime pending"}
        else:
            # Validate Origin against the entire configured origin, including port.
            # Existing API middleware additionally validates Host/query/proxy headers.
            origins = [v.decode("latin-1") for k, v in scope["headers"] if k == b"origin"]
            if origins and origins != [f"https://{self.host}"]:
                code, body = 403, {"detail": "Origin rejected"}
            else:
                await self.application(scope, receive, send)
                return
        payload = json.dumps(body).encode()
        await send(
            {
                "type": "http.response.start",
                "status": code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def check_database_readiness(application=None) -> tuple[bool, str]:
    try:
        store = None
        if application and hasattr(application, "state"):
            store = getattr(application.state, "job_store", None)
        if store is None:
            try:
                from privacytrace.main import app

                store = getattr(app.state, "job_store", None)
            except Exception:
                pass
        if not store or not getattr(store, "uses_postgres", False):
            return False, "NO_POSTGRES_STORE"
        import sqlalchemy as sa

        with store.engine.connect() as conn:
            conn.execute(sa.text("SET LOCAL statement_timeout = '2s'"))
            versions = (
                conn.execute(sa.text("SELECT version_num FROM privacytrace.alembic_version"))
                .scalars()
                .all()
            )
            if versions == ["0080_05"]:
                return True, "0080_05"
            return False, f"REVISION_MISMATCH_{versions}"
    except Exception as exc:
        return False, type(exc).__name__


class ProductionSurface:
    def __init__(self, application, host):
        self.application = application
        self.host = host

    def _check_ready(self) -> bool:
        ready, _ = check_database_readiness(self.application)
        if not ready:
            return False
        from privacytrace.runtime_health import check_runtime_readiness

        return check_runtime_readiness(os.environ.get("PRIVACYTRACE_INSTANCE_ID", ""))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.application(scope, receive, send)
            return
        path = scope["path"]
        if path in {"/_health/live", "/_health/ready"}:
            peer = (scope.get("client") or ("", 0))[0]
            if peer not in {"127.0.0.1", "::1"}:
                code, body = 404, {"detail": "Not found"}
            elif path.endswith("/live"):
                code, body = 200, {"status": "live"}
            else:
                ready = self._check_ready()
                code = 200 if ready else 503
                body = {"status": "ready" if ready else "unavailable"}
            payload = json.dumps(body).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": code,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": payload})
            return

        await self.application(scope, receive, send)


def create_app():
    deploy_mode = os.environ.get("PT_DEPLOY_MODE", "production")
    host = configure()
    from privacytrace.main import app
    from privacytrace.resources import read_json, sdk_signatures, taxonomy

    # Fail startup if packaging omits a registered resource or synthetic demo.
    taxonomy()
    sdk_signatures()
    read_json("samples/demo/evaluation-input.json")
    root = Path(os.environ["PRIVACYTRACE_STORE_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    if deploy_mode == "smoke":
        return SmokeSurface(app, host)
    return ProductionSurface(app, host)


if __name__ == "__main__":
    import uvicorn

    # No forwarded-header trust or access log containing private URLs/headers.
    # Construct first: startup failures have a fixed, non-secret message.
    try:
        application = create_app()
    except Exception:
        raise SystemExit(
            "PT-SRV-102 startup refused; see deployment compatibility matrix"
        ) from None
    uvicorn.run(
        application,
        host="0.0.0.0",
        port=8000,
        workers=1,
        proxy_headers=False,
        access_log=False,
        timeout_graceful_shutdown=30,
    )
