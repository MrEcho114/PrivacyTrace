import csv
import importlib.util
import json

from privacytrace.resources import ROOT


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ledger_mod = _load("pt907_ledger", "verify-run-ledger.py")
trace_mod = _load("pt907_trace", "validate-trace.py")
dataset_mod = _load("pt907_dataset", "build-dataset.py")
metrics_mod = _load("pt907_metrics", "metrics-user-study.py")


def write_manifest(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["sample_id", "package_name", "version_name", "version_code", "apk_sha256"]
        )
        writer.writerow(["example-app", "com.example.app", "1.0", "1", "a" * 64])


def write_ledger(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "run_id",
                "sample_id",
                "job_id",
                "report_sha256",
                "outcome",
                "limitations",
                "scanned_at",
                "evidence_count",
                "behavior_count",
                "claim_count",
                "notes",
            ]
        )
        writer.writerow(
            [
                "run-example-1",
                "example-app",
                "job-example-1",
                "b" * 64,
                "partial",
                "加固",
                "2026-10-10T01:00:00Z",
                "2",
                "",
                "",
                "",
            ]
        )


def write_trace(path):
    lines = [
        {
            "ts": "2026-10-10T01:00:00Z",
            "sample_id": "example-app",
            "job_id": "job-example-1",
            "stage": "dex",
            "event": "evidence",
            "status": "ok",
            "evidence_ref": "ev-1",
            "data_type": "定位",
            "location": "com.example.App:onCreate",
        },
        {
            "ts": "2026-10-10T01:00:01Z",
            "sample_id": "example-app",
            "job_id": "job-example-1",
            "stage": "consistency",
            "event": "conclusion",
            "status": "partial",
            "detail": "政策适用信息不全",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )


def write_answers(path):
    header = [
        "participant_id",
        "background",
        "condition",
        "material",
        "sample_id",
        "ground_truth_version",
        "question_id",
        "answer",
        "is_correct",
        "evidence_loc_seconds",
        "misconception",
        "start_time",
        "end_time",
        "subjective_understanding",
        "evidence_located",
        "git_commit",
        "notes",
    ]
    rows = [
        [
            "p1", "", "baseline_first", "baseline", "example-app", "0.1.0", "q1", "",
            "true", "12", "权限=调用", "", "", "", "", "", "",
        ],
        [
            "p1", "", "baseline_first", "privacyTrace", "example-app", "0.1.0", "q2", "",
            "false", "30", "", "", "", "", "", "", "",
        ],
        [
            "p2", "", "report_first", "privacyTrace", "example-app", "0.1.0", "q1", "",
            "true", "8", "权限=调用;法律判定", "", "", "", "", "", "",
        ],
        [
            "p2", "", "report_first", "baseline", "example-app", "0.1.0", "q2", "",
            "true", "", "", "", "", "", "", "", "",
        ],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def test_pt907_pipeline_runs_end_to_end(tmp_path):
    manifest = tmp_path / "manifest.csv"
    ledger = tmp_path / "runs.csv"
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    trace = trace_dir / "trace.jsonl"
    answers = tmp_path / "answers.csv"
    write_manifest(manifest)
    write_ledger(ledger)
    write_trace(trace)
    write_answers(answers)

    runs = ledger_mod.verify(ledger, manifest)
    assert runs[0]["outcome"] == "partial"
    assert runs[0]["limitations"] == ["加固"]

    lines = trace_mod.validate(trace_mod.load_lines(trace))
    assert len(lines) == 2

    dataset = dataset_mod.build(manifest, ledger, trace_dir)
    assert dataset["schema_version"] == "0.2.0"
    assert len(dataset["samples"]) == 1
    assert len(dataset["evidence"]) == 1
    assert len(dataset["conclusions"]) == 1
    assert dataset["evidence"][0]["event"] == "evidence"
    assert dataset["trace_events"] == {
        "total": 2,
        "evidence": 1,
        "conclusions": 1,
        "lifecycle": {},
    }
    assert len(dataset["dataset_sha256"]) == 64

    metrics = metrics_mod.compute_metrics(metrics_mod.load_records(answers))
    assert metrics["accuracy"]["correct"] == 3
    assert metrics["accuracy"]["answered"] == 4
    assert metrics["accuracy"]["missing"] == 0
    assert metrics["accuracy"]["rate"] == 0.75
    assert set(metrics["accuracy"]["by_material"]) == {"baseline", "privacyTrace"}
    assert metrics["misconceptions"]["total_count"] == 3
