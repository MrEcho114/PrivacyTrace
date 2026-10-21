"""Verify historical/current evidence bytes; never rerun network scenarios."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
repo = root.parents[2]
history = root / "evidence/history-ba46"
historical_sources = {
    "deploy/acceptance/issue132/android_network.py": "android_network.py.txt",
    "deploy/acceptance/issue132/network-config.example.json": "network-config.example.json.txt",
    "apps/api/tests/test_issue132_android_network.py": "test_issue132_android_network.py.txt",
    "docs/acceptance/issue132/README.md": "README.md.txt",
    "docs/acceptance/issue132/verify-evidence.py": "verify-evidence.py.txt",
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def manifest(name, historical=False):
    seen = set()
    for line in (root / name).read_text().splitlines():
        expected, path = line.split("  ", 1)
        target = (repo / path).resolve()
        assert target.is_relative_to(repo) and path not in seen
        seen.add(path)
        if historical and path in historical_sources:
            target = history / historical_sources[path]
        assert sha(target) == expected, path
        if target.suffix == ".json":
            json.loads(target.read_bytes())
    return seen

manifest("evidence-manifest.sha256", historical=True)
seen = manifest("evidence-manifest-review-r1.sha256")
records = json.loads((root / "case-results-review-r1.json").read_bytes())["cases"]
assert {r["case_id"] for r in records} == {"N05", "N06", "N07", "N08"}
for record in records:
    assert record["final_acceptance_passed"] is False
    assert record["status"] == ("BLOCKED" if record["case_id"] == "N08" else "PASSED")
    for evidence in record["evidence"]:
        target = (root / evidence["ref"]).resolve()
        assert target.is_relative_to(root) and target.relative_to(repo).as_posix() in seen
        assert sha(target) == evidence["sha256"]
value = json.loads((root / "evidence/review-r1/network-receipt.json").read_bytes())
assert value["subset_status"] == "BLOCKED" and value["scenario_status"] == "NOT_RUN"
assert len(value["checks"]) == 45 and all(v["passed"] for v in value["checks"][:31])
assert len(value["direct_targets"]) == 14
assert all(v["status"] == "BLOCKED" and not v["route_proven"] for v in value["direct_targets"])
assert value["script_sha256"] == sha(repo / "deploy/acceptance/issue132/android_network.py")
assert value["binding_receipt_sha256"] == sha(root / "evidence/review-r1/service-bindings.json")
print(f"Verified historical bytes and {len(seen)} current files; N05-N07 PASSED, N08 BLOCKED.")
