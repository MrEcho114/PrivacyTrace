"""Freeze independent truth before prediction, then compare immutable run outputs."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .consistency import evaluate
from .controlled import predictions
from .controlled_inputs import BuildReceipt, input_hashes, load_case, source_hashes
from .models import EvaluationInput, MatchStatus, Model
from .policy_intake import digest, read_safe
from .runtime_models import Report, ScanCoverage

SCHEMES = ("permission_keywords", "api_flat", "privacytrace")
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class PredictionRun(Model):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^C[0-9]{2}$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
    analysis_context: Literal["CONTROLLED_EVALUATION"]
    status: Literal["SUCCEEDED", "FAILED", "CANCELLED"]
    started_at: datetime
    generated_at: datetime
    input_hashes: dict[str, Hash]
    source_hashes: dict[str, Hash]
    apk_sha256: Hash
    build_receipt_sha256: Hash
    toolchain_sha256: Hash
    preparation: str
    counting_unit: str
    failure_policy: str
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    schemes: dict[str, dict]
    errors: list[dict]
    report_sha256: Hash | None = None
    ruleset_version: str | None = None
    coverage: ScanCoverage | None = None

    @model_validator(mode="after")
    def check_state(self):
        if (
            self.started_at.tzinfo is None
            or self.generated_at.tzinfo is None
            or self.generated_at < self.started_at
        ):
            raise ValueError("Invalid prediction interval")
        if self.status == "SUCCEEDED":
            if not self.report_sha256 or not self.ruleset_version or not self.coverage:
                raise ValueError("Successful predictions require a report")
        elif self.schemes or self.report_sha256 or self.coverage or self.ruleset_version:
            raise ValueError("Failed scans cannot carry successful predictions")
        return self


def validate_run(path, raw):
    run = PredictionRun.model_validate_json(raw)
    build_raw = read_safe(path.parent / "build.json")
    build = BuildReceipt.model_validate_json(build_raw)
    if (
        digest(build_raw) != run.build_receipt_sha256
        or build.case_id != run.case_id
        or build.apk_sha256 != run.apk_sha256
        or build.source_hashes != run.source_hashes
        or build.toolchain_sha256 != run.toolchain_sha256
    ):
        raise ValueError("Prediction does not match build receipt")
    if run.status == "SUCCEEDED":
        report_raw = read_safe(path.parent / "report.json")
        report = Report.model_validate_json(report_raw)
        bundle = EvaluationInput(
            job=report.job,
            evidence=report.evidence,
            behaviors=report.behaviors,
            policy_documents=report.policy_documents,
            policy_claims=report.policy_claims,
        )
        inputs_digest = digest(json.dumps(run.input_hashes, sort_keys=True).encode())
        if (
            digest(report_raw) != run.report_sha256
            or report.job.id != run.job_id
            or report.job.state != "SUCCEEDED"
            or report.job.controlled_case_id != run.case_id
            or report.sample.apk_sha256 != run.apk_sha256
            or report.job.ruleset_version != run.ruleset_version
            or report.coverage != run.coverage
            or report.result != evaluate(bundle)
            or report.tools.get("controlled_input_sha256") != inputs_digest
            or report.tools.get("controlled_build_receipt_sha256") != run.build_receipt_sha256
            or run.schemes != predictions(report)
        ):
            raise ValueError("Prediction differs from validated report")
    return run.model_dump(mode="json", exclude_none=True)


class Target(Model):
    case_id: str = Field(pattern=r"^C[0-9]{2}$")
    data_type: str
    action: Literal["ACCESS"]
    expected: MatchStatus
    reason: str = Field(min_length=1)


class GroundTruth(Model):
    schema_version: Literal[1]
    counting_unit: str
    targets: list[Target] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def distinct_targets(self):
        keys = [(t.case_id, t.data_type, t.action) for t in self.targets]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate ground-truth target")
        return self


def write_new(path, value):
    path = Path(path).absolute()
    if any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)
    ):
        raise ValueError("Linked output is not allowed")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def freeze_inputs(suite, output):
    raw = read_safe(suite / "ground-truth.json")
    truth = GroundTruth.model_validate_json(raw)
    cases = {}
    for case_id in sorted({t.case_id for t in truth.targets}):
        case_dir = suite / case_id
        if load_case(case_dir).case_id != case_id:
            raise ValueError("Case directory differs from manifest")
        cases[case_id] = {
            "input_hashes": input_hashes(case_dir),
            "source_hashes": source_hashes(case_dir),
        }
    value = {
        "schema_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "labels_sha256": digest(raw),
        "cases": cases,
        "toolchain_sha256": digest(read_safe(suite / "toolchain.json")),
    }
    write_new(output, value)
    return {"status": "FROZEN", "labels_sha256": value["labels_sha256"]}


def compare(freeze_path, labels_path, paths, output):
    frozen_raw, labels_raw = read_safe(freeze_path), read_safe(labels_path)
    frozen = json.loads(frozen_raw)
    if frozen["schema_version"] != 1 or digest(labels_raw) != frozen["labels_sha256"]:
        raise ValueError("Ground truth changed after freezing")
    truth = GroundTruth.model_validate_json(labels_raw)
    frozen_at = datetime.fromisoformat(frozen["frozen_at"])
    if frozen_at.tzinfo is None:
        raise ValueError("Freeze time requires timezone")
    if {t.case_id for t in truth.targets} != set(frozen["cases"]):
        raise ValueError("Frozen cases differ from targets")
    runs, artifacts = {}, []
    for path in paths:
        raw = read_safe(path)
        run = validate_run(path, raw)
        case_id = run["case_id"]
        if case_id in runs or case_id not in frozen["cases"]:
            raise ValueError("Duplicate or unknown prediction case")
        if (
            run["schema_version"] != 1
            or run["analysis_context"] != "CONTROLLED_EVALUATION"
            or run["input_hashes"] != frozen["cases"][case_id]["input_hashes"]
            or run["source_hashes"] != frozen["cases"][case_id]["source_hashes"]
            or run["toolchain_sha256"] != frozen["toolchain_sha256"]
            or datetime.fromisoformat(run["started_at"]) < frozen_at
            or datetime.fromisoformat(run["generated_at"])
            < datetime.fromisoformat(run["started_at"])
        ):
            raise ValueError("Prediction not bound to pre-frozen inputs")
        if run["status"] not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            raise ValueError("Unsupported run state")
        if run["status"] == "SUCCEEDED" and set(run["schemes"]) != set(SCHEMES):
            raise ValueError("Successful prediction requires every scheme")
        for scheme in run["schemes"].values():
            for row in scheme["rows"]:
                for status in row["statuses"]:
                    MatchStatus(status)
        runs[case_id] = run
        artifacts.append({"case_id": case_id, "predictions_sha256": digest(raw)})
    rows = []
    for target in truth.targets:
        run = runs.get(target.case_id)
        for scheme in SCHEMES:
            observed = run.get("schemes", {}).get(scheme, {}).get("rows", []) if run else []
            actual = sorted(
                {
                    s
                    for row in observed
                    if row["data_type"] == target.data_type
                    for s in row["statuses"]
                }
            ) or ["ABSTAIN"]
            state = run["status"] if run else "NOT_RUN"
            coverage = run.get("coverage", {}).get("status", "NOT_AVAILABLE") if run else "NOT_RUN"
            rows.append(
                {
                    "case_id": target.case_id,
                    "data_type": target.data_type,
                    "scheme": scheme,
                    "expected": target.expected.value,
                    "actual": actual,
                    "run_status": state,
                    "coverage": coverage,
                    "matches": state == "SUCCEEDED"
                    and coverage == "COMPLETE"
                    and actual == [target.expected.value],
                }
            )
    result = {
        "schema_version": 1,
        "target_count": len(truth.targets),
        "rows": rows,
        "freeze_sha256": digest(frozen_raw),
        "labels_sha256": digest(labels_raw),
        "artifacts": artifacts,
        "metrics": "N/A: two diagnostic scenarios, no precision advantage claim",
    }
    write_new(output / "comparison.json", result)
    lines = [
        "# Controlled comparison",
        "",
        "Two diagnostic scenarios; no precision claim.",
        "",
        "| Case | Type | Scheme | Expected | Actual | Run | Coverage | Match |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(row[k])
                for k in (
                    "case_id",
                    "data_type",
                    "scheme",
                    "expected",
                    "actual",
                    "run_status",
                    "coverage",
                    "matches",
                )
            )
            + " |"
        )
    with (output / "comparison.md").open("x", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return {"status": "COMPARED", "target_count": len(truth.targets)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("--suite-dir", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    comparison = sub.add_parser("compare")
    comparison.add_argument("--freeze", type=Path, required=True)
    comparison.add_argument("--labels", type=Path, required=True)
    comparison.add_argument("--predictions", type=Path, nargs="*", default=[])
    comparison.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (
            freeze_inputs(args.suite_dir, args.output)
            if args.command == "freeze"
            else compare(args.freeze, args.labels, args.predictions, args.output_dir)
        )
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        print(json.dumps({"status": "FAILED", "error": "CONTROLLED_COMPARISON_INVALID"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
