"""Topology discovery for the acceptance collectors.

Everything is read from the environment. Nothing is hardcoded: not the host, the
port, the Host header, the instance, the CA bundle, the Compose project or the
credential file locations. A collector that cannot resolve its target records a
SKIP and states which variable or precondition was missing.

The integration points are declared in :data:`ENVIRONMENT_VARIABLES` so a ticket
owner can provision exactly what the next round needs.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

PREFIX = "PT_ACCEPTANCE_"

ENVIRONMENT_VARIABLES = {
    "PT_ACCEPTANCE_BASE_URL": "Topology origin, e.g. https://privacytrace.test:443",
    "PT_ACCEPTANCE_HOST": "Host header the proxy is configured for (single DNS name)",
    "PT_ACCEPTANCE_CA_FILE": "Optional CA bundle used to verify the topology certificate",
    "PT_ACCEPTANCE_INSTANCE_ID": "PT_INSTANCE_ID of the running instance",
    "PT_ACCEPTANCE_ENV_FILE": "deployment.env used by the topology (never contains secrets)",
    "PT_ACCEPTANCE_COMPOSE_FILES": "Comma-separated compose files for operator actions",
    "PT_ACCEPTANCE_COMPOSE_PROJECT": "Compose project name used by operator actions",
    "PT_ACCEPTANCE_SECRETS_DIR": "Host directory holding the mounted secret files",
    "PT_ACCEPTANCE_DOCKER": "Docker CLI invocation, e.g. 'docker' or a WSL wrapper string",
    "PT_ACCEPTANCE_ALLOW_WRITES": "1 to permit submissions that create real state",
    "PT_ACCEPTANCE_ALLOW_DESTRUCTIVE": "1 to permit restart/delete/disk-fill drills",
    "PT_ACCEPTANCE_RECEIPT_DIR": "Default output directory for receipts",
    "PT_ACCEPTANCE_ALLOWED_HOSTS": "Comma-separated additional origins the tool may call",
    "PT_ACCEPTANCE_CONNECT_IP": "Optional test DNS override; TLS still verifies BASE_URL hostname",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(PREFIX + name, default).strip()


def _flag(name: str) -> bool:
    return _env(name) in {"1", "true", "TRUE", "yes", "on"}


@dataclass(frozen=True)
class Topology:
    """Everything a collector needs to talk to the verified deployment."""

    base_url: str
    host: str
    instance_id: str
    ca_file: Path | None = None
    env_file: Path | None = None
    compose_files: tuple[Path, ...] = ()
    compose_project: str = ""
    secrets_dir: Path | None = None
    docker: str = "docker"
    allow_writes: bool = False
    allow_destructive: bool = False
    connect_ip: str = ""

    @classmethod
    def from_env(cls) -> "Topology":
        ca_file = _env("CA_FILE")
        env_file = _env("ENV_FILE")
        secrets_dir = _env("SECRETS_DIR")
        compose = [item for item in _env("COMPOSE_FILES").split(",") if item.strip()]
        return cls(
            base_url=_env("BASE_URL").rstrip("/"),
            host=_env("HOST"),
            instance_id=_env("INSTANCE_ID"),
            ca_file=Path(ca_file) if ca_file else None,
            env_file=Path(env_file) if env_file else None,
            compose_files=tuple(Path(item.strip()) for item in compose),
            compose_project=_env("COMPOSE_PROJECT"),
            secrets_dir=Path(secrets_dir) if secrets_dir else None,
            docker=_env("DOCKER", "docker") or "docker",
            allow_writes=_flag("ALLOW_WRITES"),
            allow_destructive=_flag("ALLOW_DESTRUCTIVE"),
            connect_ip=_env("CONNECT_IP"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.host)

    def missing(self) -> list[str]:
        """Names of the variables a real run still needs."""
        missing = []
        if not self.base_url:
            missing.append("PT_ACCEPTANCE_BASE_URL")
        if not self.host:
            missing.append("PT_ACCEPTANCE_HOST")
        if not self.instance_id:
            missing.append("PT_ACCEPTANCE_INSTANCE_ID")
        return missing

    def docker_command(self, *arguments: str) -> list[str]:
        """Docker CLI as argv; ``PT_ACCEPTANCE_DOCKER`` may be a WSL wrapper."""
        return [*self.docker.split(), *arguments]

    def compose_command(self, *arguments: str) -> list[str]:
        command = [*self.docker.split(), "compose"]
        if self.compose_project:
            command += ["--project-name", self.compose_project]
        if self.env_file:
            command += ["--env-file", str(self.env_file)]
        for path in self.compose_files:
            command += ["-f", str(path)]
        return [*command, *arguments]


@dataclass
class HttpResult:
    """One HTTP exchange, reduced to what a receipt may publish."""

    method: str
    path: str
    status: int
    duration_s: float
    body_bytes: int = 0
    json: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "duration_s": round(self.duration_s, 3),
            "body_bytes": self.body_bytes,
            "error": self.error,
        }


class TopologyUnavailable(RuntimeError):
    """Raised when the topology cannot be reached at all; collectors turn this into SKIP."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: a rewritten Location would hide a proxy defect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener(ca_file: Path | None, connect_ip: str = ""):
    handlers: list[Any] = [urllib.request.ProxyHandler({}), _NoRedirect()]
    if ca_file is not None:
        context = ssl.create_default_context(cafile=str(ca_file))
        if connect_ip:

            class Connection(http.client.HTTPSConnection):
                def connect(self):
                    raw = socket.create_connection((connect_ip, self.port), self.timeout)
                    self.sock = self._context.wrap_socket(raw, server_hostname=self.host)

            class Handler(urllib.request.HTTPSHandler):
                def https_open(self, req):
                    return self.do_open(Connection, req, context=context)

            handlers.append(Handler(context=context))
        else:
            handlers.append(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener(*handlers)


def request(
    topology: Topology,
    path: str,
    *,
    method: str = "GET",
    json_body: Any = None,
    raw_body: bytes | None = None,
    token: str = "",
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> HttpResult:
    """Issue one request and never raise for an HTTP error status."""
    url = topology.base_url + path
    payload = raw_body
    merged: dict[str, str] = {"Host": topology.host}
    if raw_body is None and json_body is not None:
        payload = json.dumps(json_body).encode("utf-8")
        merged["Content-Type"] = "application/json"
    if payload is not None:
        merged["Content-Length"] = str(len(payload))
    if token:
        merged["Authorization"] = f"Bearer {token}"
    merged.update(headers or {})
    opened = urllib.request.Request(url, data=payload, headers=merged, method=method)
    opener = _opener(topology.ca_file, topology.connect_ip)
    started = time.monotonic()
    try:
        with opener.open(opened, timeout=timeout) as response:
            body = response.read()
            return HttpResult(
                method=method,
                path=path,
                status=response.status,
                duration_s=time.monotonic() - started,
                body_bytes=len(body),
                json=_maybe_json(body),
                headers={k.lower(): v for k, v in response.headers.items()},
            )
    except urllib.error.HTTPError as error:
        body = error.read()
        return HttpResult(
            method=method,
            path=path,
            status=error.code,
            duration_s=time.monotonic() - started,
            body_bytes=len(body),
            json=_maybe_json(body),
            headers={k.lower(): v for k, v in error.headers.items()},
            error="HTTPError",
        )
    except (urllib.error.URLError, OSError) as error:
        raise TopologyUnavailable(f"{url}: {type(error).__name__}") from error


def _maybe_json(body: bytes) -> Any:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def declared_length_rejection(topology: Topology, path: str, size: int, token="") -> int:
    """Expect:100-continue admission probe; body is withheld after final refusal.

    This measures declared-length rejection, not streamed-body or slow-client limits.
    """
    parsed = urllib.parse.urlsplit(topology.base_url)
    context = ssl.create_default_context(cafile=str(topology.ca_file))
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port, context=context, timeout=15)
    if topology.connect_ip:
        raw = socket.create_connection((topology.connect_ip, parsed.port), 15)
        conn.sock = context.wrap_socket(raw, server_hostname=parsed.hostname)
    try:
        conn.putrequest("POST", path, skip_host=True)
        conn.putheader("Host", topology.host)
        conn.putheader("Content-Length", str(size))
        conn.putheader("Expect", "100-continue")
        conn.putheader("Content-Type", "application/octet-stream")
        if token:
            conn.putheader("Authorization", "Bearer " + token)
        conn.endheaders()
        return conn.getresponse().status
    finally:
        conn.close()


def probe_live(topology: Topology) -> str:
    """Return the live health payload as a short note; raise when unreachable."""
    result = request(topology, "/_health/live", timeout=10)
    if result.status != 200:
        raise TopologyUnavailable(f"/_health/live returned HTTP {result.status}")
    return f"/_health/live HTTP {result.status}"


def compose_output(topology: Topology, *arguments: str, timeout: float = 120) -> str:
    """Run a Compose subcommand for an operator action and return stdout."""
    command = topology.compose_command(*arguments)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TopologyUnavailable(
            f"compose {' '.join(arguments)}: {type(error).__name__}"
        ) from error
    if result.returncode != 0:
        raise TopologyUnavailable(f"compose {' '.join(arguments)} exited {result.returncode}")
    return result.stdout.strip()


def docker_output(topology: Topology, *arguments: str, timeout: float = 120) -> str:
    command = topology.docker_command(*arguments)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TopologyUnavailable(
            f"docker {' '.join(arguments)}: {type(error).__name__}"
        ) from error
    if result.returncode != 0:
        raise TopologyUnavailable(f"docker {' '.join(arguments)} exited {result.returncode}")
    return result.stdout.strip()


def docker_versions(topology: Topology) -> dict[str, str]:
    """Version strings for the environment block; UNAVAILABLE when absent."""
    collected: dict[str, str] = {}
    for name, arguments in (
        ("docker_server", ["version", "--format", "{{.Server.Version}}"]),
        ("docker_client", ["version", "--format", "{{.Client.Version}}"]),
        ("compose", ["compose", "version", "--short"]),
    ):
        try:
            collected[name] = docker_output(topology, *arguments, timeout=30)
        except TopologyUnavailable:
            collected[name] = "UNAVAILABLE"
    return collected


def service_state(topology: Topology, service: str) -> str:
    """Health state of one Compose service, e.g. ``running``."""
    output = compose_output(topology, "ps", "--format", "json", service)
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        state = record.get("Health") or record.get("State") or ""
        if state:
            return str(state)
    return "UNKNOWN"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a deployment env file for non-secret values (keys are returned as-is)."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def compose_services(topology: Topology, *, include_profiles: bool = False) -> list[str]:
    """Service names from the rendered Compose model, without pulling images."""
    arguments = ["config", "--services"]
    if include_profiles:
        arguments = ["--profile", "*", "config", "--services"]
    output = compose_output(topology, *arguments, timeout=60)
    return [line.strip() for line in output.splitlines() if line.strip()]


def endpoint_url(base: str, path: str) -> str:
    return urllib.parse.urljoin(base, path)
