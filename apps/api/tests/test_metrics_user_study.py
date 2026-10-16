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
    located: bool | None = None,
    question_id: str = "q1",
) -> dict:
    return {
        "participant_id": participant_id,
        "condition": condition,
        "material": material,
        "question_id": question_id,
        "is_correct": is_correct,
        "evidence_loc_seconds": seconds,
        "evidence_located": located,
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
        answer("p1", "baseline_first", "baseline", True, 12.0, question_id="q1"),
        answer("p1", "baseline_first", "baseline", None, question_id="q2"),
        answer("p2", "report_first", "privacyTrace", None, question_id="q1"),
        answer("p2", "report_first", "privacyTrace", None, question_id="q2"),
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


def test_fast_failure_is_not_reported_faster_than_slow_success():
    """复审举例：baseline 20 秒且成功 vs privacyTrace 1 秒但失败。"""
    records = [
        answer("p1", "baseline_first", "baseline", True, 20.0, located=True),
        answer("p1", "baseline_first", "privacyTrace", False, 1.0, located=False),
    ]
    metrics = metrics_mod.compute_metrics(records)
    locate = metrics["evidence_locate_time_seconds"]
    # 1 秒的失败样本不得进入成功定位耗时分布
    assert locate["success"]["records"] == 1
    assert locate["success"]["timed"]["count"] == 1
    assert locate["success"]["timed"]["min"] == 20.0
    assert locate["success"]["timed"]["median"] == 20.0
    # 该失败样本的时长只出现在失败口径
    assert locate["failure"]["records"] == 1
    assert locate["failure"]["timed"]["count"] == 1
    assert locate["failure"]["timed"]["min"] == 1.0
    assert locate["success_rate"] == 0.5
    by_material = locate["by_material_outcome"]
    assert by_material["baseline"]["success"]["timed"]["median"] == 20.0
    assert by_material["baseline"]["failure"]["records"] == 0
    assert by_material["privacyTrace"]["success"]["records"] == 0
    assert by_material["privacyTrace"]["failure"]["timed"]["median"] == 1.0
    markdown = metrics_mod.render_markdown(metrics)
    assert "材料 baseline：成功率 1.0000（成功 1 / 失败 0" in markdown
    privacy_line = next(
        line
        for line in markdown.splitlines()
        if line.startswith("- 材料 privacyTrace：")
    )
    assert "成功率 0.0000（成功 0 / 失败 1" in privacy_line
    assert "成功定位耗时：—（0 条有时长）" in privacy_line
    assert "定位失败尝试耗时：1.0 / 1.0 / 1.0 / 1.0 / 1.0（1 条有时长）" in privacy_line


def test_blank_evidence_located_counts_as_not_required():
    records = [
        answer("p1", "baseline_first", "baseline", True, 5.0, located=None, question_id="q1"),
        answer("p1", "baseline_first", "baseline", True, 7.0, located=True, question_id="q2"),
    ]
    locate = metrics_mod.compute_metrics(records)["evidence_locate_time_seconds"]
    assert locate["not_required"]["records"] == 1
    assert locate["success"]["records"] == 1
    assert locate["success"]["timed"]["count"] == 1
    assert locate["success"]["timed"]["min"] == 7.0
    assert locate["success_rate"] == 1.0


def test_success_without_duration_is_counted_but_not_timed():
    records = [
        answer("p1", "baseline_first", "baseline", True, None, located=True, question_id="q1"),
        answer("p1", "baseline_first", "baseline", True, 4.0, located=True, question_id="q2"),
    ]
    locate = metrics_mod.compute_metrics(records)["evidence_locate_time_seconds"]
    assert locate["success"]["records"] == 2
    assert locate["success"]["timed"]["count"] == 1
    assert locate["success"]["timed"]["min"] == 4.0
    assert locate["success_rate"] == 1.0


def test_success_rate_is_none_when_no_row_was_judged_for_location():
    records = [answer("p1", "baseline_first", "baseline", True, 5.0, located=None)]
    metrics = metrics_mod.compute_metrics(records)
    locate = metrics["evidence_locate_time_seconds"]
    assert locate["success_rate"] is None
    assert locate["success"]["records"] == 0
    assert locate["failure"]["records"] == 0
    assert locate["not_required"]["records"] == 1
    assert json.dumps(metrics)
    assert "成功率 —（成功 0 / 失败 0，未要求定位 1 不计入分母）" in (
        metrics_mod.render_markdown(metrics)
    )


def test_load_records_reads_evidence_located_tristate(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct,evidence_located\n"
        "p1,baseline_first,baseline,q1,true,true\n"
        "p1,baseline_first,baseline,q2,true,false\n"
        "p1,baseline_first,baseline,q3,true,\n",
    )
    located = [row["evidence_located"] for row in metrics_mod.load_records(path)]
    assert located == [True, False, None]


def test_missing_evidence_located_column_means_not_required(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline,q1,true\n",
    )
    assert metrics_mod.load_records(path)[0]["evidence_located"] is None


def test_parse_located_rejects_ambiguous_value():
    with pytest.raises(ValueError, match="evidence_located must be a boolean"):
        metrics_mod.parse_located("maybe")
    assert metrics_mod.parse_located(" true ") is True
    assert metrics_mod.parse_located("FALSE") is False
    assert metrics_mod.parse_located("  ") is None


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


def test_parse_condition_accepts_only_designed_orders():
    assert metrics_mod.parse_condition(" baseline_first ") == "baseline_first"
    assert metrics_mod.parse_condition("report_first") == "report_first"
    with pytest.raises(ValueError, match="condition must be one of"):
        metrics_mod.parse_condition("baseline-first")


def test_load_records_rejects_unknown_condition(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline-first,baseline,q1,true\n",
    )
    with pytest.raises(ValueError, match="condition must be one of"):
        metrics_mod.load_records(path)


def test_load_records_rejects_blank_participant_id(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        " ,baseline_first,baseline,q1,true\n",
    )
    with pytest.raises(ValueError, match="participant_id must not be empty"):
        metrics_mod.load_records(path)


def test_load_records_rejects_blank_question_id(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline, ,true\n",
    )
    with pytest.raises(ValueError, match="question_id must not be empty"):
        metrics_mod.load_records(path)


def test_load_records_rejects_malformed_id(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p 1,baseline_first,baseline,q1,true\n",
    )
    with pytest.raises(ValueError, match="participant_id must match"):
        metrics_mod.load_records(path)


def test_load_records_rejects_repeated_answer_and_reports_both_lines(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline,q1,true\n"
        "p2,report_first,baseline,q2,true\n"
        "p1,baseline_first,baseline,q1,false\n",
    )
    with pytest.raises(ValueError) as excinfo:
        metrics_mod.load_records(path)
    message = str(excinfo.value)
    assert "duplicate answer" in message
    assert "participant_id='p1'" in message
    assert "question_id='q1'" in message
    assert "material='baseline'" in message
    assert "line 2" in message
    assert "line 4" in message


def test_load_records_allows_shared_question_across_participants_and_materials(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline,q1,true\n"
        "p2,report_first,baseline,q1,true\n"
        "p1,baseline_first,privacyTrace,q1,true\n",
    )
    assert len(metrics_mod.load_records(path)) == 3


def test_compute_metrics_rejects_repeated_answer():
    records = [
        answer("p1", "baseline_first", "baseline", True, question_id="q1"),
        answer("p1", "baseline_first", "baseline", True, question_id="q1"),
    ]
    with pytest.raises(ValueError, match="duplicate answer"):
        metrics_mod.compute_metrics(records)


def test_compute_metrics_allows_shared_question_across_materials():
    records = [
        answer("p1", "baseline_first", "baseline", True, question_id="q1"),
        answer("p1", "baseline_first", "privacyTrace", True, question_id="q1"),
    ]
    assert metrics_mod.compute_metrics(records)["records"] == 2


def test_provenance_retained_without_leaking_answers(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,sample_id,ground_truth_version,"
        "question_id,answer,is_correct\n"
        "p1,baseline_first,baseline,app-a,truth-v1,q1,private response,true\n",
    )
    records = metrics_mod.load_records(path, require_provenance=True)
    assert records[0]["sample_id"] == "app-a"
    assert records[0]["ground_truth_version"] == "truth-v1"
    assert records[0]["answer"] == "private response"
    result = metrics_mod.compute_metrics(records)
    assert result["provenance"]["complete"] == 1
    assert "private response" not in json.dumps(result)


def test_same_question_on_distinct_samples_is_allowed(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,sample_id,ground_truth_version,"
        "question_id,answer,is_correct\n"
        "p1,baseline_first,baseline,app-a,v1,q1,A,true\n"
        "p1,baseline_first,baseline,app-b,v1,q1,B,false\n",
    )
    rows = metrics_mod.load_records(path, require_provenance=True)
    assert metrics_mod.compute_metrics(rows)["records"] == 2


def test_duplicate_on_same_sample_is_rejected(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,sample_id,question_id,is_correct\n"
        "p1,baseline_first,baseline,app-a,q1,true\n"
        "p1,baseline_first,baseline,app-a,q1,false\n",
    )
    with pytest.raises(ValueError, match="duplicate answer"):
        metrics_mod.load_records(path)


def test_strict_provenance_requires_sample_and_auditable_judgement(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline,q1,true\n",
    )
    with pytest.raises(ValueError, match="sample_id is required"):
        metrics_mod.load_records(path, require_provenance=True)
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,sample_id,ground_truth_version,"
        "question_id,is_correct\n"
        "p1,baseline_first,baseline,app-a,v1,q1,true\n",
    )
    with pytest.raises(ValueError, match="judged answer requires"):
        metrics_mod.load_records(path, require_provenance=True)


def test_strict_provenance_accepts_explained_missing_answer(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,sample_id,ground_truth_version,"
        "question_id,is_correct,notes\n"
        "p1,baseline_first,baseline,app-a,v1,q1,true,answer unavailable\n",
    )
    assert len(metrics_mod.load_records(path, require_provenance=True)) == 1


def test_conflicting_condition_fails_both_entrypoints(tmp_path):
    path = write_csv(
        tmp_path,
        "participant_id,condition,material,question_id,is_correct\n"
        "p1,baseline_first,baseline,q1,true\n"
        "p1,report_first,privacyTrace,q2,false\n",
    )
    with pytest.raises(ValueError, match="conflicting condition"):
        metrics_mod.load_records(path)
    rows = [
        answer("p1", "baseline_first", "baseline", True, question_id="q1"),
        answer("p1", "report_first", "privacyTrace", False, question_id="q2"),
    ]
    with pytest.raises(ValueError, match="conflicting condition"):
        metrics_mod.compute_metrics(rows)


def test_different_participants_can_be_assigned_different_orders():
    rows = [
        answer("p1", "baseline_first", "baseline", True),
        answer("p2", "report_first", "privacyTrace", True),
    ]
    assert metrics_mod.compute_metrics(rows)["participants"] == 2
