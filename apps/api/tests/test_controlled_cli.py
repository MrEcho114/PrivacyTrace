"""Controlled CLI boundary; labels and malformed materials cannot reach the scanner."""

import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import app


def test_controlled_cli_rejects_expected_answers_as_input(tmp_path):
    features = tmp_path / "features.json"
    features.write_text(json.dumps({"expected_status": "EXACT_MATCH"}), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.controlled",
            "--features",
            str(features),
            "--artifacts",
            str(tmp_path),
            "--store-dir",
            str(tmp_path / "jobs"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["errors"][0]["code"] == "CONTROLLED_INPUT_INVALID"
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "jobs").exists()


@pytest.mark.parametrize("suite,count", [("spec30", 6), ("pt907", 12)])
def test_missing_artifacts_preserve_every_scenario_and_baseline_denominator(tmp_path, suite, count):
    output = tmp_path / "comparison"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.benchmark",
            "run",
            "--suite", suite,
            "--artifacts",
            str(tmp_path / "missing"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 1
    summary = json.loads(result.stdout)
    assert summary["scenarios_passed"] is False
    assert summary["six_scenarios_passed"] is summary["scenarios_passed"]
    comparison = json.loads((output / "comparison.json").read_bytes())
    assert summary["scenario_count"] == count
    assert "six_scenarios_passed" in summary["deprecated_fields"]
    assert len(comparison["rows"]) == count * 3
    for counts in comparison["summaries"].values():
        assert counts["total"] == count
        assert counts["failures"] == count
        assert counts["predicted"] == 0
    assert all(row["actual"] is None and row["errors"] for row in comparison["rows"])


def test_http_rejects_controlled_policy_in_real_app_input(bundle_data):
    bundle_data["job"]["input_mode"] = "APK"
    bundle_data["evidence"] = [item for item in bundle_data["evidence"] if item["kind"] != "API"]
    bundle_data["behaviors"][0]["action"] = "CAPABILITY"
    bundle_data["behaviors"][0]["evidence_ids"] = [
        next(item["id"] for item in bundle_data["evidence"] if item["kind"] == "MANIFEST")
    ]
    client = TestClient(app)
    assert client.post("/api/v1/consistency/evaluate", json=bundle_data).status_code == 200
    bundle_data["policy_documents"][0]["source_type"] = "CONTROLLED_POLICY"
    response = client.post("/api/v1/consistency/evaluate", json=bundle_data)
    assert response.status_code == 422
    assert "Controlled policy facts require a controlled APK job" in response.text


@pytest.mark.parametrize("origin", ["REAL_SCAN", "UNKNOWN", "CONTROLLED"])
def test_http_cannot_self_assert_controlled_trust(bundle_data, origin):
    bundle_data["job"].update(input_mode="CONTROLLED_APK", source_origin=origin)
    bundle_data["evidence"] = [item for item in bundle_data["evidence"] if item["kind"] != "API"]
    bundle_data["behaviors"][0].update(action="CAPABILITY", evidence_ids=[
        next(item["id"] for item in bundle_data["evidence"] if item["kind"] == "MANIFEST")
    ])
    for document in bundle_data["policy_documents"]:
        document["source_type"] = "CONTROLLED_POLICY"
    response = TestClient(app).post("/api/v1/consistency/evaluate", json=bundle_data)
    assert response.status_code == 422
    if origin == "CONTROLLED":
        assert "hash-verified controlled CLI" in response.text
    else:
        assert "controlled provenance" in response.text
