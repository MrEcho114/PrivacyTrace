"""Recheck frozen callsites with independent dexdump in the pinned isolated builder."""

import argparse
import json
import subprocess
from pathlib import Path

from controlled_paths import daemon_path
from privacytrace.controlled import SUITES
from privacytrace.isolated_scan import docker_prefix
from privacytrace.resources import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, default="spec30")
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = subprocess.check_output([
        *docker_prefix(), "run", "--rm", "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--memory=256m",
        "--pids-limit=32", "--mount",
        "type=bind,source=" + daemon_path(ROOT) + ",target=/source,readonly",
        "--mount", "type=bind,source=" + daemon_path(args.artifacts) + ",target=/fixtures,readonly",
        "--entrypoint", "python", "privacytrace-controlled-builder:1",
        "/source/scripts/controlled/location_reference.py", "--suite",
        "/source/" + SUITES[args.suite].relative_to(ROOT).as_posix(),
        "--artifacts", "/fixtures", "--verify-reference",
        "/source/benchmarks/locator-reference-v1/reference.json",
    ], text=True, timeout=120)
    evidence = json.loads(result)
    if evidence.get("verified") is not True:
        raise ValueError("Independent callsite verification failed")
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
