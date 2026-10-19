"""Clean Linux deployment checks, using disposable images/volumes and fake inputs.

No public DNS, ACME account, registry push, APK or production secret is used.
The receipt distinguishes this HTTP smoke from the pending #80 HTTPS/runner E2E.
"""

import copy
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from preflight import validate

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ["docker", "compose", "-f", str(ROOT / "deploy/compose.smoke.yaml")]


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=kwargs.pop("timeout", 120), **kwargs)


def output(command):
    return run(command, capture_output=True, text=True).stdout.strip()


def request(path, *, headers=None, method="GET", host="privacytrace.test"):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        "http://127.0.0.1:18081" + path, headers={"Host": host, **(headers or {})}, method=method
    )
    try:
        with opener.open(req, timeout=10) as response:
            return response.status, response.read(), response.headers
    except urllib.error.HTTPError as response:
        return response.code, response.read(), response.headers


def topology_tests(directory):
    digest = "0" * 64  # Syntax-only fixture; never pulled or represented as an image.
    env = directory / "config.env"
    env.write_text(
        f"PT_API_IMAGE=example.invalid/api@sha256:{digest}\n"
        f"PT_WEB_IMAGE=example.invalid/web@sha256:{digest}\n"
        "PT_PUBLIC_HOST=privacytrace.test\n"
        "PT_INSTANCE_ID=0163a8b5-3eed-481a-bfb0-31fd3fe523dc\n"
        f"PT_SECRETS_DIR={directory.as_posix()}\n",
        encoding="utf-8",
    )
    for file in ("runtime_database_url", "postgres_password", "redis.conf"):
        (directory / file).write_text("synthetic-unusable-placeholder", encoding="utf-8")
    config = json.loads(
        output(
            [
                "docker",
                "compose",
                "--env-file",
                str(env),
                "-f",
                str(ROOT / "deploy/compose.yaml"),
                "config",
                "--format",
                "json",
            ]
        )
    )
    validate(config)
    # Actual Compose output, then attacks against isolation and privilege bounds.
    mutations = [
        lambda c: c["services"]["api"].update(ports=[{"published": "8000", "target": 8000}]),
        lambda c: c["services"]["api"].update(
            volumes=[
                {"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}
            ]
        ),
        lambda c: c["services"]["api"].update(user="0:0"),
        lambda c: c["services"]["api"].update(read_only=False),
        lambda c: c["services"]["api"].update(image="example.invalid/api:latest"),
        lambda c: c["services"]["api"]["secrets"].append({"source": "postgres_password"}),
        lambda c: c["networks"]["database"].update(internal=False),
        lambda c: c["services"]["web"]["networks"].update(database={}),
        lambda c: c["services"]["api"]["environment"].update(PRIVACYTRACE_MODE="local"),
        lambda c: c["services"]["api"]["environment"].pop("PRIVACYTRACE_DATABASE_URL_FILE"),
        lambda c: c["services"]["web"].update(tmpfs=["/tmp:rw", "gid=10001"]),
        lambda c: c["services"]["api"]["volumes"].append(
            {"type": "volume", "source": "database", "target": "/var/lib/postgresql/data"}
        ),
    ]
    for mutation in mutations:
        bad = copy.deepcopy(config)
        mutation(bad)
        try:
            validate(bad)
        except ValueError:
            continue
        raise AssertionError("Unsafe deployment configuration accepted")
    result = subprocess.run(
        [os.sys.executable, str(ROOT / "deploy/preflight.py"), "--env-file", str(env)],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode != 0 and b"BLOCKED" in result.stderr
    return {
        "rendered_compose": "pass",
        "unsafe_mutations_rejected": len(mutations),
        "production_preflight": "blocked_as_required",
    }


def smoke_tests():
    run(SMOKE + ["config", "--quiet"])
    run(SMOKE + ["up", "--detach", "--wait", "--wait-timeout", "90"], timeout=120)
    for _ in range(30):
        try:
            if request("/api/v1/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise AssertionError("Proxy/API did not become live")
    for path in (
        "/",
        "/fonts/NotoSansSC-Variable.woff2",
        "/fonts/NotoSerifSC-Variable.woff2",
        "/api/v1/taxonomy",
        "/api/v1/demo/report",
    ):
        status, body, _ = request(path)
        assert status == 200 and len(body) > 100, path
    assert json.loads(request("/api/v1/demo/report")[1])["demo"] is True
    assert request("/api/v1/health", host="evil.test")[0] != 200
    assert request("/api/v1/taxonomy", headers={"Origin": "https://evil.test"})[0] == 403
    assert (
        request("/api/v1/taxonomy", headers={"Origin": "https://privacytrace.test:444"})[0] == 403
    )
    assert request("/api/v1/health", headers={"X-PrivacyTrace-Local": "1"})[0] == 403
    # Caddy must discard incoming forwarding identity before untrusted API transport.
    assert (
        request(
            "/api/v1/health",
            headers={
                "Forwarded": "for=evil",
                "X-Forwarded-For": "203.0.113.1",
                "X-Forwarded-Host": "evil.test",
            },
        )[0]
        == 200
    )
    assert request("/api/v1/jobs", method="POST")[0] == 503
    assert request("/api/v1/jobs")[0] == 503
    assert request("/api/v1/health?access_token=synthetic-canary")[0] == 400
    for path in (
        "/_health/live",
        "/_health/ready",
        "/config/",
        "/metrics",
        "/docs",
        "/openapi.json",
    ):
        assert request(path)[0] == 404, path
    inspections = {}
    for role in ("api", "web"):
        container = output(SMOKE + ["ps", "-q", role])
        inspect = json.loads(output(["docker", "inspect", container]))[0]
        settings, host = inspect["Config"], inspect["HostConfig"]
        assert settings["User"] == "10001:10001" and host["ReadonlyRootfs"]
        assert "ALL" in host["CapDrop"] and not host["Privileged"]
        assert "no-new-privileges:true" in host["SecurityOpt"]
        assert not any("docker.sock" in m.get("Source", "") for m in inspect["Mounts"])
        assert host["Memory"] > 0 and host["PidsLimit"] == 128
        inspections[role] = {
            "image_id": inspect["Image"],
            "user": settings["User"],
            "read_only": True,
            "socket": False,
            "pids_limit": 128,
            "memory_bytes": host["Memory"],
        }
    run(SMOKE + ["exec", "-T", "api", "/opt/venv/bin/python", "/app/deploy/probe.py", "live"])
    ready = subprocess.run(
        SMOKE + ["exec", "-T", "api", "/opt/venv/bin/python", "/app/deploy/probe.py", "ready"],
        capture_output=True,
        timeout=15,
    )
    assert ready.returncode == 1
    run(SMOKE + ["restart", "api"])
    run(SMOKE + ["up", "--detach", "--wait", "--wait-timeout", "60"])
    assert request("/api/v1/health")[0] == 200
    return {
        "http_synthetic_proxy_smoke": "pass",
        "readiness": "503_runtime_pending",
        "api_restart": "pass_disposable_state_only",
        "containers": inspections,
    }


def main():
    head = output(["git", "rev-parse", "HEAD"])
    receipt = {
        "head_sha": head,
        "platform": "Linux Docker",
        "production": "BLOCKED",
        "not_tested": [
            "HTTPS/ACME",
            "real PostgreSQL/Redis dispatch",
            "dedicated runner",
            "APK/splits",
            "backup/deletion replay",
            "capacity",
            "public network",
        ],
    }
    with tempfile.TemporaryDirectory(prefix="privacytrace-deployment-") as temporary:
        receipt.update(topology_tests(Path(temporary)))
    try:
        receipt.update(smoke_tests())
    finally:
        # Only this fixed, disposable project; never remove production volumes.
        run(SMOKE + ["down", "--volumes", "--remove-orphans"])
    target = ROOT / "tmp/deployment-receipt.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Linux deployment smoke passed; receipt binds " + head)


if __name__ == "__main__":
    main()
