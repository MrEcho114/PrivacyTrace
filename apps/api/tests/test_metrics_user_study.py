import importlib.util
import json

import pytest

from privacytrace.resources import ROOT

spec = importlib.util.spec_from_file_location(
    "metrics_user_study", ROOT / "scripts/metrics-user-study.py"
)
metrics_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics_mod)


def answer(
    participant_id: str,
    condition: str,
    material: str,
    is_correct: bool | None,
    seconds: float | None = None,
    misconception: str = "",
) -> dict:
    return {
        "participant_id": participant_id,
        "condition": condition,
        "material": material,
        "question_id": "q1",
        "is_correct": is_correct,
        "evidence_loc_seconds": seconds,
        "misconception": misconception,
    }


def sample_records() -> list[dict]:
    return [
        answer("p1", "baseline_first", "baseline", True, 12.0, "权限=调用"),
        answer("p1", "baseline_first", "privacyTrace", False, 30.0),
        answer("p2", "report_first", "privacyTrace", True, 8.0, "权限=调用;法律判定"),
        answer("p2", "report_first", "baseline", True, None),
    ]


def write_csv(tmp_path, body: str, name: str = "records.csv"):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_compute_metrics_aggregates_accuracy_time_and_misconceptions():
    metrics = metrics_mod.compute_metrics(sample_records())
    assert metrics["records"] == 4
    assert metrics["participants"] == 2
    assert metrics["accuracy"]["correct"] == 3
    assert metrics["accuracy"]["answered"] == 4
    assert metrics["accuracy"]["missing"] == 0
    assert metrics["accuracy"]["rate"] == pytest.approx(0.75)
    assert metrics["accuracy"]["by_condition"]["report_first"]["rate"] == 1.0
    assert metrics["accuracy"]["by_condition"]["baseline_first"]["rate"] == 0.5
    assert metrics["evidence_locate_time_seconds"]["overall"]["median"] == 12.0
    assert metrics["misconceptions"]["total_count"] == 3
    assert metrics["misconceptions"]["by_concept"]["权限=调用"] == 2


def test_compute_metrics_groups_by_material_as_well_as_order():
    metrics = metrics_mod.compute_metrics(sample_records())
    assert metrics["materials"] == ["baseline", "privacyTrace"]
    assert metrics["accuracy"]["by_material"]["baseline"] == {
        "correct": 2,
        "answered": 2,
        "missing": 0,
        "rate": 1.0,
    }
    assert metrics["accuracy"]["by_material"]["privacyTrace"]["rate"] == 0.5


def test_compute_metrics_separates_material_effect_from_order_effect():
    records = [
        answer("p1", "baseline_first", "baseline", False),
        answer("p1", "baseline_first", "privacyTrace", True),
        answer("p2", "report_first", "baseline", False),
        answer("p2", "report_first", "privacyTrace", True),
    ]
    metrics = metrics_mod.compute_metrics(records)["accuracy"]
    assert metrics["by_material"]["baseline"]["rate"] == 0.0
    assert metrics["by_material"]["privacyTrace"]["rate"] == 1.0
    assert metrics["by_condition"]["baseline_first"]["rate"] == 0.5
    assert metrics["by_condition"]["report_first"]["rate"] == 0.5
    assert metrics["by_material_and_condition"]["baseline|baseline_first"]["rate"] == 0
    assert (
        metrics["by_material_and_condition"]["privacyTrace|report_first"]["rate"] == 1.0
    )


def test_compute_metrics_still_reports_order_effect_when_material_is_balanced():
    records = [
        answer("p1", "baseline_first", "baseline", False),
        answer("p1", "baseline_first", "privacyTrace", False),
        answer("p2", "report_first", "baseline", True),
        answer("p2", "report_first", "privacyTrace", True),
    ]
    metrics = metrics_mod.compute_metrics(records)["accuracy"]
    assert metrics["by_material"]["baseline"]["rate"] == 0.5
    assert metrics["by_material"]["privacyTrace"]["rate"] == 0.5
    assert metrics["by_condition"]["baseline_first"]["rate"] == 0.0
    assert metrics["by_condition"]["report_first"]["rate"] == 1.0


def test_compute_metrics_is_deterministic():
    assert metrics_mod.compute_metrics(sample_records()) == metrics_mod.compute_metrics(
        sample_records()
    )


def test_blank_is_correct_counts_as_missing_and_leaves_rates_alone():
    records = [
        answer("p1", "baseline_first", "baseline", True, 12.0),
        answer("p1", "baseline_first", "baseline", None),
        answer("p2", "report_first", "privacyTrace", None),
        answer("p2", "report_first", "privacyTrace", None),
    ]
    metrics = metrics_mod.compute_metrics(records)
    assert metrics["records"] == 4
    assert metrics["accuracy"]["correct"] == 1
    assert metrics["accuracy"]["answered"] == 1
    assert metrics["accuracy"]["missing"] == 3
    assert metrics["accuracy"]["rate"] == 1.0
    assert metrics["accuracy"]["by_material"]["baseline"]["rate"] == 1.0
    assert metrics["accuracy"]["by_material"]["privacyTrace"]["rate"] is None


def test_metrics_report_stays_finite_with_partial_durations():
    records = [
        answer("p1", "baseline_first", "baseline", True, 12.0),
        answer("p1", "baseline_first", "privacyTrace", True, None),
    ]
    metrics = metrics_mod.compute_metrics(records)
    locate = metrics["evidence_locate_time_seconds"]
    assert locate["overall"]["count"] == 1
    assert locate["by_material"]["privacyTrace"]["count"] == 0
    assert json.dumps(metrics)


def test_load_records_reads_material_column(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline,q1,true\n",
    )
    assert metrics_mod.load_records(path)[0]["material"] == "baseline"


def test_load_records_treats_blank_is_correct_as_missing(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline,q1,\n",
    )
    assert metrics_mod.load_records(path)[0]["is_correct"] is None


def test_load_records_rejects_missing_required_columns(tmp_path):
    path = write_csv(tmp_path, "participant_id,condition\np1,baseline_first\n")
    with pytest.raises(ValueError, match="missing required columns"):
        metrics_mod.load_records(path)


def test_load_records_rejects_unknown_material(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,placebo,q1,true\n",
    )
    with pytest.raises(ValueError, match="material must be one of"):
        metrics_mod.load_records(path)


def test_parse_bool_rejects_ambiguous_value():
    with pytest.raises(ValueError, match="boolean"):
        metrics_mod.parse_bool("maybe")


def test_parse_bool_blank_means_not_judged():
    assert metrics_mod.parse_bool("") is None
    assert metrics_mod.parse_bool("  ") is None


def test_parse_seconds_rejects_negative():
    with pytest.raises(ValueError, match="non-negative"):
        metrics_mod.parse_seconds("-1")


@pytest.mark.parametrize("token", ["nan", "NaN", "inf", "-inf", "Infinity", "1e999"])
def test_parse_seconds_rejects_non_finite(token):
    with pytest.raises(ValueError, match="finite"):
        metrics_mod.parse_seconds(token)


def test_parse_seconds_rejects_non_numeric():
    with pytest.raises(ValueError, match="must be a number"):
        metrics_mod.parse_seconds("abc")


def test_selfcheck_prints_ok(capsys):
    metrics_mod.selfcheck()
    assert "selfcheck: OK" in capsys.readouterr().out
