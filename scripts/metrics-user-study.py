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
(finite, non-negative number; empty means not measured), ``misconception``
(free text; separate multiple concepts with ``;``). An empty ``is_correct``
means the answer was never judged: it is counted under ``missing`` and left out
of every rate, so unjudged rows cannot silently turn into wrong answers. No
participant identity is exposed beyond anonymized ids.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

REQUIRED = {"participant_id", "condition", "material", "question_id", "is_correct"}
TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f"}
MATERIALS = {"baseline", "privacyTrace"}
NUMERIC_COLUMN = "evidence_loc_seconds"
CONCEPT_COLUMN = "misconception"


def parse_bool(value: str) -> bool | None:
    """Parse a judged cell; empty means not judged; raise on anything ambiguous."""
    token = value.strip().lower()
    if token in TRUE_VALUES:
        return True
    if token in FALSE_VALUES:
        return False
    if not token:
        return None
    raise ValueError(f"is_correct must be a boolean value or empty, got {value!r}")


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


def split_concepts(value: str) -> list[str]:
    """Split a misconception cell on ``;`` and drop empty fragments."""
    return [part.strip() for part in value.split(";") if part.strip()]


def load_records(path: Path) -> list[dict]:
    """Load and validate the one-row-per-answer CSV."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("record file has no header")
        missing = sorted(REQUIRED - set(reader.fieldnames))
        if missing:
            raise ValueError(f"record file is missing required columns: {missing}")
        records = []
        for row in reader:
            records.append(
                {
                    "participant_id": row["participant_id"].strip(),
                    "condition": row["condition"].strip(),
                    "material": parse_material(row["material"]),
                    "question_id": row["question_id"].strip(),
                    "is_correct": parse_bool(row["is_correct"]),
                    "evidence_loc_seconds": parse_seconds(
                        row.get(NUMERIC_COLUMN, "")
                    ),
                    "misconception": row.get(CONCEPT_COLUMN, "").strip(),
                }
            )
    if not records:
        raise ValueError("record file has no answer rows")
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
    """Aggregate records into the Issue #23 metric report."""
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
        condition: distribution(
            [
                record["evidence_loc_seconds"]
                for record in records
                if record["condition"] == condition
                and record["evidence_loc_seconds"] is not None
            ]
        )
        for condition in conditions
    }
    locate_by_material = {
        material: distribution(
            [
                record["evidence_loc_seconds"]
                for record in records
                if record["material"] == material
                and record["evidence_loc_seconds"] is not None
            ]
        )
        for material in materials
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
    locate = metrics["evidence_locate_time_seconds"]["overall"]
    lines += ["", "## 定位证据耗时（秒）", f"- 记录数：{locate['count']}"]
    if locate["count"]:
        lines.append(
            "- 最小/最大/均值/中位/P90："
            f"{locate['min']} / {locate['max']} / {locate['mean']} / "
            f"{locate['median']} / {locate['p90']}"
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
            "misconception": "权限=调用",
        },
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "material": "privacyTrace",
            "question_id": "q2",
            "is_correct": False,
            "evidence_loc_seconds": 30.0,
            "misconception": "",
        },
        {
            "participant_id": "p2",
            "condition": "report_first",
            "material": "privacyTrace",
            "question_id": "q1",
            "is_correct": True,
            "evidence_loc_seconds": 8.0,
            "misconception": "权限=调用;法律判定",
        },
        {
            "participant_id": "p2",
            "condition": "report_first",
            "material": "baseline",
            "question_id": "q2",
            "is_correct": True,
            "evidence_loc_seconds": None,
            "misconception": "",
        },
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "material": "baseline",
            "question_id": "q3",
            "is_correct": None,
            "evidence_loc_seconds": None,
            "misconception": "",
        },
        {
            "participant_id": "p1",
            "condition": "baseline_first",
            "material": "privacyTrace",
            "question_id": "q4",
            "is_correct": True,
            "evidence_loc_seconds": 10.0,
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
        "--selfcheck",
        action="store_true",
        help="run the built-in fixture check and exit",
    )
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return
    metrics = compute_metrics(load_records(args.input))
    if args.format == "json":
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(metrics))


if __name__ == "__main__":
    main()
