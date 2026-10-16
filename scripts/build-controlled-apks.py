"""Download checksum-pinned official tools to project cache; compile source without network."""

import argparse
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

from controlled_paths import daemon_path, output_user
from privacytrace.controlled import SUITES
from privacytrace.isolated_scan import docker_prefix

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/toolchain")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=SUITES, default="spec30")
    parser.add_argument(
        "--cached", action="store_true", help="Do not download any archive"
    )
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=False)
    lock = json.loads((SUITES[args.suite] / "toolchain.lock.json").read_text())
    for name, artifact in lock["archives"].items():
        path = args.cache / name
        if not path.exists():
            if args.cached:
                raise ValueError("Offline toolchain archive missing: " + name)
            urllib.request.urlretrieve(artifact["url"], path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("Official tool archive checksum mismatch: " + name)
    docker = docker_prefix()
    subprocess.run(
        [
            *docker,
            "build",
            "--network=none",
            "-f",
            daemon_path(ROOT / "scripts/controlled/build.Dockerfile"),
            "-t",
            "privacytrace-controlled-builder:1",
            daemon_path(args.cache),
        ],
        check=True,
    )
    image = subprocess.check_output(
        [
            *docker,
            "image",
            "inspect",
            "privacytrace-controlled-builder:1",
            "--format",
            "{{.Id}}",
        ],
        text=True,
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
            "--memory=1g",
            "--pids-limit=128",
            "--tmpfs=/tmp:rw,size=256m",
            *output_user(),
            "--mount",
            "type=bind,source=" + daemon_path(ROOT) + ",target=/source,readonly",
            "--mount",
            "type=bind,source=" + daemon_path(args.output) + ",target=/output",
            image,
            args.suite,
        ],
        check=True,
    )
    print(
        json.dumps(
            {
                "status": "BUILT",
                "builder_image": image,
                "receipt": str(args.output / "build-receipt.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
