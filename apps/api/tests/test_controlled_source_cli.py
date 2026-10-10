"""Opt-in real source build and isolated CLI/HTTP acceptance; no binary fixtures."""

import json
import os
import shutil
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import create_app
from privacytrace.resources import ROOT


def cli(module, *args):
    return subprocess.run(
        [sys.executable, "-m", "privacytrace." + module, *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.fixture(scope="module")
def source_builds(tmp_path_factory):
    sdk, jdk = os.getenv("PRIVACYTRACE_ANDROID_SDK"), os.getenv("PRIVACYTRACE_JAVA_HOME")
    if not sdk or not jdk:
        pytest.skip("Set explicit SDK/JDK paths to verify actual source builds")
    root = tmp_path_factory.mktemp("source-builds")
    suite = root / "suite"
    shutil.copytree(ROOT / "benchmarks/controlled", suite)
    process = cli(
        "controlled_compare", "freeze", "--suite-dir", suite, "--output", root / "frozen.json"
    )
    assert process.returncode == 0, process.stdout + process.stderr
    # Predictions must still run when expected labels are unavailable in the input tree.
    (suite / "ground-truth.json").unlink()
    for case_id in ("C02", "C06"):
        process = cli(
            "controlled_build",
            "--case-dir",
            suite / case_id,
            "--sdk",
            sdk,
            "--jdk",
            jdk,
            "--output-dir",
            root / case_id,
        )
        assert process.returncode == 0, process.stdout + process.stderr
    return root, suite, sdk, jdk


def test_independent_source_rebuilds_are_identical_and_tampering_is_rejected(
    source_builds, tmp_path
):
    root, suite, sdk, jdk = source_builds
    hashes = []
    for case_id in ("C02", "C06"):
        process = cli(
            "controlled_build",
            "--case-dir",
            suite / case_id,
            "--sdk",
            sdk,
            "--jdk",
            jdk,
            "--output-dir",
            tmp_path / case_id,
        )
        assert process.returncode == 0, process.stdout + process.stderr
        original = json.loads((root / case_id / "build.json").read_bytes())
        rebuilt = json.loads((tmp_path / case_id / "build.json").read_bytes())
        assert original["apk_sha256"] == rebuilt["apk_sha256"]
        hashes.append(rebuilt["apk_sha256"])
        (tmp_path / case_id / "scenario.apk").write_bytes(b"changed after build")
        rejected = cli(
            "controlled",
            "run",
            "--case-dir",
            suite / case_id,
            "--build-receipt",
            tmp_path / case_id / "build.json",
            "--output-dir",
            tmp_path / (case_id + "-run"),
            "--store-dir",
            tmp_path / "jobs",
            "--job-id",
            case_id,
        )
        assert rejected.returncode == 1
        assert json.loads(rejected.stdout)["error"] == "CONTROLLED_INPUT_INVALID"
        assert not (tmp_path / "jobs" / (case_id + ".json")).exists()
    assert hashes[0] != hashes[1]


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Requires local Docker")
@pytest.mark.parametrize(
    "case_id,data_type,status",
    [
        ("C02", "CAMERA", "EXACT_MATCH"),
        ("C06", "MICROPHONE", "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_source_cli_predictions_remain_label_free_and_match_http(
    source_builds,
    tmp_path,
    case_id,
    data_type,
    status,
):
    root, suite, _, _ = source_builds
    process = cli(
        "controlled",
        "run",
        "--case-dir",
        suite / case_id,
        "--build-receipt",
        root / case_id / "build.json",
        "--output-dir",
        tmp_path / "run",
        "--store-dir",
        tmp_path / "jobs",
        "--job-id",
        "source-" + case_id,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    client = TestClient(create_app(store_root=tmp_path / "jobs"))
    response = client.get("/api/v1/jobs/source-" + case_id + "/report")
    assert response.status_code == 200
    report = response.json()
    assert report["job"]["controlled_case_id"] == case_id
    ids = {
        b["id"]
        for b in report["behaviors"]
        if b["action"] == "ACCESS" and b["data_type"] == data_type
    }
    assert ids
    assert {i["status"] for i in report["result"]["issues"] if i["behavior_id"] in ids} == {status}
    assert report["policy_documents"][0]["review_status"] == "UNREVIEWED"
    predicted = json.loads((tmp_path / "run/predictions.json").read_bytes())
    assert set(predicted["schemes"]) == {"permission_keywords", "api_flat", "privacytrace"}
    process = cli(
        "controlled_compare",
        "compare",
        "--freeze",
        root / "frozen.json",
        "--labels",
        ROOT / "benchmarks/controlled/ground-truth.json",
        "--predictions",
        tmp_path / "run/predictions.json",
        "--output-dir",
        tmp_path / "comparison",
    )
    assert process.returncode == 0, process.stdout + process.stderr
