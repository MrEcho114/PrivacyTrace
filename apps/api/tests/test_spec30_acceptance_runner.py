"""A failed build still produces every comparison row; reruns retain earlier evidence."""

import json
import subprocess
import sys

import pytest

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


@pytest.mark.parametrize("mismatch", ("apks", "source_hashes", "invalid-receipt"))
def test_rebuild_mismatch_preserves_18_failures_without_scanning(tmp_path, monkeypatch, mismatch):
    """Exercise the real acceptance runner without Docker or a real APK scan."""
    import importlib.util
    from pathlib import Path

    validator_file = ROOT / "scripts/validate-spec30.py"
    spec = importlib.util.spec_from_file_location("spec30_runner_under_test", validator_file)
    validator = importlib.util.module_from_spec(spec)
    # Direct spec loading does not add the scripts directory to sys.path.
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec.loader.exec_module(validator)

    frozen = json.loads((ROOT / "benchmarks/controlled/artifacts.lock.json").read_bytes())
    if failed_stage == "worker-build":
        # Prerequisite tests isolate the state transition, not byte verification.
        monkeypatch.setattr(validator, "verify_build_artifacts", lambda a, b: None)
    real_run = subprocess.run
    calls = []
    expected_error = (
        "BUILD_ARTIFACT_RECEIPT_INVALID"
        if mismatch == "invalid-receipt"
        else "BUILD_ARTIFACT_HASH_MISMATCH"
    )

    # This pre-existing test covers runner propagation; byte-level checks
    # are exercised separately with real synthetic bytes below.
    def receipt_only_check(a, b):
        try:
            first = json.loads((a / "build-receipt.json").read_bytes())
            second = json.loads((b / "build-receipt.json").read_bytes())
            return (None if first["apks"] == second["apks"] == frozen["apks"]
                    and first["source_hashes"] == second["source_hashes"] == frozen["source_hashes"]
                    else "BUILD_ARTIFACT_HASH_MISMATCH")
        except (OSError, ValueError, KeyError, TypeError):
            return "BUILD_ARTIFACT_RECEIPT_INVALID"

    monkeypatch.setattr(validator, "verify_build_artifacts", receipt_only_check)

    def fake_run(command, *args, **kwargs):
        argv = list(map(str, command))
        if argv[0] == "git":
            return real_run(command, *args, **kwargs)
        if len(argv) > 1 and Path(argv[1]).name == "build-controlled-apks.py":
            output = Path(argv[argv.index("--output") + 1])
            output.mkdir(parents=True, exist_ok=False)
            receipt = {
                "apks": dict(frozen["apks"]),
                "source_hashes": dict(frozen["source_hashes"]),
            }
            if output.name == "build-b":
                if mismatch == "invalid-receipt":
                    (output / "build-receipt.json").write_text("{", encoding="utf-8")
                else:
                    key = next(iter(receipt[mismatch]))
                    receipt[mismatch][key] = "0" * 64
                    (output / "build-receipt.json").write_text(json.dumps(receipt))
            else:
                (output / "build-receipt.json").write_text(json.dumps(receipt))
            calls.append(output.name)
            return subprocess.CompletedProcess(command, 0)
        if argv[1:3] == ["-m", "privacytrace.benchmark"]:
            assert argv[3] == "run"
            assert argv[argv.index("--blocked-error") + 1] == expected_error
            calls.append("six-scenarios")
            return real_run(command, *args, **kwargs)
        raise AssertionError("Unexpected prediction or Docker invocation: " + repr(argv))

    monkeypatch.setattr(validator.subprocess, "run", fake_run)
    output = tmp_path / "validation"
    monkeypatch.setattr(validator.sys, "argv", [str(validator_file), "--output", str(output)])
    assert validator.main() == 1
    assert calls == ["build-a", "build-b", "six-scenarios"]
    comparison = json.loads((output / "evaluation/comparison.json").read_bytes())
    assert len(comparison["rows"]) == 18
    assert {row["scenario_id"] for row in comparison["rows"]} == {
        "C01", "C02", "C03", "C04", "C05", "C06"
    }
    assert all(row["actual"] is None and not row["agreement"] for row in comparison["rows"])
    assert all(row["errors"] == [{"code": expected_error}] for row in comparison["rows"])
    assert all(item["total"] == item["failures"] == 6
               and item["predicted"] == item["abstentions"] == 0
               for item in comparison["summaries"].values())
    assert not (output / "evaluation/jobs").exists()
    receipt = json.loads((output / "integration-receipt.json").read_bytes())
    assert receipt["passed"] is False
    stages = {step["stage"]: step for step in receipt["stages"]}
    assert stages["rebuild-hashes"]["exit_code"] == 1
    assert stages["rebuild-hashes"]["error_code"] == expected_error
    assert stages["six-scenarios"]["exit_code"] == 1
    assert "evaluation/comparison.json" in receipt["evidence_sha256"]



