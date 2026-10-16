"""Compute deterministic metrics for the PrivacyTrace user study (Issue #23).

Reads one row per question answer (schema in ``evidence/user-study.template.csv``)
and reports the aggregates named by Issue #23: accurate judgments, time to
locate evidence, and concept-misunderstanding counts. A within-subject
comparison has two effects that must stay apart, so every number is split by
the reading order (``condition``) *and* by the material the answer was actually
given against (``material``, ``baseline`` or ``privacyTrace``), and the cross
tab of both is reported as well. Grouping by ``condition`` alone cannot say
whether a difference comes from the material or from having read the other
material first. The same input always produces the same output so a reviewer
can recompute every number.

Required columns: ``participant_id``, ``condition``, ``material``,
``question_id``, ``is_correct``. Optional columns: ``evidence_loc_seconds``
(finite, non-negative number; empty means not measured), ``evidence_located``
(``true`` / ``false`` / empty, the same tokens ``is_correct`` accepts), and
``misconception`` (free text; separate multiple concepts with ``;``). An empty
``is_correct`` means the answer was never judged: it is counted under
``missing`` and left out of every rate, so unjudged rows cannot silently turn
into wrong answers. A missing ``evidence_located`` column is read as all-empty,
which means no question asked for a location. No participant identity is
exposed beyond anonymized ids.

The experiment design is fixed, so a record may not invent its own:
``condition`` accepts only the two designed reading orders, ``baseline_first``
and ``report_first`` (see ``evidence/user-study-facilitator-script.template.md``),
and ``participant_id`` and ``question_id`` must be non-empty ids of letters,
digits, ``_``, ``.`` and ``-``. An answer is keyed by ``(participant_id, sample_id, question_id, material)``.
This permits the same question id to recur across different Apps, but prevents
double counting a response for the same sample. Older five-column inputs have
empty sample ids and retain the previous duplicate policy.
Within one dataset a participant has one assigned reading order; conflicting
``condition`` values are rejected.

Optional ``sample_id``, ``ground_truth_version``, and ``answer`` fields are
retained internally for auditing. Aggregate output only publishes provenance
completeness counts, not raw answers. Formal collection may enable
``--require-provenance`` to require sample and ground truth identifiers,
and either the answer or an explanatory note for an already judged row.

Locate-time accounting (``evidence_locate_time_seconds``). Durations are split
by ``evidence_located`` so that a fast failure can never be reported as faster
than a slow success:

* ``success`` -- rows with ``evidence_located == true`` (locating was required
  and the participant pointed at a concrete place). ``records`` counts every
  such row; ``timed`` is the duration distribution over those of them whose
  ``evidence_loc_seconds`` is not empty.
* ``failure`` -- rows with ``evidence_located == false`` (locating was required
  and the participant did not point at a concrete place). Same shape as
  ``success``, counted and reported separately: these durations are failed
  attempts, never successes.
* ``not_required`` -- rows with an empty ``evidence_located``: the question did
  not ask for a location, which is not a failure. ``records`` counts them; they
  enter no distribution and no rate.
* ``success_rate`` -- ``success.records / (success.records + failure.records)``,
  i.e. ``true / (true + false)``; the empty cells stay out of the denominator
  and ``None`` (rendered as ``—``) is reported when that denominator is ``0``.
* ``by_material_outcome`` / ``by_condition_outcome`` -- the same block computed
  inside each material and each reading order.
* ``overall`` / ``by_material`` / ``by_condition`` -- the older mixed-duration
  distributions (every non-empty duration regardless of outcome), kept so
  earlier reports stay reproducible. They must not be used to compare materials
  or orders; use the success blocks for that.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path

REQUIRED = {"participant_id", "condition", "material", "question_id", "is_correct"}
TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f"}
MATERIALS = {"baseline", "privacyTrace"}
CONDITIONS = {"baseline_first", "report_first"}
ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")
PROVENANCE_FIELDS = ("sample_id", "ground_truth_version", "answer")
NUMERIC_COLUMN = "evidence_loc_seconds"
LOCATED_COLUMN = "evidence_located"
CONCEPT_COLUMN = "misconception"


def parse_tristate(value: str, column: str) -> bool | None:
    """Parse a tri-state boolean cell; empty means the column does not apply."""
    token = value.strip().lower()
    if token in TRUE_VALUES:
        return True
    if token in FALSE_VALUES:
        return False
    if not token:
        return None
    raise ValueError(f"{column} must be a boolean value or empty, got {value!r}")


def parse_bool(value: str) -> bool | None:
    """Parse a judged cell; empty means not judged; raise on anything ambiguous."""
    return parse_tristate(value, "is_correct")


def parse_located(value: str) -> bool | None:
    """Parse ``evidence_located``; empty means the question asked for no location."""
    return parse_tristate(value, LOCATED_COLUMN)


def parse_seconds(value: str) -> float | None:
    """Parse an optional non-negative finite duration; empty means not measured."""
    token = value.strip()
    if not token:
        return None
    try:
        number = float(token)
    except ValueError as exc:
        raise ValueError(
            f"evidence_loc_seconds must be a number, got {value!r}"
        ) from exc
    if not math.isfinite(number):
        raise ValueError("evidence_loc_seconds must be finite")
    if number < 0:
        raise ValueError("evidence_loc_seconds must be non-negative")
    return number


def parse_material(value: str) -> str:
    """Parse the material an answer was given against; raise on unknown values."""
    material = value.strip()
    if material not in MATERIALS:
        raise ValueError(
            f"material must be one of {sorted(MATERIALS)}, got {value!r}"
        )
    return material


def parse_condition(value: str) -> str:
    """Parse the designed reading order; raise on any other spelling."""
    condition = value.strip()
    if condition not in CONDITIONS:
        raise ValueError(
            f"condition must be one of {sorted(CONDITIONS)}, got {value!r}"
        )
    return condition


def parse_id(value: str, column: str) -> str:
    """Parse a required identifier; an empty or malformed id is rejected."""
    identifier = value.strip()
    if not identifier:
        raise ValueError(f"{column} must not be empty, got {value!r}")
    if not ID_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"{column} must match {ID_PATTERN.pattern}, got {value!r}"
        )
    return identifier


def split_concepts(value: str) -> list[str]:
    """Split a misconception cell on ``;`` and drop empty fragments."""
    return [part.strip() for part in value.split(";") if part.strip()]


def answer_key(record: dict) -> tuple[str, str, str, str]:
    """One participant/sample/question/material response."""
    return (
        record["participant_id"],
        record.get("sample_id", ""),
        record["question_id"],
        record["material"],
    )


def validate_condition_consistency(
    records: list[dict], line_numbers: list[int] | None = None
) -> None:
    """A participant belongs to only one order group within this dataset."""
    first_seen: dict[str, tuple[str, int]] = {}
    for index, record in enumerate(records):
        participant = record["participant_id"]
        condition = record["condition"]
        previous = first_seen.get(participant)
        if previous is None:
            first_seen[participant] = (condition, index)
        elif previous[0] != condition:
            where = ""
            if line_numbers is not None:
                where = (
                    f" (lines {line_numbers[previous[1]]} "
                    f"and {line_numbers[index]})"
                )
            raise ValueError(
                f"conflicting condition for participant_id={participant!r}: "
                f"{previous[0]!r} vs {condition!r}{where}"
            )


def validate_provenance(records: list[dict]) -> None:
    """Require enough source information to review formal observations."""
    for index, record in enumerate(records, start=1):
        for field in ("sample_id", "ground_truth_version"):
            if not record.get(field):
                raise ValueError(f"record {index}: {field} is required for provenance")
        if record["is_correct"] is not None and not (
            record.get("answer") or record.get("notes")
        ):
            raise ValueError(
                f"record {index}: judged answer requires answer or explanatory notes"
            )


def provenance_counts(records: list[dict]) -> dict:
    """Only publish aggregate completeness; never participants' answers."""
    return {
        "complete": sum(
            all(r.get(field) for field in PROVENANCE_FIELDS) for r in records
        ),
        "total": len(records),
        "with_sample_id": sum(bool(r.get("sample_id")) for r in records),
        "with_ground_truth_version": sum(
            bool(r.get("ground_truth_version")) for r in records
        ),
        "with_answer": sum(bool(r.get("answer")) for r in records),
    }


