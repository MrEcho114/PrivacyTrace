import importlib.util

import pytest

from privacytrace.resources import ROOT

spec = importlib.util.spec_from_file_location(
    "metrics_user_study", ROOT / "scripts/metrics_user_study.py"
)
metrics_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics_mod)


def sample_records() -> list[dict]:
    return [
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "question_id": "q1",
            "is_correct": True,
            "evidence_loc_seconds": 12.0,
            "misconception": "权限=调用",
        },
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "question_id": "q2",
            "is_correct": False,
            "evidence_loc_seconds": 30.0,
            "misconception": "",
        },
        {
            "participant_id": "p2",
            "condition": "report_first",
            "question_id": "q1",
            "is_correct": True,
            "evidence_loc_seconds": 8.0,
            "misconception": "权限=调用;法律判定",
        },
        {
            "participant_id": "p2",
            "condition": "report_first",
            "question_id": "q2",
            "is_correct": True,
            "evidence_loc_seconds": None,
            "misconception": "",
        },
    ]


def test_compute_metrics_aggregates_accuracy_time_and_misconceptions():
    metrics = metrics_mod.compute_metrics(sample_records())
    assert metrics["records"] == 4
    assert metrics["participants"] == 2
    assert metrics["accuracy"]["correct"] == 3
    assert metrics["accuracy"]["rate"] == pytest.approx(0.75)
    assert metrics["accuracy"]["by_condition"]["report_first"]["rate"] == 1.0
    assert metrics["accuracy"]["by_condition"]["baseline_first"]["rate"] == 0.5
    assert metrics["evidence_locate_time_seconds"]["overall"]["median"] == 12.0
    assert metrics["misconceptions"]["total_count"] == 3
    assert metrics["misconceptions"]["by_concept"]["权限=调用"] == 2


def test_compute_metrics_is_deterministic():
    assert metrics_mod.compute_metrics(sample_records()) == metrics_mod.compute_metrics(
        sample_records()
    )


def test_load_records_rejects_missing_required_columns(tmp_path):
    path = tmp_path / "records.csv"
    path.write_text(
        "participant_id,condition\np1,baseline_first\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="missing required columns"):
        metrics_mod.load_records(path)


def test_parse_bool_rejects_ambiguous_value():
    with pytest.raises(ValueError, match="boolean"):
        metrics_mod.parse_bool("maybe")


def test_parse_seconds_rejects_negative():
    with pytest.raises(ValueError, match="non-negative"):
        metrics_mod.parse_seconds("-1")


def test_selfcheck_prints_ok(capsys):
    metrics_mod.selfcheck()
    assert "selfcheck: OK" in capsys.readouterr().out
