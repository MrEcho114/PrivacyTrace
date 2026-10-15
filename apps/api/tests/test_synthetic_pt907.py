import importlib.util

from privacytrace.resources import ROOT

spec_gen = importlib.util.spec_from_file_location(
    "generate_synthetic_pt907", ROOT / "scripts/generate-synthetic-pt907.py"
)
generator_mod = importlib.util.module_from_spec(spec_gen)
spec_gen.loader.exec_module(generator_mod)

spec_ledger = importlib.util.spec_from_file_location(
    "pt907_synthetic_ledger", ROOT / "scripts/verify-run-ledger.py"
)
ledger_mod = importlib.util.module_from_spec(spec_ledger)
spec_ledger.loader.exec_module(ledger_mod)

spec_trace = importlib.util.spec_from_file_location(
    "pt907_synthetic_trace", ROOT / "scripts/validate-trace.py"
)
trace_mod = importlib.util.module_from_spec(spec_trace)
spec_trace.loader.exec_module(trace_mod)

spec_dataset = importlib.util.spec_from_file_location(
    "pt907_synthetic_dataset", ROOT / "scripts/build-dataset.py"
)
dataset_mod = importlib.util.module_from_spec(spec_dataset)
spec_dataset.loader.exec_module(dataset_mod)

spec_metrics = importlib.util.spec_from_file_location(
    "pt907_synthetic_metrics", ROOT / "scripts/metrics-user-study.py"
)
metrics_mod = importlib.util.module_from_spec(spec_metrics)
spec_metrics.loader.exec_module(metrics_mod)


def test_synthetic_pt907_pack_rehearses_full_pipeline(tmp_path):
    generator_mod.generate(tmp_path)

    manifest = tmp_path / "samples" / "synthetic" / "manifest.csv"
    runs_path = tmp_path / "samples" / "synthetic" / "runs.csv"
    trace_dir = tmp_path / "samples" / "synthetic" / "trace"
    answers = tmp_path / "evidence" / "synthetic" / "user-study.csv"

    runs = ledger_mod.verify(runs_path, manifest)
    assert len(runs) == 4
    assert {row["outcome"] for row in runs} == {"success", "partial", "failed"}
    assert any(not row["report_sha256"] for row in runs)

    trace_files = sorted(trace_dir.glob("*.jsonl"))
    assert len(trace_files) == 4
    for trace_file in trace_files:
        lines = trace_mod.load_lines(trace_file)
        trace_mod.validate(lines)
        assert len(lines) == 4

    dataset = dataset_mod.build(manifest, runs_path, trace_dir)
    assert dataset["schema_version"] == "0.3.0"
    assert len(dataset["samples"]) == 4
    assert len(dataset["runs"]) == 4
    assert len(dataset["evidence"]) == 4
    assert len(dataset["conclusions"]) == 4
    assert dataset["trace_events"] == {
        "total": 16,
        "evidence": 4,
        "conclusions": 4,
        "lifecycle": {"done": 4, "start": 4},
    }
    assert len(dataset["dataset_sha256"]) == 64
    assert (
        dataset["dataset_sha256"]
        == dataset_mod.build(manifest, runs_path, trace_dir)["dataset_sha256"]
    )

    metrics = metrics_mod.compute_metrics(metrics_mod.load_records(answers))
    assert metrics["records"] == 72
    assert metrics["participants"] == 6
    assert set(metrics["accuracy"]["by_condition"]) == {
        "baseline_first",
        "report_first",
    }
    assert set(metrics["accuracy"]["by_material"]) == {"baseline", "privacyTrace"}
    assert set(metrics["accuracy"]["by_material_and_condition"]) == {
        "baseline|baseline_first",
        "baseline|report_first",
        "privacyTrace|baseline_first",
        "privacyTrace|report_first",
    }
    assert metrics["accuracy"]["answered"] == 72
    assert metrics["accuracy"]["missing"] == 0
    assert metrics["misconceptions"]["total_count"] > 0

    manifest_text = manifest.read_text(encoding="utf-8")
    assert "synthetic.example.invalid" in manifest_text
    assert "SYNTHETIC_READY" in manifest_text

    readme_text = (tmp_path / "samples" / "synthetic" / "README.md").read_text(
        encoding="utf-8"
    )
    assert "SYNTHETIC ONLY" in readme_text
    assert "must not" in readme_text.lower()

    evidence_readme_text = (
        tmp_path / "evidence" / "synthetic" / "README.md"
    ).read_text(encoding="utf-8")
    assert "SYNTHETIC ONLY" in evidence_readme_text
    assert "not real evidence" in evidence_readme_text.lower()

    answer_text = answers.read_text(encoding="utf-8")
    assert answer_text.splitlines()[0].split(",")[3] == "material"
    assert "SYNTHETIC_REHEARSAL" in answer_text
    assert "synthetic-pt907-v1" in answer_text