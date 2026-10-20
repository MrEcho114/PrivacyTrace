"""Validate the rendered topology without printing its environment or secrets."""

import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

DIGEST = re.compile(r"[^\s]+@sha256:[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parents[1]

TOPOLOGY_7 = {"web", "api", "postgres", "redis", "worker", "dispatcher", "gateway"}
OPTIONAL_MAINTENANCE = {"migrate", "reclaim"}


def validate(config):
    services = config["services"]
    if not TOPOLOGY_7.issubset(services) or set(services) - TOPOLOGY_7 - OPTIONAL_MAINTENANCE:
        raise ValueError("Unexpected service topology")
    volumes = {
        "web": {("certificates", "/data"), ("caddy_config", "/config")},
        "api": {
            ("materials", "/var/lib/privacytrace"),
            ("deletion_journal", "/var/lib/privacytrace-deletions"),
        },
        "postgres": {("database", "/var/lib/postgresql/data")},
        "redis": {("broker", "/data")},
        "worker": {
            ("materials", "/var/lib/privacytrace"),
            ("deletion_journal", "/var/lib/privacytrace-deletions"),
        },
        "dispatcher": {("materials", "/var/lib/privacytrace")},
        "gateway": {("materials", "/var/lib/privacytrace")},
        "migrate": set(),
        "reclaim": {("materials", "/var/lib/privacytrace")},
    }
    for name, service in services.items():
        if not DIGEST.fullmatch(service["image"]):
            raise ValueError("Images must use immutable registry digests")
        if (
            not service.get("read_only")
            or service.get("cap_drop") != ["ALL"]
            or "no-new-privileges:true" not in service.get("security_opt", [])
            or service.get("privileged")
            or service.get("network_mode")
            or service.get("pid")
            or service.get("devices")
            or service.get("cap_add")
            or service.get("userns_mode")
            or not service.get("user")
            or service["user"].split(":")[0] in {"0", "root"}
            or not service.get("pids_limit")
            or not service.get("mem_limit")
        ):
            raise ValueError("Container isolation contract violated")
        if name not in {"web", "gateway"} and service.get("ports"):
            raise ValueError("Only the HTTPS proxy may publish ports")
        if any(not mount.startswith("/") for mount in service.get("tmpfs", [])):
            raise ValueError("Tmpfs options must not become separate mount paths")
        for mount in service.get("volumes", []):
            if mount["type"] != "volume":
                raise ValueError("Host bind mounts are forbidden")
        actual_volumes = {(m["source"], m["target"]) for m in service.get("volumes", [])}
        if actual_volumes != volumes.get(name, set()) and not (
            name == "dispatcher" and actual_volumes == set()
        ):
            raise ValueError("Service volume privileges changed")
    ports = services["web"].get("ports", [])
    if {(int(p["published"]), p["target"]) for p in ports} != {(80, 8080), (443, 8443)}:
        raise ValueError("Only HTTPS and certificate-validation ports may be published")
    api_env = services["api"].get("environment", {})
    if (
        api_env.get("PT_DEPLOY_MODE") != "isolated"
        or api_env.get("PT_PUBLIC_BIND_IP") != "127.0.0.1"
        or any(p.get("host_ip") != "127.0.0.1" for p in ports)
    ):
        raise ValueError("Public release blocked: isolated proxy must use loopback")
    for name in ("api", "database"):
        if not config["networks"][name].get("internal"):
            raise ValueError("Internal networks must not have default external egress")
    if set(services["api"]["networks"]) not in (
        {"api", "database"},
        {"api", "database", "control"},
    ):
        raise ValueError("API network boundary changed")
    if set(services["web"]["networks"]) != {"edge", "api"}:
        raise ValueError("Proxy must not join the database network")
    for name in ("postgres", "redis"):
        if set(services[name]["networks"]) != {"database"}:
            raise ValueError("Database or broker network boundary changed")
    if "dispatcher" in services and set(services["dispatcher"]["networks"]) != {"database"}:
        raise ValueError("Dispatcher network boundary changed")
    if "worker" in services and set(services["worker"]["networks"]) not in (
        {"database"},
        {"database", "control"},
    ):
        raise ValueError("Worker network boundary changed")
    if "gateway" in services and set(services["gateway"]["networks"]) != {
        "database", "control"
    }:
        raise ValueError("Gateway network boundary changed")

    valid_secret_sets = {
        "web": [set()],
        "api": [{
            "runtime_database_url",
            "material_key",
            "control_tls_ca",
            "control_tls_cert",
            "control_tls_key",
        }],
        "postgres": [{"postgres_password"}],
        "redis": [{"redis_config"}],
        "dispatcher": [{"runtime_database_url", "runtime_broker_url"}],
        "worker": [{
            "runtime_database_url",
            "runtime_broker_url",
            "material_key",
            "control_tls_ca",
            "control_tls_cert",
            "control_tls_key",
        }],
        "migrate": [{"migration_database_url"}],
        "reclaim": [{"runtime_database_url"}],
        "gateway": [{
            "runtime_database_url",
            "material_key",
            "gateway_tls_ca",
            "gateway_tls_cert",
            "gateway_tls_key",
        }],
    }
    for name, service in services.items():
        actual_secrets = {s["source"] for s in service.get("secrets", [])}
        allowed = valid_secret_sets.get(name, [set()])
        if actual_secrets not in allowed:
            raise ValueError("Service secret privileges changed")

    if "gateway" in services:
        gateway = services["gateway"]
        gateway_env = gateway.get("environment", {})
        try:
            subnet = ipaddress.ip_network(
                config["networks"]["control"]["ipam"]["config"][0]["subnet"],
                strict=True,
            )
            container_ip = ipaddress.ip_address(
                gateway["networks"]["control"]["ipv4_address"]
            )
            binds = gateway.get("ports", [])
            if len(binds) != 1:
                raise ValueError
            published = binds[0]
            host_ip = ipaddress.ip_address(published["host_ip"])
            if (
                subnet.version != 4
                or not subnet.is_private
                or container_ip not in subnet
                or container_ip == subnet.network_address
                or container_ip == subnet.broadcast_address
                or gateway_env.get("PRIVACYTRACE_GATEWAY_BIND") != str(container_ip)
                or not host_ip.is_private
                or host_ip.is_loopback
                or host_ip.is_link_local
                or host_ip.is_unspecified
                or int(published["published"]) != 8443
                or int(published["target"]) != 8443
                or published.get("protocol", "tcp") != "tcp"
            ):
                raise ValueError
        except (KeyError, ValueError, TypeError, IndexError, AttributeError):
            raise ValueError("Gateway must bind only a routed private mTLS interface") from None
        peers = gateway_env.get("PRIVACYTRACE_GATEWAY_PEERS", "")
        parts = peers.split(",")
        if not parts or any(
            not re.fullmatch(r"[a-f0-9]{64}", v) or v == "0" * 64 for v in parts
        ):
            raise ValueError("Explicit non-placeholder gateway TLS peers required")

    for role in ("api", "worker"):
        if (
            services[role].get("environment", {}).get("PRIVACYTRACE_DELETION_JOURNAL_ROOT")
            != "/var/lib/privacytrace-deletions"
        ):
            raise ValueError("Independent deletion journal volume required")

    if "reclaim" in services:
        reclaim = services["reclaim"]
        if (
            reclaim.get("profiles") != ["reclamation"]
            or set(reclaim.get("networks", [])) != {"database"}
            or reclaim.get("command") != ["-m", "privacytrace.material_lifecycle", "--once"]
            or reclaim.get("environment", {}).get("PRIVACYTRACE_DATABASE_URL_FILE")
            != "/run/secrets/runtime_database_url"
            or reclaim.get("restart", "no") != "no"
        ):
            raise ValueError("Reclamation execution privilege contract changed")
    if "migrate" in services:
        mig = services["migrate"]
        if (
            set(mig.get("networks", [])) != {"database"}
            or mig.get("profiles") != ["migration"]
            or mig.get("command") != ["/app/deploy/bootstrap.py"]
            or mig.get("environment", {}).get("PRIVACYTRACE_MIGRATION_DATABASE_URL_FILE")
            != "/run/secrets/migration_database_url"
            or mig.get("restart", "no") != "no"
        ):
            raise ValueError("Migration role privilege or execution contract changed")
    env = services["api"].get("environment", {})
    if "worker" in services:
        worker_env = services["worker"].get("environment", {})
        required_image = worker_env.get("PRIVACYTRACE_RUNNER_IMAGE_ID")
        required_url = worker_env.get("PRIVACYTRACE_RUNNER_URL")
        if (
            required_image is None
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", required_image)
            or required_image == "sha256:" + "0" * 64
        ):
            raise ValueError("Runner must use a real immutable image digest")
        try:
            endpoint = urlsplit(required_url)
            ip = ipaddress.ip_address(endpoint.hostname)
            if (
                endpoint.scheme != "https"
                or not ip.is_private
                or ip.is_loopback
                or ip.is_unspecified
                or ip.is_link_local
                or endpoint.port is None
                or not 1 <= endpoint.port <= 65535
                or endpoint.path not in {"", "/"}
                or endpoint.query
                or endpoint.fragment
                or endpoint.username
                or endpoint.password
            ):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Runner must use a non-loopback private HTTPS endpoint") from None
        if (
            env.get("PRIVACYTRACE_RUNNER_IMAGE_ID") != required_image
            or env.get("PRIVACYTRACE_RUNNER_URL") != required_url
        ):
            raise ValueError("API and worker must agree on fixed Runner identity")

    if env.get("PT_DEPLOY_MODE") != "isolated" or env.get("PRIVACYTRACE_STORAGE") != "postgres":
        raise ValueError("Production must not silently use smoke or JSON storage")
    if (
        env.get("PRIVACYTRACE_MODE") != "remote"
        or env.get("PRIVACYTRACE_DATABASE_URL_FILE") != "/run/secrets/runtime_database_url"
    ):
        raise ValueError("Remote mode and service-specific secret file are required")
    if "PRIVACYTRACE_DATABASE_URL" in env or "PRIVACYTRACE_MIGRATION_DATABASE_URL" in env:
        raise ValueError("Do not inline secret database URLs")

    for bg in ("worker", "dispatcher", "gateway"):
        if bg in services:
            bg_env = services[bg].get("environment", {})
            if (
                "PRIVACYTRACE_DATABASE_URL" in bg_env
                or "PRIVACYTRACE_MIGRATION_DATABASE_URL" in bg_env
            ):
                raise ValueError("Do not inline secret database URLs")
            if (
                bg_env.get("PRIVACYTRACE_STORAGE")
                and bg_env.get("PRIVACYTRACE_STORAGE") != "postgres"
            ):
                raise ValueError("Background services must use postgres storage")


def _build_synthetic_config():
    digest = "a" * 64
    return {
        "services": {
            "web": {
                "image": f"example.invalid/web@sha256:{digest}",
                "user": "10001:10001",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128,
                "mem_limit": 268435456,
                "ports": [
                    {"published": "80", "target": 8080, "host_ip": "127.0.0.1"},
                    {"published": "443", "target": 8443, "host_ip": "127.0.0.1"},
                ],
                "networks": ["edge", "api"],
                "volumes": [
                    {"type": "volume", "source": "certificates", "target": "/data"},
                    {"type": "volume", "source": "caddy_config", "target": "/config"},
                ],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=16m,uid=10001,gid=10001"],
            },
            "api": {
                "image": f"example.invalid/api@sha256:{digest}",
                "user": "10001:10001",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128,
                "mem_limit": 805306368,
                "networks": ["api", "database", "control"],
                "volumes": [
                    {"type": "volume", "source": "materials", "target": "/var/lib/privacytrace"},
                    {
                        "type": "volume",
                        "source": "deletion_journal",
                        "target": "/var/lib/privacytrace-deletions",
                    }
                ],
                "secrets": [
                    {"source": x}
                    for x in ("runtime_database_url", "material_key", "control_tls_ca",
                              "control_tls_cert", "control_tls_key")
                ],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001"],
                "environment": {
                    "PT_DEPLOY_MODE": "isolated",
                    "PT_PUBLIC_BIND_IP": "127.0.0.1",
                    "PRIVACYTRACE_STORAGE": "postgres",
                    "PRIVACYTRACE_MODE": "remote",
                    "PRIVACYTRACE_DATABASE_URL_FILE": "/run/secrets/runtime_database_url",
                    "PRIVACYTRACE_DELETION_JOURNAL_ROOT": "/var/lib/privacytrace-deletions",
                    "PRIVACYTRACE_RUNNER_URL": "https://10.77.0.9:8444",
                    "PRIVACYTRACE_RUNNER_IMAGE_ID": "sha256:" + "a" * 64,
                },
            },
            "postgres": {
                "image": f"postgres:17.9-alpine@sha256:{digest}",
                "user": "70:70",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128,
                "mem_limit": 805306368,
                "networks": ["database"],
                "volumes": [
                    {"type": "volume", "source": "database", "target": "/var/lib/postgresql/data"}
                ],
                "secrets": [{"source": "postgres_password"}],
                "tmpfs": [
                    "/tmp:rw,noexec,nosuid,size=16m,uid=70,gid=70",
                    "/var/run/postgresql:rw,noexec,nosuid,size=4m,uid=70,gid=70",
                ],
            },
            "redis": {
                "image": f"redis:7.4.8-alpine@sha256:{digest}",
                "user": "999:999",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128,
                "mem_limit": 268435456,
                "networks": ["database"],
                "volumes": [{"type": "volume", "source": "broker", "target": "/data"}],
                "secrets": [{"source": "redis_config"}],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=16m,uid=999,gid=999"],
            },
            "worker": {
                "image": f"example.invalid/api@sha256:{digest}",
                "user": "10001:10001",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128,
                "mem_limit": 1073741824,
                "networks": ["database"],
                "volumes": [
                    {"type": "volume", "source": "materials", "target": "/var/lib/privacytrace"},
                    {
                        "type": "volume",
                        "source": "deletion_journal",
                        "target": "/var/lib/privacytrace-deletions",
                    }
                ],
                "secrets": [
                    {"source": x}
                    for x in ("runtime_database_url", "runtime_broker_url", "material_key",
                              "control_tls_ca", "control_tls_cert", "control_tls_key")
                ],
                "environment": {
                    "PRIVACYTRACE_DELETION_JOURNAL_ROOT": "/var/lib/privacytrace-deletions",
                    "PRIVACYTRACE_RUNNER_URL": "https://10.77.0.9:8444",
                    "PRIVACYTRACE_RUNNER_IMAGE_ID": "sha256:" + "a" * 64,
                },
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001"],
            },
            "dispatcher": {
                "image": f"example.invalid/api@sha256:{digest}",
                "user": "10001:10001",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128,
                "mem_limit": 268435456,
                "networks": ["database"],
                "volumes": [
                    {"type": "volume", "source": "materials", "target": "/var/lib/privacytrace"}
                ],
                "secrets": [{"source": "runtime_database_url"}, {"source": "runtime_broker_url"}],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=32m,uid=10001,gid=10001"],
            },
            "gateway": {
                "image": f"example.invalid/api@sha256:{digest}",
                "user": "10001:10001",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128,
                "mem_limit": 536870912,
                "networks": {
                    "database": {},
                    "control": {"ipv4_address": "172.29.98.10"},
                },
                "ports": [
                    {"host_ip": "10.77.0.10", "published": "8443", "target": 8443}
                ],
                "environment": {
                    "PRIVACYTRACE_GATEWAY_BIND": "172.29.98.10",
                    "PRIVACYTRACE_GATEWAY_PEERS": "b" * 64,
                },
                "volumes": [
                    {"type": "volume", "source": "materials", "target": "/var/lib/privacytrace"}
                ],
                "secrets": [
                    {"source": x}
                    for x in ("runtime_database_url", "material_key", "gateway_tls_ca",
                              "gateway_tls_cert", "gateway_tls_key")
                ],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001"],
            },
        },
        "networks": {
            "edge": {},
            "api": {"internal": True},
            "database": {"internal": True},
            "control": {"ipam": {"config": [{"subnet": "172.29.98.0/24"}]}},
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
    if not args.env_file:
        raise SystemExit(
            "Deployment preflight requires an explicit --env-file; "
            "synthetic validation is test-only"
        )
    command = [
        "docker",
        "compose",
        "--env-file",
        str(args.env_file),
        "-f",
        str(ROOT / "deploy/compose.yaml"),
        "config",
        "--format",
        "json",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        validate(json.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        # Render errors may contain env values; do not echo stderr or exception text.
        raise SystemExit("Deployment configuration rejected; inspect non-secret inputs locally")
    if not args.config_only:
        raise SystemExit(
            "Production BLOCKED: launch gates remain closed without authorization"
        )
    print("Deployment configuration valid; production gates remain closed")


if __name__ == "__main__":
    main()