@pytest.mark.parametrize(
    ("failed_stage", "error_code", "expected_calls"),
    (
        ("build-a", "BUILD_A_FAILED", ["build-a", "six-scenarios"]),
        ("build-b", "BUILD_B_FAILED", ["build-a", "build-b", "six-scenarios"]),
        ("worker-build", "WORKER_BUILD_FAILED",
         ["build-a", "build-b", "worker-build", "six-scenarios"]),
    ),
)
def test_prerequisite_failure_blocks_real_prediction(
    tmp_path, monkeypatch, failed_stage, error_code, expected_calls
):
    """Failures after either build, including worker-build, cannot launch predictions."""
    import importlib.util
    from pathlib import Path

    validator_file = ROOT / "scripts/validate-spec30.py"
    spec = importlib.util.spec_from_file_location("spec30_prerequisite_test", validator_file)
    validator = importlib.util.module_from_spec(spec)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec.loader.exec_module(validator)
    frozen = json.loads((ROOT / "benchmarks/controlled/artifacts.lock.json").read_bytes())
    real_run = subprocess.run
    calls = []

    def fake_run(command, *args, **kwargs):
        argv = list(map(str, command))
        if argv[0] == "git":
            return real_run(command, *args, **kwargs)
        if len(argv) > 1 and Path(argv[1]).name == "build-controlled-apks.py":
            label = Path(argv[argv.index("--output") + 1]).name
            calls.append(label)
            if label == failed_stage:
                return subprocess.CompletedProcess(command, 1)
            out = Path(argv[argv.index("--output") + 1])
            out.mkdir(parents=True)
            (out / "build-receipt.json").write_text(
                json.dumps({"apks": frozen["apks"], "source_hashes": frozen["source_hashes"]}),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0)
        if "build" in argv and "privacytrace-worker:s1" in argv:
            calls.append("worker-build")
            assert failed_stage == "worker-build"
            return subprocess.CompletedProcess(command, 1)
        if argv[1:3] == ["-m", "privacytrace.benchmark"]:
            assert argv[3] == "run" and "--blocked-error" in argv
            assert argv[argv.index("--blocked-error") + 1] == error_code
            calls.append("six-scenarios")
            return real_run(command, *args, **kwargs)
        raise AssertionError("Unexpected prediction or Docker invocation: " + repr(argv))

    monkeypatch.setattr(validator.subprocess, "run", fake_run)
    output = tmp_path / "prerequisite-failed"
    monkeypatch.setattr(validator.sys, "argv", [str(validator_file), "--output", str(output)])
    assert validator.main() == 1
    assert calls == expected_calls
    receipt = json.loads((output / "integration-receipt.json").read_bytes())
    assert receipt["passed"] is False
    stages = {item["stage"]: item for item in receipt["stages"]}
    assert stages[failed_stage]["error_code"] == error_code
    assert "evaluation/comparison.json" in receipt["evidence_sha256"]
    comparison = json.loads((output / "evaluation/comparison.json").read_bytes())
    assert len(comparison["rows"]) == 18
    assert all(row["actual"] is None and row["errors"] == [{"code": error_code}]
               for row in comparison["rows"])
    assert all(item["total"] == item["failures"] == 6
               and item["predicted"] == item["abstentions"] == 0
               for item in comparison["summaries"].values())
    assert not (output / "evaluation/jobs").exists()



