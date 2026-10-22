"""Lane F's disposable lab. All mutations use its persisted random owner marker."""

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from deploy.acceptance import provision

BASE = Path("/var/tmp/pt134f")
ROLES = {"api", "dispatcher", "worker", "runner", "redis"}


def owned():
    root = Path((BASE / "current").read_text().strip())
    if root.parent != BASE or root.is_symlink() or root.resolve() != root:
        raise ValueError("F owner path rejected")
    return provision.Laboratory(root)


def create(args):
    if (BASE / "current").exists():
        raise ValueError("Inspect or clean the existing F lab first")
    root = BASE / ("pt81-" + uuid4().hex[:12])
    root.mkdir(mode=0o711)
    (BASE / "current").write_text(str(root))
    provision.free_port = lambda: 28453
    try:
        lab = provision._populate(root, root.name, args.api, args.web, args.runner, args.scanner)
        env = root / "deployment.env"
        env.write_text(
            env.read_text().replace("PT_PUBLIC_HOST=privacytrace.test", "PT_PUBLIC_HOST=127.0.0.1")
        )
        caddy = root / "Caddyfile"
        caddy.chmod(0o644)
        caddy.write_text(
            caddy.read_text()
            .replace("https://privacytrace.test:8443", "https://127.0.0.1:8443")
            .replace("admin off\n", "admin off\n default_sni 127.0.0.1\n")
        )
        caddy.chmod(0o444)
        override = root / "laboratory.json"
        value = json.loads(override.read_text())
        # The outer owned daemon publishes only the Windows loopback port.
        value["services"]["web"]["ports"] = ["0.0.0.0:28453:8443"]
        override.write_text(json.dumps(value))
        lab.run("up", "-d", "--no-deps", "--force-recreate", "api", "web")
        lab.ready()
        print(json.dumps({"state": "READY", "source_sha": lab.state["source_sha"], "port": 28453}))
    except BaseException as error:
        log = root / "provision-error.log"
        log.write_text(getattr(error, "stdout", "") + "\n" + getattr(error, "stderr", ""))
        log.chmod(0o600)
        raise RuntimeError("F provisioning failed; inspect the private log") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["create", "observe", "stop", "start", "pause", "resume", "clean"]
    )
    parser.add_argument("--role", choices=sorted(ROLES))
    for name in ("api", "web", "runner", "scanner"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if os.name != "posix" or os.geteuid() != 0 or BASE.is_symlink():
        parser.error("Use the owned Linux F controller")
    BASE.mkdir(mode=0o711, exist_ok=True)
    if args.action == "create":
        if not all((args.api, args.web, args.runner, args.scanner)):
            parser.error("Supply all four immutable images")
        return create(args)
    lab = owned()
    if args.action == "observe":
        print(lab.python((Path(__file__).parent / "state_query.py").read_text()))
    elif args.action == "clean":
        lab.stop()
        shutil.rmtree(lab.root)
        (BASE / "current").unlink()
        print(json.dumps({"state": "CLEANED", "project": lab.project}))
    else:
        if not args.role:
            parser.error("Choose the owned role")
        identifier = lab.run("ps", "-a", "-q", args.role)
        if not re.fullmatch(r"[a-f0-9]{12,64}", identifier):
            raise ValueError("Exactly one owned role required")
        actual = json.loads(provision.execute(["docker", "inspect", identifier]))[0]
        if actual["Config"]["Labels"]["com.docker.compose.project"] != lab.project:
            raise ValueError("Role ownership changed")
        if args.action in {"stop", "start"}:
            lab.run(args.action, args.role)
        else:
            provision.execute(
                ["docker", "pause" if args.action == "pause" else "unpause", identifier]
            )
        print(json.dumps({"state": "OBSERVED", "action": args.action, "role": args.role}))


if __name__ == "__main__":
    main()
