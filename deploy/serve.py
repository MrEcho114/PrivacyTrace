"""Deployment-only launcher; production stays closed until #80 is integrated.

The smoke surface serves synthetic, read-only resources. It cannot accept work
and must never be used as the production runtime or as a scanning receipt.
"""

import json
import os
from pathlib import Path

READ_PATHS = {"/api/v1/health", "/api/v1/taxonomy", "/api/v1/demo/report"}


def configure():
    if os.environ.get("PT_DEPLOY_MODE", "production") != "smoke":
        raise RuntimeError("PT-SRV-102: production blocked pending #80 runtime integration")
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
    host = os.environ.get("PT_PUBLIC_HOST", "privacytrace.test")
    # A single DNS hostname only; never accept wildcards, ports or Caddy syntax.
    import re

    if not re.fullmatch(r"(?=.{1,253}$)[a-z0-9]+(?:[.-][a-z0-9]+)*", host):
        raise RuntimeError("PT-SRV-102: a single lowercase DNS hostname is required")
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


def create_app():
    host = configure()
    from privacytrace.main import app
    from privacytrace.resources import read_json, sdk_signatures, taxonomy

    # Fail startup if packaging omits a registered resource or synthetic demo.
    taxonomy()
    sdk_signatures()
    read_json("samples/demo/evaluation-input.json")
    root = Path(os.environ["PRIVACYTRACE_STORE_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    return SmokeSurface(app, host)


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