def _synthetic_apk_builds(tmp_path):
    """Build fake byte streams outside the repository and frozen artifact lock."""
    import hashlib
    scenarios = [f"C0{i}" for i in range(1, 7)]
    values = {name: ("fixture-" + name).encode() for name in scenarios}
    apks = {name: hashlib.sha256(data).hexdigest() for name, data in values.items()}
    sources = {"android/C01/MainActivity.java": "1" * 64}
    frozen = {"schema_version": 1, "apks": apks, "source_hashes": sources}
    inputs = {"schema_version": 1, "sources": sources}
    toolchain = {"schema_version": 1, "test_fixture": True}
    for name in ("build-a", "build-b"):
        directory = tmp_path / name
        directory.mkdir()
        for scenario, data in values.items():
            (directory / (scenario + ".apk")).write_bytes(data)
        (directory / "build-receipt.json").write_text(
            json.dumps({
                "schema_version": 1,
                "apks": apks,
                "source_hashes": sources,
                "toolchain": toolchain,
                "artifact_use": "UNSIGNED_STATIC_ANALYSIS_ONLY",
            }), encoding="utf-8"
        )
    return (tmp_path / "build-a", tmp_path / "build-b"), (frozen, inputs, toolchain)


@pytest.mark.parametrize("modified", ["build-a", "build-b"])
def test_rebuild_validator_hashes_both_actual_apk_byte_streams(tmp_path, modified, monkeypatch):
    import importlib.util
    validator_file = ROOT / "scripts/validate-spec30.py"
    spec = importlib.util.spec_from_file_location("spec30_real_bytes", validator_file)
    validator = importlib.util.module_from_spec(spec)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec.loader.exec_module(validator)
    (build_a, build_b), contract = _synthetic_apk_builds(tmp_path)
    assert validator.verify_build_artifacts(build_a, build_b, contract=contract) is None
    (tmp_path / modified / "C02.apk").write_bytes(b"tampered actual apk bytes")
    assert validator.verify_build_artifacts(
        build_a, build_b, contract=contract
    ) == "BUILD_ARTIFACT_HASH_MISMATCH"


@pytest.mark.parametrize("problem", [
    "missing-apk", "missing-hash", "malformed-receipt", "wrong-type",
    "extra-apk", "source-mismatch", "receipt-hash-mismatch"
])
def test_rebuild_validator_rejects_invalid_receipts_and_artifacts(tmp_path, monkeypatch, problem):
    import importlib.util
    validator_file = ROOT / "scripts/validate-spec30.py"
    spec = importlib.util.spec_from_file_location("spec30_invalid_bytes", validator_file)
    validator = importlib.util.module_from_spec(spec)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec.loader.exec_module(validator)
    (build_a, build_b), contract = _synthetic_apk_builds(tmp_path)
    receipt_path = build_b / "build-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    expected = "BUILD_ARTIFACT_RECEIPT_INVALID"
    if problem == "missing-apk":
        (build_a / "C04.apk").unlink()
    elif problem == "missing-hash":
        del receipt["apks"]["C01"]
    elif problem == "malformed-receipt":
        receipt_path.write_text("{", encoding="utf-8")
    elif problem == "wrong-type":
        receipt["apks"] = ["C01"]
    elif problem == "extra-apk":
        (build_b / "extra.apk").write_bytes(b"extra")
    elif problem == "source-mismatch":
        receipt["source_hashes"]["android/C01/MainActivity.java"] = "0" * 64
        expected = "BUILD_ARTIFACT_HASH_MISMATCH"
    elif problem == "receipt-hash-mismatch":
        receipt["apks"]["C03"] = "0" * 64
        expected = "BUILD_ARTIFACT_HASH_MISMATCH"
    if problem not in ("malformed-receipt",):
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert validator.verify_build_artifacts(build_a, build_b, contract=contract) == expected



