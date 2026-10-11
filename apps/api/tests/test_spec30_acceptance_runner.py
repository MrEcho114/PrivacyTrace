"""A failed build still produces every comparison row; reruns retain earlier evidence."""

import json
import subprocess
import sys

from privacytrace.resources import ROOT


def test_failed_build_preserves_comparison_and_unique_runs(tmp_path):
    receipts = []
    for name in ("first", "second"):
        output = tmp_path / name
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate-spec30.py"),
             "--cached", "--cache", str(tmp_path / "empty-cache"), "--output", str(output)],
            capture_output=True, text=True, encoding="utf-8", check=False, timeout=60,
        )
        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        receipt = json.loads((output / "integration-receipt.json").read_bytes())
        assert receipt["passed"] is False
        assert len(receipt["commit_sha"]) == 40
        assert receipt["stages"][0]["stage"] == "build-a"
        assert receipt["stages"][0]["exit_code"] != 0
        comparison = json.loads((output / "evaluation/comparison.json").read_bytes())
        assert len(comparison["rows"]) == 18
        assert all(row["actual"] is None and row["errors"] for row in comparison["rows"])
        assert all(counts["total"] == counts["failures"] == 6
                   for counts in comparison["summaries"].values())
        receipts.append((receipt, (output / "integration-receipt.json").read_bytes()))
    assert receipts[0][0]["run_id"] != receipts[1][0]["run_id"]
    assert (tmp_path / "first/integration-receipt.json").read_bytes() == receipts[0][1]
