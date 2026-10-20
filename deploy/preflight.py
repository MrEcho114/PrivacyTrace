"""Validate the rendered topology without printing its environment or secrets."""

import argparse
import json
import re
import subprocess
from pathlib import Path

DIGEST = re.compile(r"[^\s]+@sha256:[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parents[1]

TOPOLOGY_7 = {"web", "api", "postgres", "redis", "worker", "dispatcher", "gateway"}
TOPOLOGY_4 = {"web", "api", "postgres", "redis"}


def validate(config):
    services = config["services"]
    if set(services) not in (TOPOLOGY_7, TOPOLOGY_4):
        raise ValueError("Unexpected service topology")
    volumes = {
        "web": {("certificates", "/data"), ("caddy_config", "/config")},
        "api": {("materials", "/var/lib/privacytrace")},
        "postgres": {("database", "/var/lib/postgresql/data")},
        "redis": {("broker", "/data")},
        "worker": {("materials", "/var/lib/privacytrace")},
        "dispatcher": {("materials", "/var/lib/privacytrace")},
        "gateway": {("materials", "/var/lib/privacytrace")},
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
        if name != "web" and service.get("ports"):
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
    if "gateway" in services and set(services["gateway"]["networks"]) not in (
        {"database"},
        {"database", "control"},
    ):
        raise ValueError("Gateway network boundary changed")

    valid_secret_sets = {
        "web": [set()],
        "api": [
            {"runtime_database_url"},
            {
                "runtime_database_url",
                "material_key",
                "control_tls_ca",
                "control_tls_cert",
                "control_tls_key",
            },
        ],
        "postgres": [{"postgres_password"}],
        "redis": [{"redis_config"}],
        "dispatcher": [
            {"runtime_database_url", "runtime_broker_url"},
            {"runtime_database_url", "broker_url"},
        ],
        "worker": [
            {
                "runtime_database_url",
                "runtime_broker_url",
                "material_key",
                "control_tls_ca",
                "control_tls_cert",
                "control_tls_key",
            },
            {"runtime_database_url", "broker_url"},
            {"runtime_database_url", "runtime_broker_url"},
        ],
        "gateway": [
            {
                "runtime_database_url",
                "material_key",
                "gateway_tls_ca",
                "gateway_tls_cert",
                "gateway_tls_key",
            },
            {"runtime_database_url"},
        ],
    }
    for name, service in services.items():
        actual_secrets = {s["source"] for s in service.get("secrets", [])}
        allowed = valid_secret_sets.get(name, [set()])
        if actual_secrets not in allowed:
            raise ValueError("Service secret privileges changed")

    env = services["api"].get("environment", {})
    if env.get("PT_DEPLOY_MODE") != "production" or env.get("PRIVACYTRACE_STORAGE") != "postgres":
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
                    {"published": "80", "target": 8080},
                    {"published": "443", "target": 8443},
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
                "networks": ["api", "database"],
                "volumes": [
                    {"type": "volume", "source": "materials", "target": "/var/lib/privacytrace"}
                ],
                "secrets": [{"source": "runtime_database_url"}],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001"],
                "environment": {
                    "PT_DEPLOY_MODE": "production",
                    "PRIVACYTRACE_STORAGE": "postgres",
                    "PRIVACYTRACE_MODE": "remote",
                    "PRIVACYTRACE_DATABASE_URL_FILE": "/run/secrets/runtime_database_url",
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
                    {"type": "volume", "source": "materials", "target": "/var/lib/privacytrace"}
                ],
                "secrets": [{"source": "runtime_database_url"}, {"source": "broker_url"}],
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
                "secrets": [{"source": "runtime_database_url"}, {"source": "broker_url"}],
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
                "networks": ["database"],
                "volumes": [
                    {"type": "volume", "source": "materials", "target": "/var/lib/privacytrace"}
                ],
                "secrets": [{"source": "runtime_database_url"}],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001"],
            },
        },
        "networks": {
            "edge": {},
            "api": {"internal": True},
            "database": {"internal": True},
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
    if not args.env_file:
        validate(_build_synthetic_config())
        if not args.config_only:
            raise SystemExit(
                "Production BLOCKED: deployment capability baseline only; production launch gates remain BLOCKED without explicit authorization"
            )
        print("Deployment configuration valid; production gates remain closed without explicit authorization")
        return
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
            "Production BLOCKED: deployment capability baseline only; production launch gates remain BLOCKED without explicit authorization"
        )
    print("Deployment configuration valid; production gates remain closed without explicit authorization")


if __name__ == "__main__":
    main()
