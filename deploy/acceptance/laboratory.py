"""Run collectors only against a previously provisioned, owned laboratory."""

import argparse
import json
import os
from pathlib import Path

from .provision import ROOT, Laboratory


def configure(directory):
    lab = Laboratory(directory)
    os.environ.update(
        {
            "PT_ACCEPTANCE_BASE_URL": f"https://privacytrace.test:{lab.state['https_port']}",
            "PT_ACCEPTANCE_HOST": "privacytrace.test",
            "PT_ACCEPTANCE_CONNECT_IP": "127.0.0.1",
            "PT_ACCEPTANCE_CA_FILE": str(lab.root / "public-ca.pem"),
            "PT_ACCEPTANCE_INSTANCE_ID": lab.state["instance_id"],
            "PT_ACCEPTANCE_ENV_FILE": str(lab.root / "deployment.env"),
            "PT_ACCEPTANCE_COMPOSE_PROJECT": lab.project,
            "PT_ACCEPTANCE_COMPOSE_FILES": ",".join(
                map(
                    str,
                    [
                        ROOT / "deploy/compose.yaml",
                        lab.root / "ports.yaml",
                        lab.root / "laboratory.json",
                    ],
                )
            ),
            "PT_ACCEPTANCE_ALLOW_WRITES": "1",
            "PT_ACCEPTANCE_ALLOW_DESTRUCTIVE": "1",
            "PT_ACCEPTANCE_LAB_STATE": str(lab.root),
            "PT_ACCEPTANCE_SOURCE_SHA": lab.state["source_sha"],
        }
    )
    return lab


def inspect_roles(lab):
    result = {}
    for role in ("web", "api", "postgres", "redis", "dispatcher", "worker", "gateway", "runner"):
        identifier = lab.run("ps", "-q", role)
        from .provision import execute

        raw = json.loads(execute(["docker", "inspect", identifier]))[0]
        host = raw["HostConfig"]
        mounts = raw["Mounts"]
        sockets = [m for m in mounts if m["Destination"] == "/var/run/docker.sock"]
        if bool(sockets) != (role == "runner"):
            raise AssertionError(f"socket boundary changed: {role}")
        if not host["ReadonlyRootfs"] or host["CapDrop"] != ["ALL"] or host["Privileged"]:
            raise AssertionError(f"container isolation changed: {role}")
        if (
            host.get("CapAdd")
            or host.get("Devices")
            or not any(
                value.startswith("no-new-privileges") for value in host.get("SecurityOpt", [])
            )
        ):
            raise AssertionError(f"privilege boundary changed: {role}")
        if role != "runner":
            for mount in mounts:
                if mount["Type"] == "bind" and not (
                    mount["Destination"].startswith("/run/secrets/")
                    and not mount["RW"]
                    or role == "web"
                    and mount["Destination"] == "/etc/caddy/Caddyfile"
                    and not mount["RW"]
                ):
                    raise AssertionError(f"unexpected host bind: {role}")
        if raw["Config"]["User"].split(":")[0] in {"", "0", "root"}:
            raise AssertionError(f"root process: {role}")
        result[role] = {
            "image_id": raw["Image"],
            "user": raw["Config"]["User"],
            "read_only": host["ReadonlyRootfs"],
            "cap_drop": host["CapDrop"],
            "socket": bool(sockets),
            "memory_limit": host["Memory"],
            "pids_limit": host["PidsLimit"],
            "source_revision": (raw["Config"].get("Labels") or {}).get(
                "org.opencontainers.image.revision", "UNLABELLED"
            ),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--only", default="r1,r2,r3,r4,r5,r6")
    parser.add_argument("--receipt-dir", type=Path, required=True)
    parser.add_argument(
        "--other-state", type=Path, help="Second owned instance for isolation checks"
    )
    parser.add_argument(
        "--previous-api-image", help="Explicit compatible baseline for rollback drill"
    )
    args = parser.parse_args()
    lab = configure(args.state)
    if args.other_state:
        Laboratory(args.other_state)  # validate its independent ownership marker
        os.environ["PT_ACCEPTANCE_OTHER_LAB_STATE"] = str(args.other_state)
    if args.previous_api_image:
        os.environ["PT_ACCEPTANCE_PREVIOUS_API_IMAGE"] = args.previous_api_image
    args.receipt_dir.mkdir(parents=True, exist_ok=True)
    roles = inspect_roles(lab)
    (args.receipt_dir / "topology.json").write_text(
        json.dumps(
            {
                "source_sha": lab.state["source_sha"],
                "roles": roles,
                "migration": "0080_05",
                "protocol": 1,
                "scan_host_separate": False,
                "untested": ["dedicated physical/VM scan-host separation and firewall persistence"],
            },
            indent=2,
        )
    )
    from .run import main as run_collectors

    return run_collectors(["--only", args.only, "--receipt-dir", str(args.receipt_dir)])


if __name__ == "__main__":
    raise SystemExit(main())
