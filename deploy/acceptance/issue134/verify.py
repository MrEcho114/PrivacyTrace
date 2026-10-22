"""Read every public receipt byte and verify the lane F evidence index."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    root = args.packet.resolve()
    index = json.loads((root / "index.json").read_bytes())
    names = set()
    for entry in index["files"]:
        name = entry["path"]
        if not re.fullmatch(r"[a-z0-9-]+\.json", name) or name in names:
            raise ValueError("Invalid or duplicate public evidence name")
        names.add(name)
        path = root / name
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError("Evidence escaped its packet")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError("Evidence bytes changed: " + name)
        json.loads(raw)
    actual = {p.name for p in root.iterdir()} - {"index.json"}
    if names != actual:
        raise ValueError("Unindexed or missing public evidence")
    cases = json.loads((root / "cases.json").read_bytes())
    if set(cases["cases"]) != {"F01", "F02", "F03", "F04", "F07"}:
        raise ValueError("Lane F case denominator changed")
    if any(
        v["status"] not in {"PASSED", "FAILED", "BLOCKED", "NOT_RUN"}
        for v in cases["cases"].values()
    ):
        raise ValueError("Unknown case status")
    passes = sum(v["status"] == "PASSED" for v in cases["cases"].values())
    if cases["denominator"] != 5 or cases["full_case_passes"] != passes:
        raise ValueError("Full-case count does not match the original denominator")
    print(
        json.dumps(
            {
                "status": "HASHES_VERIFIED",
                "files": len(names),
                "full_case_passes": cases["full_case_passes"],
            }
        )
    )


if __name__ == "__main__":
    main()
