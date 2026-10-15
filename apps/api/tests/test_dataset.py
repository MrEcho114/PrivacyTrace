import csv
import importlib.util
import json

import pytest

from privacytrace.resources import ROOT

spec = importlib.util.spec_from_file_location(
    "build_dataset", ROOT / "scripts/build-dataset.py"
)
dataset_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset_mod)


def write_manifest(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["sample_id", "package_name", "version_name", "version_code", "apk_sha256"]
        )
        writer.writerow(["app-1", "com.example.app", "1.0", "1", "a" * 64])


def write_ledger(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["run_id", "sample_id", "job_id", "report_sha256", "outcome", "limitations"]
        )
        writer.writerow(["run-1", "app-1", "job-1", "b" * 64, "partial", "加固"])


def trace_line(**overrides):
    line = {
        "ts": "2026-10-10T01:00:00Z",
        "sample_id": "app-1",
        "job_id": "job-1",
        "stage": "dex",
        "event": "evidence",
        "status": "ok",
        "evidence_ref": "ev-1",
        "data_type": "定位",
        "location": "com.example.App:onCreate",
    }
    line.update(overrides)
    return line


def lifecycle_line(event):
    line = trace_line()
    del line["evidence_ref"]
    line["event"] = event
    return line


def write_trace_file(directory, lines, name="trace.jsonl"):
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )


def write_traces(directory):
    write_trace_file(
        directory,
        [
            trace_line(),
            {
                "ts": "2026-10-10T01:00:01Z",
                "sample_id": "app-1",
                "job_id": "job-1",
                "stage": "consistency",
                "event": "conclusion",
                "status": "partial",
                "detail": "适用信息不全",
            },
        ],
    )


def build_with_trace(tmp_path, lines):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    write_manifest(manifest)
    write_ledger(ledger)
    write_trace_file(tmp_path / "trace", lines)
    return dataset_mod.build(manifest, ledger, tmp_path / "trace")


def test_build_dataset_normalizes_dimensions(tmp_path):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    write_manifest(manifest)
    write_ledger(ledger)
    write_traces(tmp_path / "trace")
    dataset = dataset_mod.build(manifest, ledger, tmp_path / "trace")
    assert dataset["schema_version"] == "0.2.0"
    assert len(dataset["samples"]) == 1
    assert dataset["samples"][0]["package_name"] == "com.example.app"
    assert len(dataset["evidence"]) == 1
    assert dataset["evidence"][0]["evidence_ref"] == "ev-1"
    assert dataset["evidence"][0]["event"] == "evidence"
    assert len(dataset["conclusions"]) == 1
    assert dataset["trace_events"] == {
        "total": 2,
        "evidence": 1,
        "conclusions": 1,
        "lifecycle": {},
    }
    assert len(dataset["dataset_sha256"]) == 64


def test_build_dataset_hash_is_deterministic(tmp_path):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    write_manifest(manifest)
    write_ledger(ledger)
    write_traces(tmp_path / "trace")
    first = dataset_mod.build(manifest, ledger, tmp_path / "trace")
    second = dataset_mod.build(manifest, ledger, tmp_path / "trace")
    assert first["dataset_sha256"] == second["dataset_sha256"]


def test_build_dataset_without_manifest_derives_sample_ids(tmp_path):
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger)
    write_traces(tmp_path / "trace")
    dataset = dataset_mod.build(None, ledger, tmp_path / "trace")
    assert dataset["samples"] == [{"sample_id": "app-1"}]


def test_build_dataset_counts_lifecycle_events(tmp_path):
    dataset = build_with_trace(
        tmp_path, [lifecycle_line("start"), lifecycle_line("done")]
    )
    assert dataset["trace_events"] == {
        "total": 2,
        "evidence": 0,
        "conclusions": 0,
        "lifecycle": {"done": 1, "start": 1},
    }


def test_build_dataset_rejects_trace_from_unknown_run(tmp_path):
    with pytest.raises(ValueError, match="missing from the ledger"):
        build_with_trace(tmp_path, [trace_line(job_id="job-2")])


def test_build_dataset_rejects_unknown_sample(tmp_path):
    with pytest.raises(ValueError, match="unknown sample"):
        build_with_trace(tmp_path, [trace_line(sample_id="app-2")])


def test_build_dataset_rejects_duplicate_evidence_ref(tmp_path):
    with pytest.raises(ValueError, match="repeats evidence_ref"):
        build_with_trace(
            tmp_path,
            [
                trace_line(),
                trace_line(stage="policy", location="policy:3.1"),
            ],
        )


def test_build_dataset_rejects_evidence_ref_on_other_events(tmp_path):
    conclusion = trace_line(event="conclusion", status="ok")
    with pytest.raises(ValueError, match="only allowed on event=evidence"):
        build_with_trace(tmp_path, [conclusion])


def test_build_dataset_rejects_evidence_event_without_ref(tmp_path):
    evidence = trace_line()
    del evidence["evidence_ref"]
    with pytest.raises(ValueError, match="requires evidence_ref"):
        build_with_trace(tmp_path, [evidence])
