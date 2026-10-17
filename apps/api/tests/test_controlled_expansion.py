"""Versioned authored scenarios retain old truth and preserve every failed target."""

import hashlib
import json
import subprocess
import sys

import pytest

from privacytrace.controlled import SUITE, SUITES, Features, load_features, scenario_ids


def test_original_six_are_byte_identical_reuse_not_new_scenarios():
    expanded = SUITES["pt907"]
    for scenario in scenario_ids():
        for relative in (f"features/{scenario}.json", f"policies/{scenario}.txt",
                         f"android/{scenario}/MainActivity.java",
                         f"android/{scenario}/AndroidManifest.xml"):
            assert (expanded / relative).read_bytes() == (SUITE / relative).read_bytes()
    truth_raw = (expanded / "ground-truth.json").read_bytes()
    truth = json.loads(truth_raw)
    assert hashlib.sha256(truth_raw).hexdigest() == (
        expanded / "ground-truth.sha256").read_text().strip()
    assert truth["reused_truth_sha256"] == hashlib.sha256(
        (SUITE / "ground-truth.json").read_bytes()).hexdigest()
    assert len(truth["new_scenarios"]) == 6
    assert set(truth["scenarios"]) == set(scenario_ids(expanded))
    for scenario in scenario_ids():
        assert truth["scenarios"][scenario] == json.loads(
            (SUITE / "ground-truth.json").read_bytes())["scenarios"][scenario]


def test_expanded_freeze_binds_sources_candidates_policy_and_condition():
    suite = SUITES["pt907"]
    inputs_raw = (suite / "inputs.lock.json").read_bytes()
    inputs = json.loads(inputs_raw)
    truth = json.loads((suite / "ground-truth.json").read_bytes())
    assert truth["inputs_lock_sha256"] == hashlib.sha256(inputs_raw).hexdigest()
    for relative, expected in inputs["sources"].items():
        assert hashlib.sha256((suite / relative).read_bytes()).hexdigest() == expected
    for scenario, expected in inputs["features"].items():
        raw = (suite / "features" / (scenario + ".json")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        feature = Features.model_validate_json(raw)
        policy = (suite / "policies" / feature.policy_file).read_bytes()
        assert hashlib.sha256(policy).hexdigest() == feature.policy_sha256
        for claim in feature.candidates:
            assert policy.decode().count(claim.excerpt) == 1
    conditional = Features.model_validate_json((suite / "features/C08.json").read_bytes())
    assert conditional.candidates[0].condition == "仅当您启用附近功能时"


def test_expansion_cannot_enter_the_original_frozen_trust_set(tmp_path):
    with pytest.raises(ValueError, match="frozen controlled suite"):
        load_features(SUITES["pt907"] / "features/C07.json", tmp_path)


def test_failed_expansion_retains_36_rows_and_full_denominators(tmp_path):
    output = tmp_path / "run"
    process = subprocess.run(
        [sys.executable, "-m", "privacytrace.benchmark", "run", "--suite", "pt907",
         "--artifacts", str(tmp_path / "missing"), "--output", str(output),
         "--blocked-error", "BUILD_A_FAILED"],
        capture_output=True, text=True, encoding="utf-8", check=False, timeout=30,
    )
    assert process.returncode == 1
    comparison = json.loads((output / "comparison.json").read_bytes())
    assert comparison["suite"] == "pt907"
    assert len(comparison["rows"]) == 36
    assert all(row["actual"] is None and row["errors"] == [{"code": "BUILD_A_FAILED"}]
               for row in comparison["rows"])
    assert all(summary["total"] == summary["failures"] == 12
               and summary["predicted"] == summary["abstentions"] == 0
               for summary in comparison["summaries"].values())
    assert len(list(output.glob("*.prediction.json"))) == 12
    assert not (output / "jobs").exists()


def test_failed_expanded_build_retains_36_targets_before_scanning(tmp_path):
    from privacytrace.resources import ROOT

    output = tmp_path / "acceptance"
    process = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate-spec30.py"), "--suite", "pt907",
         "--cached", "--cache", str(tmp_path / "empty"), "--output", str(output)],
        capture_output=True, text=True, encoding="utf-8", check=False, timeout=60,
    )
    assert process.returncode == 1
    receipt = json.loads((output / "integration-receipt.json").read_bytes())
    assert receipt["suite"] == "pt907" and receipt["scenario_count"] == 12
    assert receipt["passed"] is False
    comparison = json.loads((output / "evaluation/comparison.json").read_bytes())
    assert len(comparison["rows"]) == 36
    assert all(row["errors"] == [{"code": "BUILD_A_FAILED"}] for row in comparison["rows"])
    assert not (output / "evaluation/jobs").exists()


def test_twelfth_apk_tampering_is_rejected(tmp_path, monkeypatch):
    import importlib.util

    from privacytrace.resources import ROOT

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "expanded_validator", ROOT / "scripts/validate-spec30.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    sources = {"source.java": "a" * 64}
    apks = {}
    builds = [tmp_path / "a", tmp_path / "b"]
    for build in builds:
        build.mkdir()
        for scenario in scenario_ids(SUITES["pt907"]):
            raw = ("ENGINEERING_TEST_BYTES_" + scenario).encode()
            (build / (scenario + ".apk")).write_bytes(raw)
            apks[scenario] = hashlib.sha256(raw).hexdigest()
        (build / "build-receipt.json").write_text(json.dumps({
            "schema_version": 1, "artifact_use": "UNSIGNED_STATIC_ANALYSIS_ONLY",
            "apks": apks, "source_hashes": sources, "toolchain": {"test": "not a real build"},
        }))
    contract = ({"schema_version": 1, "apks": apks, "source_hashes": sources},
                {"schema_version": 1, "sources": sources}, {"test": "not a real build"})
    options = {"contract": contract, "scenarios": scenario_ids(SUITES["pt907"])}
    assert validator.verify_build_artifacts(*builds, **options) is None
    (builds[1] / "C12.apk").write_bytes(b"changed")
    assert validator.verify_build_artifacts(*builds, **options) == "BUILD_ARTIFACT_HASH_MISMATCH"


def test_failed_prediction_archive_keeps_error_codes_without_private_paths(tmp_path, monkeypatch):
    from privacytrace import benchmark

    monkeypatch.setattr(benchmark, "analyze", lambda *args, **kwargs: {
        "job_id": "controlled-test", "status": "FAILED",
        "errors": [{"code": "ISOLATION_REJECTED"}],
        "report_path": "/private/local/job.json",
        "tools": {"isolation_receipt": "/private/local/receipt.json"},
    })
    record = benchmark.predict(tmp_path / "C02.json", tmp_path, tmp_path / "jobs", 120)
    assert record["analysis"]["errors"] == [{"code": "ISOLATION_REJECTED"}]
    assert record["predictions"] is None
    assert "/private/local" not in json.dumps(record)