def reject_repeated_answers(
    records: list[dict], line_numbers: list[int] | None = None
) -> None:
    """Raise when one participant/sample/question/material response is repeated.

    ``line_numbers``, when given, carries the source line of each record so the
    error can point at both rows; in-memory records are reported by key alone.
    """
    first_seen: dict[tuple[str, str, str, str], int] = {}
    for index, record in enumerate(records):
        key = answer_key(record)
        previous = first_seen.get(key)
        if previous is None:
            first_seen[key] = index
            continue
        where = ""
        if line_numbers is not None:
            where = (
                f"; first recorded on line {line_numbers[previous]}, "
                f"repeated on line {line_numbers[index]}"
            )
        raise ValueError(
            f"duplicate answer for participant_id={key[0]!r}, "
            f"sample_id={key[1]!r}, question_id={key[2]!r}, "
            f"material={key[3]!r}{where}"
        )


def load_records(path: Path, *, require_provenance: bool = False) -> list[dict]:
    """Load and validate the one-row-per-answer CSV."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("record file has no header")
        missing = sorted(REQUIRED - set(reader.fieldnames))
        if missing:
            raise ValueError(f"record file is missing required columns: {missing}")
        records = []
        line_numbers = []
        for row in reader:
            line_numbers.append(reader.line_num)
            records.append(
                {
                    "participant_id": parse_id(
                        row["participant_id"], "participant_id"
                    ),
                    "condition": parse_condition(row["condition"]),
                    "material": parse_material(row["material"]),
                    "question_id": parse_id(row["question_id"], "question_id"),
                    "sample_id": (
                        parse_id(row["sample_id"], "sample_id")
                        if row.get("sample_id", "").strip()
                        else ""
                    ),
                    "ground_truth_version": row.get(
                        "ground_truth_version", ""
                    ).strip(),
                    "answer": row.get("answer", "").strip(),
                    "notes": row.get("notes", "").strip(),
                    "is_correct": parse_bool(row["is_correct"]),
                    "evidence_loc_seconds": parse_seconds(
                        row.get(NUMERIC_COLUMN, "")
                    ),
                    "evidence_located": parse_located(row.get(LOCATED_COLUMN, "")),
                    "misconception": row.get(CONCEPT_COLUMN, "").strip(),
                }
            )
    if not records:
        raise ValueError("record file has no answer rows")
    reject_repeated_answers(records, line_numbers)
    validate_condition_consistency(records, line_numbers)
    if require_provenance:
        validate_provenance(records)
    return records


def percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile over an already-sorted non-empty list."""
    index = min(
        len(sorted_values) - 1,
        max(0, math.ceil(pct / 100 * len(sorted_values)) - 1),
    )
    return sorted_values[index]


