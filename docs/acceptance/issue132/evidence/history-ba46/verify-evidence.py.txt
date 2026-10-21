"""Read back published evidence bytes; this does not rerun Android scenarios."""

import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
repo = root.parents[2]
entries = (root / "evidence-manifest.sha256").read_text().splitlines()
seen = set()
for entry in entries:
    expected, name = entry.split("  ", 1)
    target = (repo / name).resolve()
    if not target.is_relative_to(repo) or name in seen:
        raise ValueError("Invalid or duplicated manifest path")
    seen.add(name)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"Evidence byte mismatch: {name}")
    if target.suffix == ".json":
        json.loads(target.read_bytes())

records = json.loads((root / "case-results.json").read_bytes())["cases"]
assert {record["case_id"] for record in records} == {"N05", "N06", "N07", "N08"}
for record in records:
    assert record["status"] == "PASSED" and record["final_acceptance_passed"] is False
    for evidence in record["evidence"]:
        target = (root / evidence["ref"]).resolve()
        assert target.is_relative_to(root)
        assert target.relative_to(repo).as_posix() in seen
        assert hashlib.sha256(target.read_bytes()).hexdigest() == evidence["sha256"]

for name in ["N05-live-receipt.json", "N06-live-receipt.json"]:
    value = json.loads((root / "evidence" / name).read_bytes())
    assert value["subset_status"] == "PASSED" and len(value["checks"]) == 95
    assert all(check["status"] == "PASSED" and check["target_unchanged"]
               for check in value["checks"])
network = json.loads((root / "evidence/N08-android-network-receipt.json").read_bytes())
assert network["subset_status"] == "PASSED" and len(network["checks"]) == 31
assert network["scenario_status"] == "NOT_RUN"
assert network["script_sha256"] == hashlib.sha256(
    (repo / "deploy/acceptance/issue132/android_network.py").read_bytes(),
).hexdigest()
print(f"Verified {len(seen)} files and four composed local cases; no scenario rerun.")
