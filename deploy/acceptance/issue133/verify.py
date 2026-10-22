"""Read back every packet reference/hash without promoting observations to PASSED."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    args = parser.parse_args()
    root = args.packet.resolve()
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    if index["case_passed"]:
        raise AssertionError("This partial packet cannot assert case PASSED")
    for entry in index["evidence"]:
        candidate = root / entry["path"]
        path = candidate.resolve()
        if not path.is_relative_to(root) or candidate.is_symlink():
            raise AssertionError("Evidence escaped packet")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise AssertionError("Evidence digest mismatch: " + entry["path"])
        json.loads(raw)
    print(
        json.dumps(
            {"read_back": len(index["evidence"]), "sha256_verified": True, "case_passed": False}
        )
    )


if __name__ == "__main__":
    main()