def distribution(values: list[float]) -> dict:
    """Summary statistics for a list of durations."""
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": round(ordered[0], 6),
        "max": round(ordered[-1], 6),
        "mean": round(statistics.mean(ordered), 6),
        "median": round(statistics.median(ordered), 6),
        "p90": round(percentile(ordered, 90), 6),
    }


def locate_distribution(subset: list[dict]) -> dict:
    """Duration distribution over the subset's rows that carry a measured time."""
    return distribution(
        [
            record["evidence_loc_seconds"]
            for record in subset
            if record["evidence_loc_seconds"] is not None
        ]
    )


def locate_outcome_block(subset: list[dict]) -> dict:
    """Split a subset by ``evidence_located`` into success, failure, not required."""
    success = [record for record in subset if record["evidence_located"] is True]
    failure = [record for record in subset if record["evidence_located"] is False]
    not_required = [record for record in subset if record["evidence_located"] is None]
    judged = len(success) + len(failure)
    return {
        "success": {"records": len(success), "timed": locate_distribution(success)},
        "failure": {"records": len(failure), "timed": locate_distribution(failure)},
        "not_required": {"records": len(not_required)},
        "success_rate": round(len(success) / judged, 6) if judged else None,
    }


def accuracy_block(subset: list[dict]) -> dict:
    """Accuracy of a subset with its denominator and missing count made explicit."""
    answered = [record for record in subset if record["is_correct"] is not None]
    correct = sum(1 for record in answered if record["is_correct"])
    return {
        "correct": correct,
        "answered": len(answered),
        "missing": len(subset) - len(answered),
        "rate": round(correct / len(answered), 6) if answered else None,
    }


