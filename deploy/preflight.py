"""Validate the rendered topology without printing its environment or secrets."""

import argparse
import json
import re
import subprocess
from pathlib import Path

DIGEST = re.compile(r"[^\s]+@sha256:[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parents[1]


def validate(config):
    services = config["services"]
    if set(services) != {"web", "api", "postgres", "redis"}:
        raise ValueError("Unexpected service topology")
    volumes = {
        "web": {("certificates", "/data"), ("caddy_config", "/config")},
        "api": {("materials", "/var/lib/privacytrace")},
        "postgres": {("database", "/var/lib/postgresql/data")},
        "redis": {("broker", "/data")},
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
        for mount in service.get("volumes", []):
            if mount["type"] != "volume":
                raise ValueError("Host bind mounts are forbidden")
        actual_volumes = {(m["source"], m["target"]) for m in service.get("volumes", [])}
        if actual_volumes != volumes[name]:
            raise ValueError("Service volume privileges changed")
    ports = services["web"].get("ports", [])
    if {(int(p["published"]), p["target"]) for p in ports} != {(80, 8080), (443, 8443)}:
        raise ValueError("Only HTTPS and certificate-validation ports may be published")
    for name in ("api", "database"):
        if not config["networks"][name].get("internal"):
            raise ValueError("Internal networks must not have default external egress")
    if set(services["api"]["networks"]) != {"api", "database"}:
        raise ValueError("API network boundary changed")
    if set(services["web"]["networks"]) != {"edge", "api"}:
        raise ValueError("Proxy must not join the database network")
    for name in ("postgres", "redis"):
        if set(services[name]["networks"]) != {"database"}:
            raise ValueError("Database or broker network boundary changed")
    expected_secrets = {
        "web": set(),
        "api": {"runtime_database_url"},
        "postgres": {"postgres_password"},
        "redis": {"redis_config"},
    }
    for name, service in services.items():
        if {s["source"] for s in service.get("secrets", [])} != expected_secrets[name]:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--config-only", action="store_true")
    args = parser.parse_args()
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
            "Production BLOCKED: #80 role/protocol/readiness handoff is not integrated"
        )
    print("Deployment configuration valid; production remains BLOCKED pending #80")


if __name__ == "__main__":
    main()
