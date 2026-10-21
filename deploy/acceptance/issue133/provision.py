"""Provision only lane E's disposable Linux laboratory using the existing recipe."""

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from deploy.acceptance import provision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("api", "web", "runner", "scanner"):
        parser.add_argument(f"--{name}-image", required=True)
    parser.add_argument("--port", type=int, default=28443)
    parser.add_argument("--capture-synthetic-capabilities", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose an unprivileged TCP port")
    if os.name != "posix" or os.geteuid() != 0:
        parser.error("Use the owned Linux controller; private file owners require Linux root")
    parent = Path("/var/tmp/pt133e")
    if parent.is_symlink():
        parser.error("Lane E root must not be a symlink")
    parent.mkdir(mode=0o711, exist_ok=True)
    parent.chmod(0o711)
    if (parent / "current").exists():
        parser.error("An owned lane E laboratory already exists; inspect or clean it first")
    root = parent / ("pt81-" + uuid4().hex[:12])
    root.mkdir(mode=0o711)
    # _populate is the shared deployment recipe. Only this process's port
    # allocator changes; no shared source, daemon configuration or other lab changes.
    provision.free_port = lambda: args.port
    try:
        lab = provision._populate(
            root,
            root.name,
            args.api_image,
            args.web_image,
            args.runner_image,
            args.scanner_image,
        )
        env = root / "deployment.env"
        env.write_text(
            env.read_text().replace("PT_PUBLIC_HOST=privacytrace.test", "PT_PUBLIC_HOST=127.0.0.1")
        )
        caddy = root / "Caddyfile"
        caddy.chmod(0o644)
        private_capture = (
            " servers {\n log_credentials\n }\n" if args.capture_synthetic_capabilities else ""
        )
        caddy.write_text(
            caddy.read_text()
            .replace("admin off\n", "admin off\n default_sni 127.0.0.1\n" + private_capture)
            .replace(
                "https://privacytrace.test:8443 {",
                "https://127.0.0.1:8443 {\n log {\n"
                " output file /tmp/pt133e-access.json\n format json\n }",
            )
        )
        caddy.chmod(0o444)
        lab.run("up", "-d", "--no-deps", "--force-recreate", "api", "web")
        lab.ready()
        (parent / "current").write_text(str(root))
        print(
            json.dumps(
                {
                    "project": lab.project,
                    "port": args.port,
                    "source_sha": lab.state["source_sha"],
                    "scan_host_separate": False,
                }
            )
        )
    except BaseException as error:
        # Provisioning errors can contain credential-bearing SQL. Never print
        # subprocess diagnostics; keep the original only inside the private lab.
        log = root / "provision-error.log"
        log.write_text(getattr(error, "stdout", "") + "\n" + getattr(error, "stderr", ""))
        log.chmod(0o600)
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "error_type": type(error).__name__,
                    "owned_project": root.name,
                }
            )
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