def compute_metrics(records: list[dict]) -> dict:
    """Aggregate records into the Issue #23 metric report.

    Records built in memory carry the same contract as a loaded CSV: a repeated
    ``(participant_id, sample_id, question_id, material)`` combination is rejected.
    """
    reject_repeated_answers(records)
    validate_condition_consistency(records)
    participants = sorted({record["participant_id"] for record in records})
    conditions = sorted({record["condition"] for record in records})
    materials = sorted({record["material"] for record in records})

    by_condition = {
        condition: accuracy_block(
            [record for record in records if record["condition"] == condition]
        )
        for condition in conditions
    }
    by_material = {
        material: accuracy_block(
            [record for record in records if record["material"] == material]
        )
        for material in materials
    }
    by_material_and_condition = {
        f"{material}|{condition}": accuracy_block(
            [
                record
                for record in records
                if record["material"] == material
                and record["condition"] == condition
            ]
        )
        for material in materials
        for condition in conditions
    }
    by_participant = {
        participant: accuracy_block(
            [record for record in records if record["participant_id"] == participant]
        )
        for participant in participants
    }

    locate_times = [
        record["evidence_loc_seconds"]
        for record in records
        if record["evidence_loc_seconds"] is not None
    ]
    locate_by_condition = {
        condition: locate_distribution(
            [record for record in records if record["condition"] == condition]
        )
        for condition in conditions
    }
    locate_by_material = {
        material: locate_distribution(
            [record for record in records if record["material"] == material]
        )
        for material in materials
    }
    locate_outcome_by_material = {
        material: locate_outcome_block(
            [record for record in records if record["material"] == material]
        )
        for material in materials
    }
    locate_outcome_by_condition = {
        condition: locate_outcome_block(
            [record for record in records if record["condition"] == condition]
        )
        for condition in conditions
    }

    concept_totals: Counter[str] = Counter()
    condition_totals: Counter[str] = Counter()
    material_totals: Counter[str] = Counter()
    records_with = 0
    participants_with: set[str] = set()
    for record in records:
        concepts = split_concepts(record["misconception"])
        if concepts:
            records_with += 1
            participants_with.add(record["participant_id"])
            for concept in concepts:
                concept_totals[concept] += 1
                condition_totals[record["condition"]] += 1
                material_totals[record["material"]] += 1

    return {
        "records": len(records),
        "participants": len(participants),
        "provenance": provenance_counts(records),
        "conditions": conditions,
        "materials": materials,
        "accuracy": {
            **accuracy_block(records),
            "by_material": by_material,
            "by_material_and_condition": by_material_and_condition,
            "by_condition": by_condition,
            "by_participant": by_participant,
        },
        "evidence_locate_time_seconds": {
            **locate_outcome_block(records),
            "by_material_outcome": locate_outcome_by_material,
            "by_condition_outcome": locate_outcome_by_condition,
            "overall": distribution(locate_times),
            "by_material": locate_by_material,
            "by_condition": locate_by_condition,
        },
        "misconceptions": {
            "total_count": sum(concept_totals.values()),
            "records_with_misconception": records_with,
            "participants_with_misconception": len(participants_with),
            "by_concept": dict(sorted(concept_totals.items())),
            "by_material": dict(sorted(material_totals.items())),
            "by_condition": dict(sorted(condition_totals.items())),
        },
    }


def rate_text(values: dict) -> str:
    """Render one accuracy block with its denominator and missing count."""
    share = "n/a" if values["rate"] is None else f"{values['rate']:.4f}"
    return (
        f"{values['correct']}/{values['answered']} = {share}"
        f"（未判 {values['missing']}）"
    )


def duration_text(values: dict) -> str:
    """Render one duration distribution, or ``—`` when nothing was measured."""
    if not values["count"]:
        return "—（0 条有时长）"
    return (
        f"{values['min']} / {values['max']} / {values['mean']} / "
        f"{values['median']} / {values['p90']}（{values['count']} 条有时长）"
    )


def locate_outcome_text(block: dict) -> str:
    """Render one success/failure/not-required block with its rate denominator."""
    rate = "—" if block["success_rate"] is None else f"{block['success_rate']:.4f}"
    return (
        f"成功率 {rate}"
        f"（成功 {block['success']['records']} / 失败 {block['failure']['records']}，"
        f"未要求定位 {block['not_required']['records']} 不计入分母）"
        f"；成功定位耗时：{duration_text(block['success']['timed'])}"
        f"；定位失败尝试耗时：{duration_text(block['failure']['timed'])}"
    )


