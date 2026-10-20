"""External CLI -> stored HTTP checks using freshly built, frozen source APKs."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from privacytrace.controlled import SUITES
from privacytrace.main import create_app

SUITE_NAME = os.environ.get("PRIVACYTRACE_CONTROLLED_SUITE", "spec30")
SUITE = SUITES[SUITE_NAME]
ARTIFACTS = os.environ.get("PRIVACYTRACE_CONTROLLED_ARTIFACTS")
LABELS = json.loads((SUITE / "ground-truth.json").read_bytes())["scenarios"]
pytestmark = pytest.mark.skipif(not ARTIFACTS, reason="requires fresh controlled source build")


def cli(module, *args):
    if module == "controlled":
        args = (*args, "--suite", SUITE_NAME)
    result = subprocess.run(
        [sys.executable, "-m", "privacytrace." + module, *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    assert "Traceback" not in result.stderr, result.stderr
    return result.returncode, json.loads(result.stdout)


@pytest.mark.parametrize("scenario,expected", [
    (scenario, label["expected"])
    for scenario, label in LABELS.items()
    if SUITE_NAME == "pt907" or scenario in {"C02", "C06"}
])
def test_source_cli_http_roundtrip(tmp_path, scenario, expected):
    store = tmp_path / "jobs"
    code, output = cli(
        "controlled", "--features", SUITE / "features" / (scenario + ".json"),
        "--artifacts", ARTIFACTS, "--store-dir", store,
    )
    assert code == 0, output
    response = TestClient(create_app(store)).get(f"/api/v1/jobs/{output['job_id']}/report")
    assert response.status_code == 200
    report = response.json()
    assert report["job"]["input_mode"] == "CONTROLLED_APK"
    assert report["job"]["source_origin"] == "CONTROLLED"
    assert report["delivery_mode"] == "PERSISTED_REPLAY"
    assert expected in {issue["status"] for issue in report["result"]["issues"]}
    assert report["coverage"]["status"] == "COMPLETE"
    if scenario == "C06":
        assert report["job"]["region"] is None
        assert report["policy_documents"][0]["review_status"] == "UNREVIEWED"


@pytest.mark.parametrize("tamper", ["apk", "sources", "toolchain", "artifact_use", "schema",
                                  "receipt_type"])
def test_tampered_build_rejected_before_creating_job(tmp_path, tamper):
    build = tmp_path / "build"
    build.mkdir()
    shutil.copyfile(Path(ARTIFACTS) / "C02.apk", build / "C02.apk")
    record = json.loads((Path(ARTIFACTS) / "build-receipt.json").read_bytes())
    if tamper == "apk":
        with (build / "C02.apk").open("ab") as target:
            target.write(b"changed")
    elif tamper == "schema":
        record["schema_version"] = 2
    elif tamper == "sources":
        record["source_hashes"] = {}
    elif tamper == "receipt_type":
        record = []
    else:
        record[tamper] = "altered"
    (build / "build-receipt.json").write_text(json.dumps(record), encoding="utf-8")
    store = tmp_path / "jobs"
    code, output = cli(
        "controlled", "--features", SUITE / "features/C02.json",
        "--artifacts", build, "--store-dir", store,
    )
    assert code == 1
    assert output["errors"][0]["code"] == "CONTROLLED_INPUT_INVALID"
    assert not store.exists()


def test_same_apk_through_ordinary_cli_keeps_unknown_unreviewed_facts(tmp_path):
    feature = json.loads((SUITE / "features/C02.json").read_bytes())
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps(feature["candidates"]), encoding="utf-8")
    capture = tmp_path / "capture"
    code, output = cli(
        "policy_intake", "--raw", SUITE / "policies/C02.txt",
        "--source-url", "https://example.invalid/controlled-recheck", "--version", "1",
        "--output-dir", capture, "--candidates", candidates,
        "--package", feature["package_name"], "--version-code", "1",
    )
    assert code == 0, output
    store = tmp_path / "ordinary-jobs"
    code, output = cli(
        "pipeline", "--apk", Path(ARTIFACTS) / "C02.apk",
        "--policy", capture / "policy.capture.json", "--name", "ordinary-C02",
        "--store-dir", store,
    )
    assert code == 0, output
    report = TestClient(create_app(store)).get(f"/api/v1/jobs/{output['job_id']}/report").json()
    assert report["job"]["input_mode"] == "APK"
    assert report["job"]["source_origin"] == "REAL_SCAN"
    assert report["job"]["region"] is None
    doc = report["policy_documents"][0]
    assert doc["source_type"] != "CONTROLLED_POLICY"
    assert (doc["extraction_status"], doc["review_status"], doc["attachments_status"]) == (
        "PARTIAL", "UNREVIEWED", "NOT_CHECKED",
    )
    assert {item["status"] for item in report["result"]["issues"]} == {"INSUFFICIENT_EVIDENCE"}
