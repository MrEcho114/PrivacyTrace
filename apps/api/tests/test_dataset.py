import csv
import importlib.util
import json
import sys

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


def write_ledger(path, **overrides):
    row = {
        "run_id": "run-1",
        "sample_id": "app-1",
        "job_id": "job-1",
        "report_sha256": "b" * 64,
        "outcome": "partial",
        "limitations": "加固",
        "scanned_at": "2026-10-10T01:00:00Z",
        "evidence_count": "1",
        "behavior_count": "",
        "claim_count": "",
        "notes": "",
    }
    row.update(overrides)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


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
    assert dataset["schema_version"] == "0.3.0"
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
    assert dataset["runs"][0]["scanned_at"] == "2026-10-10T01:00:00+00:00"
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


def test_build_dataset_keeps_evidence_status_and_detail(tmp_path):
    ok = build_with_trace(tmp_path, [trace_line(status="ok", detail="normal")])
    failed = build_with_trace(
        tmp_path, [trace_line(status="failed", detail="extraction failure")]
    )
    assert ok["evidence"][0]["status"] == "ok"
    assert ok["evidence"][0]["detail"] == "normal"
    assert failed["evidence"][0]["status"] == "failed"
    assert failed["evidence"][0]["detail"] == "extraction failure"
    assert ok["dataset_sha256"] != failed["dataset_sha256"]


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"sample_id": "missing-app"}, "Unknown sample_id"),
        ({"outcome": "nonsense"}, "Unknown outcome"),
        ({"report_sha256": "not-a-hash"}, "lowercase SHA-256"),
        ({"outcome": "success", "report_sha256": ""}, "must carry report_sha256"),
    ],
)
def test_build_dataset_rejects_illegal_ledger_without_traces(
    tmp_path, overrides, match
):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    write_manifest(manifest)
    write_ledger(ledger, **overrides)
    with pytest.raises(ValueError, match=match):
        dataset_mod.build(manifest, ledger, trace_dir)


def test_load_traces_rejects_missing_directory(tmp_path):
    trace_dir = tmp_path / "missing-trace"
    with pytest.raises(ValueError, match="does not exist") as error:
        dataset_mod.load_traces(trace_dir)
    assert str(trace_dir) in str(error.value)


def test_load_traces_rejects_path_that_is_a_file(tmp_path):
    trace_file = tmp_path / "trace.jsonl"
    trace_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory") as error:
        dataset_mod.load_traces(trace_file)
    assert str(trace_file) in str(error.value)


def test_build_dataset_rejects_missing_trace_directory(tmp_path):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    trace_dir = tmp_path / "missing-trace"
    write_manifest(manifest)
    write_ledger(ledger)
    with pytest.raises(ValueError, match="does not exist") as error:
        dataset_mod.build(manifest, ledger, trace_dir)
    assert str(trace_dir) in str(error.value)


def test_build_dataset_rejects_trace_path_that_is_a_file(tmp_path):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    trace_file = tmp_path / "trace.jsonl"
    write_manifest(manifest)
    write_ledger(ledger)
    trace_file.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="not a directory") as error:
        dataset_mod.build(manifest, ledger, trace_file)
    assert str(trace_file) in str(error.value)


def test_build_dataset_allows_empty_trace_directory(tmp_path):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    trace_dir = tmp_path / "trace"
    write_manifest(manifest)
    write_ledger(ledger)
    trace_dir.mkdir()
    dataset = dataset_mod.build(manifest, ledger, trace_dir)
    assert dataset["evidence"] == []
    assert dataset["conclusions"] == []
    assert dataset["trace_events"] == {
        "total": 0,
        "evidence": 0,
        "conclusions": 0,
        "lifecycle": {},
    }
    assert len(dataset["dataset_sha256"]) == 64
    assert (
        dataset["dataset_sha256"]
        == dataset_mod.build(manifest, ledger, trace_dir)["dataset_sha256"]
    )


def test_load_traces_ignores_non_jsonl_files(tmp_path):
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "notes.txt").write_text("not a trace\n", encoding="utf-8")
    assert dataset_mod.load_traces(trace_dir) == []


def test_main_exits_nonzero_on_missing_trace_directory(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    missing_trace = tmp_path / "missing-trace"
    write_manifest(manifest)
    write_ledger(ledger)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-dataset.py",
            "--ledger",
            str(ledger),
            "--manifest",
            str(manifest),
            "--trace-dir",
            str(missing_trace),
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        dataset_mod.main()
    assert exit_info.value.code not in (0, None)
    assert str(missing_trace) in capsys.readouterr().err