def render_markdown(metrics: dict) -> str:
    """Render the metric report as plain Markdown."""
    accuracy = metrics["accuracy"]
    lines = [
        "# 用户理解测试指标",
        "",
        f"- 作答记录：{metrics['records']} 条；参与者：{metrics['participants']} 人",
        f"- 未判（`is_correct` 空）记录：{accuracy['missing']} 条，不计入任何比率",
        "",
        "## 各材料准确率（材料效果）",
    ]
    for material, values in accuracy["by_material"].items():
        lines.append(f"- {material}: {rate_text(values)}")
    lines += ["", "## 各阅读顺序准确率（顺序效果）"]
    for condition, values in accuracy["by_condition"].items():
        lines.append(f"- {condition}: {rate_text(values)}")
    lines += ["", "## 材料×顺序交叉准确率"]
    for key, values in accuracy["by_material_and_condition"].items():
        lines.append(f"- {key}: {rate_text(values)}")
    locate = metrics["evidence_locate_time_seconds"]
    lines += [
        "",
        "## 定位证据耗时（秒）",
        (
            "- 口径：按 `evidence_located` 分「成功定位 / 定位失败尝试 / 未要求定位」；"
            "`evidence_located` 空＝该题没要求定位，只计数，不进任何分布与比率"
        ),
        f"- 全部记录：{locate_outcome_text(locate)}",
    ]
    for material, block in locate["by_material_outcome"].items():
        lines.append(f"- 材料 {material}：{locate_outcome_text(block)}")
    for condition, block in locate["by_condition_outcome"].items():
        lines.append(f"- 阅读顺序 {condition}：{locate_outcome_text(block)}")
    lines.append(
        "- 对照（不分成败的混合口径，仅用于与旧报告对数，不得据此比较材料）："
        f"{duration_text(locate['overall'])}"
    )
    misconceptions = metrics["misconceptions"]
    lines += [
        "",
        "## 概念误解",
        (
            f"- 总计数：{misconceptions['total_count']}；"
            f"涉及记录：{misconceptions['records_with_misconception']}；"
            f"涉及参与者：{misconceptions['participants_with_misconception']}"
        ),
    ]
    for concept, count in misconceptions["by_concept"].items():
        lines.append(f"- {concept}: {count}")
    return "\n".join(lines) + "\n"


def selfcheck() -> None:
    """Run against a small built-in fixture and assert the expected numbers."""
    records = [
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "material": "baseline",
            "question_id": "q1",
            "is_correct": True,
            "evidence_loc_seconds": 12.0,
            "evidence_located": True,
            "misconception": "权限=调用",
        },
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "material": "privacyTrace",
            "question_id": "q2",
            "is_correct": False,
            "evidence_loc_seconds": 30.0,
            "evidence_located": False,
            "misconception": "",
        },
        {
            "participant_id": "p2",
            "condition": "report_first",
            "material": "privacyTrace",
            "question_id": "q1",
            "is_correct": True,
            "evidence_loc_seconds": 8.0,
            "evidence_located": True,
            "misconception": "权限=调用;法律判定",
        },
        {
            "participant_id": "p2",
            "condition": "report_first",
            "material": "baseline",
            "question_id": "q2",
            "is_correct": True,
            "evidence_loc_seconds": None,
            "evidence_located": None,
            "misconception": "",
        },
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "material": "baseline",
            "question_id": "q3",
            "is_correct": None,
            "evidence_loc_seconds": None,
            "evidence_located": None,
            "misconception": "",
        },
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "material": "privacyTrace",
            "question_id": "q4",
            "is_correct": True,
            "evidence_loc_seconds": 10.0,
            "evidence_located": True,
            "misconception": "",
        },
    ]
    metrics = compute_metrics(records)
    assert metrics["records"] == 6
    assert metrics["participants"] == 2
    assert metrics["accuracy"]["correct"] == 4
    assert metrics["accuracy"]["answered"] == 5
    assert metrics["accuracy"]["missing"] == 1
    assert metrics["accuracy"]["by_material"]["baseline"]["rate"] == 1.0
    assert metrics["accuracy"]["by_condition"]["report_first"]["rate"] == 1.0
    assert metrics["evidence_locate_time_seconds"]["overall"]["median"] == 11.0
    locate = metrics["evidence_locate_time_seconds"]
    assert locate["success"]["records"] == 3
    assert locate["success"]["timed"]["count"] == 3
    assert locate["success"]["timed"]["min"] == 8.0
    assert locate["success"]["timed"]["median"] == 10.0
    assert locate["failure"]["records"] == 1
    assert locate["failure"]["timed"]["count"] == 1
    assert locate["failure"]["timed"]["min"] == 30.0
    assert locate["not_required"]["records"] == 2
    assert locate["success_rate"] == 0.75
    assert locate["by_material_outcome"]["baseline"]["success_rate"] == 1.0
    assert locate["by_material_outcome"]["privacyTrace"]["success_rate"] == round(2 / 3, 6)
    assert metrics["misconceptions"]["total_count"] == 3
    print("selfcheck: OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("evidence/user-study.csv"),
        help="one-row-per-answer CSV (default: evidence/user-study.csv)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="output format (default: json)",
    )
    parser.add_argument(
        "--require-provenance",
        action="store_true",
        help="reject records without auditable provenance",
    )
    parser.add_argument(
        "--selfcheck",
        action="store_true",
        help="run the built-in fixture check and exit",
    )
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return
    metrics = compute_metrics(
        load_records(args.input, require_provenance=args.require_provenance)
    )
    if args.format == "json":
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(metrics))


if __name__ == "__main__":
    main()
