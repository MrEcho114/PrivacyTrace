"""Prepare browser dependencies, then verify a standalone package in a fresh disconnected container."""

import argparse
import json
import subprocess
from pathlib import Path

from controlled_paths import daemon_path, output_user
from privacytrace.isolated_scan import docker_prefix
from privacytrace.policy_intake import digest, read_safe

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument(
        "--browser-runtime",
        required=True,
        help="Linux Chromium directory on the local daemon (WSL on Windows)",
    )
    parser.add_argument("--playwright-modules", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--prepared", action="store_true", help="Reuse the prepared test image"
    )
    args = parser.parse_args()
    read_safe(args.package / "manifest.json")
    if not args.browser_runtime.startswith("/"):
        raise ValueError("Browser runtime must be an absolute local daemon path")
    args.output.mkdir(parents=True, exist_ok=False)
    docker = docker_prefix()
    tag = "privacytrace-offline-browser-test:1"
    if not args.prepared:
        subprocess.run(
            [
                *docker,
                "build",
                "-f",
                daemon_path(ROOT / "scripts/controlled/offline-test.Dockerfile"),
                "-t",
                tag,
                daemon_path(ROOT / "scripts/controlled"),
            ],
            check=True,
            timeout=600,
        )
    image = subprocess.check_output(
        [*docker, "image", "inspect", tag, "--format", "{{.Id}}"], text=True, timeout=30
    ).strip()
    subprocess.run(
        [
            *docker,
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory=2g",
            "--pids-limit=512",
            "--tmpfs=/tmp:rw,size=512m",
            *output_user(),
            "--env=NODE_PATH=/verify_modules",
            "--mount",
            "type=bind,source="
            + daemon_path(args.package)
            + ",target=/package,readonly",
            "--mount",
            "type=bind,source="
            + daemon_path(ROOT / "scripts/verify-offline-container.py")
            + ",target=/verify.py,readonly",
            "--mount",
            "type=bind,source="
            + daemon_path(ROOT / "scripts/controlled/offline-browser.cjs")
            + ",target=/offline-browser.cjs,readonly",
            "--mount",
            "type=bind,source=" + args.browser_runtime + ",target=/browser,readonly",
            "--mount",
            "type=bind,source="
            + daemon_path(args.playwright_modules / "playwright")
            + ",target=/verify_modules/playwright,readonly",
            "--mount",
            "type=bind,source="
            + daemon_path(args.playwright_modules / "playwright-core")
            + ",target=/verify_modules/playwright-core,readonly",
            "--mount",
            "type=bind,source=" + daemon_path(args.output) + ",target=/output",
            image,
        ],
        check=True,
        timeout=120,
    )
    proof = args.output / "offline-proof.json"
    record = json.loads(read_safe(proof))
    record.update(
        test_image=image,
        validation_script_sha256=digest(
            read_safe(ROOT / "scripts/verify-offline-container.py")
        ),
        browser_driver_sha256=digest(
            read_safe(ROOT / "scripts/controlled/offline-browser.cjs")
        ),
        playwright_version=json.loads(
            read_safe(args.playwright_modules / "playwright/package.json")
        )["version"],
    )
    proof.write_text(json.dumps(record, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
