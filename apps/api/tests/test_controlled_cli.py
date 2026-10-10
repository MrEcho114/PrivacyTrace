"""Controlled runner CLI; malformed provenance must fail before APK scanning."""

import json
import subprocess
import sys
from hashlib import sha256

import pytest

from privacytrace.resources import ROOT


def invoke(*args):
    process = subprocess.run(
        [sys.executable, "-m", "privacytrace.controlled", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return process, json.loads(process.stdout)


def test_runner_rejects_unbound_build_before_creating_a_job(tmp_path):
    receipt = tmp_path / "build.json"
    receipt.write_text('{"schema_version":1,"apk_sha256":"wrong"}', encoding="utf-8")
    process, result = invoke(
        "run",
        "--case-dir",
        ROOT / "benchmarks/controlled/C02",
        "--build-receipt",
        receipt,
        "--output-dir",
        tmp_path / "run",
        "--store-dir",
        tmp_path / "jobs",
        "--job-id",
        "controlled-test",
    )
    assert process.returncode == 1
    assert result["error"] == "CONTROLLED_INPUT_INVALID"
    assert not (tmp_path / "jobs/controlled-test.json").exists()


def test_comparison_retains_missing_runs_as_abstentions(tmp_path):
    freeze = tmp_path / "freeze.json"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.controlled_compare",
            "freeze",
            "--suite-dir",
            str(ROOT / "benchmarks/controlled"),
            "--output",
            str(freeze),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert process.returncode == 0, process.stderr
    output = tmp_path / "comparison"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.controlled_compare",
            "compare",
            "--freeze",
            str(freeze),
            "--labels",
            str(ROOT / "benchmarks/controlled/ground-truth.json"),
            "--output-dir",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert process.returncode == 0, process.stderr
    result = json.loads((output / "comparison.json").read_bytes())
    assert result["target_count"] == 2
    assert len(result["rows"]) == 6
    assert all(row["actual"] == ["ABSTAIN"] and not row["matches"] for row in result["rows"])
    assert result["metrics"] == "N/A: two diagnostic scenarios, no precision advantage claim"


@pytest.mark.parametrize("problem", ["unbound_prediction", "changed_labels", "late_freeze"])
def test_comparison_rejects_unverifiable_results(tmp_path, problem):
    freeze = tmp_path / "freeze.json"
    base = [sys.executable, "-m", "privacytrace.controlled_compare"]
    subprocess.run(
        base
        + ["freeze", "--suite-dir", str(ROOT / "benchmarks/controlled"), "--output", str(freeze)],
        check=True,
        capture_output=True,
    )
    labels = tmp_path / "labels.json"
    labels.write_bytes((ROOT / "benchmarks/controlled/ground-truth.json").read_bytes())
    if problem == "changed_labels":
        changed = json.loads(labels.read_bytes())
        changed["targets"][0]["expected"] = "NOT_DECLARED"
        labels.write_text(json.dumps(changed), encoding="utf-8")
    prediction = tmp_path / "predictions.json"
    frozen = json.loads(freeze.read_bytes())
    if problem == "late_freeze":
        # A structurally valid FAILED run isolates the timing rule from report validation.
        build_bytes = json.dumps(
            {
                "schema_version": 1,
                "case_id": "C02",
                "apk": "scenario.apk",
                "apk_sha256": "a" * 64,
                "source_hashes": frozen["cases"]["C02"]["source_hashes"],
                "toolchain_sha256": frozen["toolchain_sha256"],
                "tools": {"fixture": "contract only"},
                "commands": [["fixture"]],
                "built_at": "1999-01-01T00:00:00+00:00",
                "elapsed_seconds": 0,
            }
        ).encode()
        (tmp_path / "build.json").write_bytes(build_bytes)
        value = {
            "schema_version": 1,
            "case_id": "C02",
            "job_id": "fixture",
            "analysis_context": "CONTROLLED_EVALUATION",
            "status": "FAILED",
            "input_hashes": frozen["cases"]["C02"]["input_hashes"],
            "source_hashes": frozen["cases"]["C02"]["source_hashes"],
            "toolchain_sha256": frozen["toolchain_sha256"],
            "apk_sha256": "a" * 64,
            "build_receipt_sha256": sha256(build_bytes).hexdigest(),
            "started_at": "2000-01-01T00:00:00+00:00",
            "generated_at": frozen["frozen_at"],
            "preparation": "contract fixture",
            "counting_unit": "ACCESS",
            "failure_policy": "retain",
            "elapsed_seconds": 0,
            "schemes": {},
            "errors": [],
        }
    else:
        value = {
            "schema_version": 1,
            "case_id": "C02",
            "analysis_context": "CONTROLLED_EVALUATION",
            "input_hashes": frozen["cases"]["C02"]["input_hashes"],
            "source_hashes": frozen["cases"]["C02"]["source_hashes"],
            "toolchain_sha256": frozen["toolchain_sha256"],
            "status": "SUCCEEDED",
            "started_at": frozen["frozen_at"],
            "generated_at": frozen["frozen_at"],
            "coverage": {"status": "COMPLETE"},
            "schemes": {},
        }
    # Deliberately forged summary with no build/report, formerly accepted by comparison.
    prediction.write_text(
        json.dumps(value),
        encoding="utf-8",
    )
    process = subprocess.run(
        base
        + [
            "compare",
            "--freeze",
            str(freeze),
            "--labels",
            str(labels),
            "--predictions",
            str(prediction),
            "--output-dir",
            str(tmp_path / "result"),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 1
    assert json.loads(process.stdout)["error"] == "CONTROLLED_COMPARISON_INVALID"
    assert not (tmp_path / "result/comparison.json").exists()
