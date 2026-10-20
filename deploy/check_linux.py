"""Clean Linux deployment checks, using disposable images/volumes and fake inputs.

No public DNS, ACME account, registry push, APK or production secret is used.
The receipt distinguishes synthetic proxy smoke from the pending #80 runner E2E.
"""

import copy
import http.client
import json
import os
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from check_infrastructure import check_infrastructure
from preflight import validate

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ["docker", "compose", "-f", str(ROOT / "deploy/compose.smoke.yaml")]
TLS_SMOKE = SMOKE + ["-f", str(ROOT / "deploy/compose.tls-smoke.yaml")]


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=kwargs.pop("timeout", 120), **kwargs)


def output(command):
    return run(command, capture_output=True, text=True).stdout.strip()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(path, *, headers=None, method="GET", host="privacytrace.test"):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
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
        "PT_RUNNER_URL=https://10.77.0.9:8444\n"
        "PT_RUNNER_IMAGE_ID=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "PT_GATEWAY_PEERS=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        "PT_GATEWAY_CONTAINER_IP=172.29.98.10\n"
        "PT_CONTROL_SUBNET=172.29.98.0/24\n"
        "PT_GATEWAY_HOST_IP=10.77.0.10\n"
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
    last_probe = "no response"
    for _ in range(30):
        try:
            status, body, _ = request("/api/v1/health")
            last_probe = f"HTTP {status}"
            # Fixed diagnostic classifications only; never echo arbitrary headers/body.
            if b"Untrusted forwarding headers" in body:
                last_probe += " (forwarding rejected)"
            elif body == b"Invalid host header":
                last_probe += " (host rejected)"
            if status == 200:
                break
        except OSError as error:
            last_probe = type(error).__name__
        time.sleep(1)
    else:
        raise AssertionError(f"Proxy/API did not become live: {last_probe}")
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
        ports = inspect["NetworkSettings"]["Ports"]
        if role == "web":
            assert ports["8080/tcp"] == [{"HostIp": "127.0.0.1", "HostPort": "18081"}]
        else:
            assert not any(ports.values())
            assert set(inspect["NetworkSettings"]["Networks"]) == {"privacytrace-smoke_private"}
        inspections[role] = {
            "image_id": inspect["Image"],
            "source_revision": settings["Labels"]["org.opencontainers.image.revision"],
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


def tls_request(context, path, host="privacytrace.test"):
    raw = socket.create_connection(("127.0.0.1", 18443), timeout=5)
    try:
        secure = context.wrap_socket(raw, server_hostname="privacytrace.test")
    except BaseException:
        raw.close()
        raise
    connection = http.client.HTTPConnection("privacytrace.test", 18443, timeout=5)
    connection.sock = secure
    try:
        connection.request("GET", path, headers={"Host": host})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def tls_tests(directory):
    run(TLS_SMOKE + ["up", "--detach", "--wait", "--wait-timeout", "60"])
    container = output(TLS_SMOKE + ["ps", "-q", "web"])
    inspected = json.loads(output(["docker", "inspect", container]))[0]
    assert {"/data", "/config"}.issubset(inspected["HostConfig"]["Tmpfs"])
    assert all(
        m["Type"] == "tmpfs"
        for m in inspected["Mounts"]
        if m["Destination"] in {"/data", "/config"}
    )
    # Only the public CA certificate leaves the ephemeral container. Never copy keys.
    root = output(
        TLS_SMOKE + ["exec", "-T", "web", "cat", "/data/caddy/pki/authorities/local/root.crt"]
    )
    certificate = directory / "smoke-public-root.crt"
    certificate.write_text(root + "\n", encoding="ascii")
    context = ssl.create_default_context(cafile=str(certificate))
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert tls_request(context, "/api/v1/health")[0] == 200
    assert tls_request(context, "/api/v1/demo/report")[0] == 200
    assert tls_request(context, "/api/v1/health", host="evil.test")[0] == 421
    assert tls_request(context, "/_health/live")[0] == 404
    try:
        tls_request(ssl.create_default_context(), "/api/v1/health")
    except ssl.SSLCertVerificationError:
        pass
    else:
        raise AssertionError("Untrusted smoke CA was accepted")
    assert request("/api/v1/health")[0] == 421
    return {
        "https_synthetic_proxy_smoke": "pass",
        "tls_trust": "ephemeral local CA; certificate and hostname verified",
        "tls_misdirected_host": "421",
        "tls_untrusted_ca": "rejected",
        "tls_key_storage": "tmpfs verified; no certificate bind or persistent volume",
    }


def main():
    head = output(["git", "rev-parse", "HEAD"])
    receipt = {
        "head_sha": head,
        "platform": "Linux Docker",
        "docker_server_version": output(["docker", "version", "--format", "{{.Server.Version}}"]),
        "compose_version": output(["docker", "compose", "version", "--short"]),
        "production": "BLOCKED",
        "not_tested": [
            "public HTTPS/ACME",
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
        with tempfile.TemporaryDirectory(prefix="privacytrace-tls-") as temporary:
            receipt.update(tls_tests(Path(temporary)))
    finally:
        # Only this fixed, disposable project; never remove production volumes.
        run(SMOKE + ["down", "--volumes", "--remove-orphans"])
    receipt["infrastructure"] = check_infrastructure()
    target = ROOT / "tmp/deployment-receipt.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Linux deployment smoke passed; receipt binds " + head)


if __name__ == "__main__":
    main()