def test_build_script_name_is_platform_aware():
    """Host-native paths handle Windows during Windows CI without POSIX splitting."""
    from pathlib import Path, PureWindowsPath
    assert Path("scripts/build-controlled-apks.py").name == "build-controlled-apks.py"
    assert PureWindowsPath(r"C:\\repo\\scripts\\build-controlled-apks.py").name == "build-controlled-apks.py"
    assert PureWindowsPath(r"C:\\repo\\scripts\\another-script.py").name != "build-controlled-apks.py"


@pytest.mark.parametrize("corrupted_build", ["build-a", "build-b"])
def test_actual_apk_corruption_blocks_runner_and_retains_all_rows(
    tmp_path, monkeypatch, corrupted_build
):
    """Exercise real byte validation through the runner while forbidding Docker/scan."""
    import hashlib
    import importlib.util
    from pathlib import Path

    validator_file = ROOT / "scripts/validate-spec30.py"
    spec = importlib.util.spec_from_file_location("spec30_corrupt_runner", validator_file)
    validator = importlib.util.module_from_spec(spec)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec.loader.exec_module(validator)

    fake_bytes = {f"C0{i}": f"fake-apk-{i}".encode() for i in range(1, 7)}
    apks = {name: hashlib.sha256(data).hexdigest() for name, data in fake_bytes.items()}
    sources = {"android/C01/MainActivity.java": "a" * 64}
    toolchain = {"schema_version": 1, "synthetic_test": True}
    frozen = {"schema_version": 1, "apks": apks, "source_hashes": sources}
    inputs = {"schema_version": 1, "sources": sources}
    monkeypatch.setattr(validator, "_frozen_build_contract",
                        lambda: (frozen, inputs, toolchain))
    real_run = subprocess.run
    calls = []

    def fake_run(command, *args, **kwargs):
        argv = list(map(str, command))
        if argv[0] == "git":
            return real_run(command, *args, **kwargs)
        if len(argv) > 1 and Path(argv[1]).name == "build-controlled-apks.py":
            build_dir = Path(argv[argv.index("--output") + 1])
            build_dir.mkdir()
            calls.append(build_dir.name)
            for scenario, data in fake_bytes.items():
                (build_dir / (scenario + ".apk")).write_bytes(data)
            (build_dir / "build-receipt.json").write_text(
                json.dumps({
                    "schema_version": 1, "artifact_use": "UNSIGNED_STATIC_ANALYSIS_ONLY",
                    "apks": apks, "source_hashes": sources, "toolchain": toolchain,
                }), encoding="utf-8"
            )
            if build_dir.name == corrupted_build:
                (build_dir / "C03.apk").write_bytes(b"actual-byte-corruption")
            return subprocess.CompletedProcess(command, 0)
        if argv[1:3] == ["-m", "privacytrace.benchmark"]:
            assert argv[3] == "run"
            assert argv[argv.index("--blocked-error") + 1] == "BUILD_ARTIFACT_HASH_MISMATCH"
            calls.append("six-scenarios")
            return real_run(command, *args, **kwargs)
        raise AssertionError("Real worker or prediction must not run: " + repr(argv))

    monkeypatch.setattr(validator.subprocess, "run", fake_run)
    output = tmp_path / "blocked-validation"
    monkeypatch.setattr(validator.sys, "argv", [str(validator_file), "--output", str(output)])
    assert validator.main() == 1
    assert calls == ["build-a", "build-b", "six-scenarios"]
    receipt = json.loads((output / "integration-receipt.json").read_bytes())
    stages = {item["stage"]: item for item in receipt["stages"]}
    assert receipt["passed"] is False
    assert stages["rebuild-hashes"]["error_code"] == "BUILD_ARTIFACT_HASH_MISMATCH"
    assert "evaluation/comparison.json" in receipt["evidence_sha256"]
    comparison = json.loads((output / "evaluation/comparison.json").read_bytes())
    assert len(comparison["rows"]) == 18
    assert all(row["actual"] is None and row["errors"] == [
        {"code": "BUILD_ARTIFACT_HASH_MISMATCH"}
    ] for row in comparison["rows"])
    assert not (output / "evaluation/jobs").exists()
