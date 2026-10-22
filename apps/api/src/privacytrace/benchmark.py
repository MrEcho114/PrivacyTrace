"""Three schemes on identical scanned materials; scoring reads frozen labels afterwards."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .benchmark_locations import REFERENCE, expected_calls, load_reference, locator
from .controlled import SUITE, SUITES, analyze, scenario_ids
from .isolated_scan import docker_prefix
from .job_store import JobStore
from .models import EvaluationInput
from .policy_intake import digest, read_safe
from .resources import ACTIVE_SDK_SIGNATURES_VERSION, ROOT, SDK_SIGNATURE_FILES, taxonomy
from .wsl import wsl_distro

SCHEMES = ("permission_keyword", "api_flat", "privacytrace")
SCHEME_INPUTS = {
    "permission_keyword": "Same APK/permissions/policy/evidence/claims available; uses permission "
    "mappings and exact data-type phrases in complete provided text. "
    "No hierarchy, polarity or completeness gate; nominal baseline only.",
    "api_flat": "Same API invoke evidence, trusted full descriptors and context; exact flat "
    "data-type phrases in same policy text. No hierarchy, polarity or scope gate. "
    "Missing invoke abstains. No descriptor weakening.",
    "privacytrace": "Same materials; existing deterministic engine and controlled known facts. "
    "No expected labels. Reviews are optional local annotations, not signatures.",
}


def schemes(report):
    # Only features cross into the networkless worker. Results, reviews and labels are excluded.
    material = {
        "bundle": report.model_dump(
            mode="json",
            include={"job", "evidence", "behaviors", "policy_documents", "policy_claims"},
        ),
        "permissions": report.sample.permissions,
    }
    raw = json.dumps(material, ensure_ascii=True, sort_keys=True).encode()
    material["material_sha256"] = digest(raw)
    docker = docker_prefix()
    image = subprocess.check_output(
        [*docker, "image", "inspect", "privacytrace-worker:s1", "--format", "{{.Id}}"],
        text=True,
        timeout=30,
    ).strip()

    def local(path):
        if docker[0].lower().endswith("wsl.exe"):
            return subprocess.check_output(
                ["wsl.exe", "-d", wsl_distro(), "--exec", "wslpath", "-a", str(path)], text=True
            ).strip()
        return str(path)

    process = subprocess.run(
        [
            *docker,
            "run",
            "--rm",
            "-i",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--memory=256m",
            "--pids-limit=32",
            "--tmpfs=/tmp:rw,size=16m",
            "--user=65534:65534",
            "--mount",
            "type=bind,source="
            + local(ROOT / "apps/api/src")
            + ",target=/prediction/apps/api/src,readonly",
            "--mount",
            "type=bind,source=" + local(ROOT / "rules") + ",target=/prediction/rules,readonly",
            "--env",
            "PYTHONPATH=/prediction/apps/api/src",
            "--entrypoint",
            "/app/apps/api/.venv/bin/python",
            image,
            "-m",
            "privacytrace.benchmark_algorithms",
        ],
        input=json.dumps(material),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    output = json.loads(process.stdout)
    if not output["truth_files_absent"] or output["material_sha256"] != material["material_sha256"]:
        raise ValueError("Prediction isolation verification failed")
    output["prediction_image"] = image
    saved = sorted(
        (behavior.data_type, behavior.action, issue.status)
        for behavior in report.behaviors
        for issue in report.result.issues
        if issue.behavior_id == behavior.id
    )
    predicted = sorted(
        (item["data_type"], item["action"], item["status"])
        for item in output["predictions"]["privacytrace"]
    )
    if predicted != saved:
        raise ValueError("Isolated prediction disagrees with persisted report")
    return output


def validate_policy_spans(report):
    """Audit the current material with the same Unicode/codepoint contract as intake.

    Revalidate serialized values, including document identities and snapshot hashes;
    existing model instances may have been modified since their initial validation.
    Do not export policy text or exception messages containing private input.
    """
    material = report.model_dump(
        mode="json", include={"job", "evidence", "behaviors", "policy_documents", "policy_claims"},
    )
    try:
        bundle = EvaluationInput.model_validate(material)
    except ValidationError:
        return {"validated": False, "checked_evidence_ids": [],
                "errors": [{"code": "POLICY_EVIDENCE_INVALID"}]}
    return {
        "validated": True,
        "checked_evidence_ids": sorted(item.id for item in bundle.evidence
                                       if item.kind == "POLICY_SENTENCE"),
        "policy_document_sha256": {doc.id: doc.artifact.sha256 for doc in bundle.policy_documents},
        "errors": [],
    }


def predict(features, artifacts, store_dir, timeout, suite=SUITE):
    started = time.perf_counter()
    output = analyze(features, artifacts, store_dir, timeout, "controlled-" + uuid4().hex,
                     suite=suite)
    record = {
        "scenario_id": features.stem,
        # Local report/receipt paths stay in the private job store, never in CI artifacts.
        "analysis": {key: value for key, value in output.items()
                     if key in {"job_id", "status", "coverage", "counts", "human_review_gate",
                                "errors", "primary_error", "cleanup_errors"}},
        "elapsed_seconds": time.perf_counter() - started,
        "predictions": None,
    }
    if output["status"] == "SUCCEEDED":
        report = JobStore(store_dir).report(output["job_id"])
        policy_validation = validate_policy_spans(report)
        record.update(policy_spans_validated=policy_validation["validated"],
                      policy_span_validation=policy_validation)
        if not policy_validation["validated"]:
            record["elapsed_seconds"] = time.perf_counter() - started
            return record
        record.update(
            **schemes(report),
            coverage=report.coverage.model_dump(),
            api_evidence=[
                item.model_dump(mode="json") for item in report.evidence if item.api_call
            ],
            evidence_locators=[
                item.model_dump(mode="json",
                                include={"id", "kind", "source", "locator", "api_call"})
                for item in report.evidence
            ],
            features_sha256=digest(read_safe(features)),
            stored_job_sha256=digest(read_safe(store_dir / (output["job_id"] + ".json"))),
            report_sha256=digest(report.model_dump_json().encode()),
            behavior_limitations=report.coverage.behavior_limitations,
            apk_sha256=report.sample.apk_sha256,
        )
    record["elapsed_seconds"] = time.perf_counter() - started
    return record


def api_locators_match(api, scenario, label, apk_hash, reference):
    """Independent frozen mapping/location check, for either shared or referenced APIs."""
    rules = taxonomy()
    calls = expected_calls(reference, scenario, label, apk_hash)
    if calls is None or len(api) != len(calls):
        return False
    if sorted(item["locator"] for item in api) != sorted(locator(apk_hash, call) for call in calls):
        return False
    return all(
        item["api_call"]["target_descriptor"] == label["target_descriptor"]
        and item["api_call"]["ruleset_version"] == rules["version"]
        and item["api_call"]["context"] == label.get("target_context", {"provider": "gps"})
        and any(
            rule["rule_id"] == item["api_call"]["rule_id"]
            and rule["data_type"] == label["data_type"]
            and rule["target_descriptor"] == item["api_call"]["target_descriptor"]
            and rule["context"] == item["api_call"]["context"]
            for rule in rules["api_mappings"]
        )
        and any(item["source"] == call["dex"]
                and item["locator"] == locator(apk_hash, call) for call in calls)
        for item in api
    )


def score(records, truth):
    reference = load_reference()
    rows = []
    summaries = {
        scheme: {
            "total": len(truth["scenarios"]),
            "status_agreement": 0,
            "failures": 0,
            "abstentions": 0,
            "predicted": 0,
        }
        for scheme in SCHEMES
    }
    by_id = {record["scenario_id"]: record for record in records}
    for scenario, label in truth["scenarios"].items():
        record = by_id.get(scenario)
        for scheme in SCHEMES:
            predictions = record.get("predictions") if record else None
            matching = (
                []
                if predictions is None
                else [
                    item
                    for item in predictions[scheme]
                    if item["data_type"] == label["data_type"]
                    and (scheme == "permission_keyword" or item["action"] == label["action"])
                ]
            )
            statuses = sorted({item["status"] for item in matching})
            actual = statuses[0] if len(statuses) == 1 else None
            success = bool(record and record["analysis"]["status"] == "SUCCEEDED")
            api = record.get("api_evidence", []) if record else []
            apk_hash = (record or {}).get("apk_sha256")
            located = api_locators_match(api, scenario, label, apk_hash, reference)
            locators = {item["id"]: item for item in (record or {}).get("evidence_locators", [])}
            refs = sorted({ref for item in matching for ref in item["evidence_ids"]})
            refs_exist = bool(matching and refs) and all(ref in locators for ref in refs)
            referenced_api = [locators[ref] for ref in refs if ref in locators
                              and locators[ref].get("api_call")]
            # No sensitive invoke is expected in capability-only cases (C01).
            # Verify that absence in the shared scan; it is not a scheme API locator success.
            scheme_located = (
                success and refs_exist and api_locators_match(
                    referenced_api, scenario, label, apk_hash, reference)
                if label["api_count"] else None
            )
            policy_validation = record.get("policy_span_validation", {}) if record else {}
            policy_valid = bool(success and policy_validation.get("validated")
                                and not policy_validation.get("errors"))
            agreement = success and actual == label["expected"]
            summary = summaries[scheme]
            summary["status_agreement"] += int(agreement)
            summary["failures"] += int(not success or actual is None)
            summary["predicted"] += int(success and actual is not None)
            summary["abstentions"] += int(actual == "INSUFFICIENT_EVIDENCE")
            rows.append(
                {
                    "scenario_id": scenario,
                    "scheme": scheme,
                    "expected": label["expected"],
                    "actual": actual,
                    "agreement": agreement,
                    "shared_scanner_api_evidence_verified": success and located,
                    "scheme_prediction_evidence_locator_validated": scheme_located,
                    "scheme_evidence_references_resolved": success and refs_exist,
                    "shared_policy_spans_validated": policy_valid,
                    "elapsed_seconds": record.get("elapsed_seconds") if record else None,
                    "scheme_elapsed_seconds": record.get("scheme_elapsed_seconds", {}).get(scheme)
                    if record
                    else None,
                    "coverage": record.get("coverage") if record else None,
                    "truth_files_absent": record.get("truth_files_absent", False)
                    if record
                    else False,
                    "material_sha256": record.get("material_sha256") if record else None,
                    "evidence_ids": refs,
                    "errors": ((record["analysis"].get("errors", []) if record
                                else [{"code": "MISSING_RECORD"}])
                               + policy_validation.get("errors", [])),
                    "analysis_status": record["analysis"]["status"] if record else "MISSING",
                    "features_sha256": record.get("features_sha256") if record else None,
                    "apk_sha256": record.get("apk_sha256") if record else None,
                    "report_sha256": record.get("report_sha256") if record else None,
                    "behavior_limitations": record.get("behavior_limitations") if record else None,
                    "stored_job_sha256": record.get("stored_job_sha256") if record else None,
                }
            )
    return rows, summaries


def diagnostics(rows):
    """Status classification, evidence location and coverage have separate denominators."""
    result = {}
    for scheme in SCHEMES:
        selected = [row for row in rows if row["scheme"] == scheme]
        confusion = {}
        for row in selected:
            key = row["expected"] + " -> " + (row["actual"] or "NO_PREDICTION")
            confusion[key] = confusion.get(key, 0) + 1
        result[scheme] = {
            "total": len(selected),
            "confusion_counts": confusion,
            "shared_scanner_api_evidence_verified": sum(
                row["shared_scanner_api_evidence_verified"] for row in selected),
            "scheme_prediction_evidence_locator_validated": sum(
                row["scheme_prediction_evidence_locator_validated"] is True for row in selected),
            "scheme_api_locator_applicable": sum(
                row["scheme_prediction_evidence_locator_validated"] is not None
                for row in selected),
            "scheme_api_locator_not_applicable": sum(
                row["scheme_prediction_evidence_locator_validated"] is None for row in selected),
            "shared_policy_spans_validated": sum(
                row["shared_policy_spans_validated"] for row in selected),
            "coverage_complete": sum((row["coverage"] or {}).get("status") == "COMPLETE"
                                     for row in selected),
            "coverage_partial": sum((row["coverage"] or {}).get("status") == "PARTIAL"
                                    for row in selected),
            "coverage_unobserved": sum(row["coverage"] is None for row in selected),
            "execution_failures": sum(row["analysis_status"] != "SUCCEEDED" for row in selected),
            "missing_target_predictions": sum(row["analysis_status"] == "SUCCEEDED"
                                              and row["actual"] is None for row in selected),
            "truncated_outputs": sum(any("truncated" in text.lower()
                                         for text in (row["behavior_limitations"] or []))
                                     for row in selected),
            "mismatches_or_failures": [row["scenario_id"] for row in selected
                                        if not row["agreement"]],
            "precision_recall_f1": None,
            "precision_recall_f1_reason": "N/A: no binary runtime collection or legality target",
            "cpu_peak_memory": None,
            "human_preparation_seconds": None,
        }
    return result


def comparison_markdown(result):
    lines = ["# Controlled comparison", "",
             f"Suite: {result['suite']}; truth SHA256: `{result['truth_sha256']}`.", "",
             "One target per source scenario; failures and abstentions remain in the denominator.",
             "Shared scanner evidence, scheme-referenced API locators and status agreement "
             "are separate. Scheme API locators are N/A when the frozen target has no invoke.", "",
             "Exact byte callsites are checked against a separately versioned Android dexdump "
             "reference bound to the APK/DEX, caller, target and source-reviewed context.", "",
             "| Scheme | Total | Status agreement | Failures | Abstentions | "
             "Shared scanner | Scheme API locators (applicable) | API N/A | "
             "Shared policy spans | Complete DEX | Truncated |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for scheme, summary in result["summaries"].items():
        detail = result["diagnostics"][scheme]
        lines.append(f"| {scheme} | {summary['total']} | {summary['status_agreement']} | "
                     f"{summary['failures']} | {summary['abstentions']} | "
                     f"{detail['shared_scanner_api_evidence_verified']} | "
                     f"{detail['scheme_prediction_evidence_locator_validated']}/"
                     f"{detail['scheme_api_locator_applicable']} | "
                     f"{detail['scheme_api_locator_not_applicable']} | "
                     f"{detail['shared_policy_spans_validated']} | {detail['coverage_complete']} | "
                     f"{detail['truncated_outputs']} |")
    lines.extend(["", "| Scenario | Scheme | Expected | Actual | Agreement | Errors |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for row in result["rows"]:
        errors = ", ".join(error.get("code", "UNKNOWN") for error in row["errors"])
        lines.append(f"| {row['scenario_id']} | {row['scheme']} | {row['expected']} | "
                     f"{row['actual'] or 'NO_PREDICTION'} | {row['agreement']} | {errors} |")
    lines.extend(["", "P/R/F1: N/A (no binary runtime collection/legality target). "
                  "CPU, peak memory and human preparation cost: not measured.", "",
                  "The legacy failures column includes missing target predictions; diagnostics "
                  "separately count execution failures and successful runs with no target output.",
                  "",
                  "Complete DEX processing does not prove complete behavior coverage. "
                  "Prediction files retain non-target findings and coverage limitations.", ""])
    return "\n".join(lines)


def run_benchmark(artifacts, output, timeout, blocked_error=None, *, suite=SUITE):
    # Verify the freeze before execution; prediction subprocesses never receive truth paths/labels.
    truth_raw = read_safe(suite / "ground-truth.json")
    if digest(truth_raw) != (suite / "ground-truth.sha256").read_text().strip():
        raise ValueError("Ground truth changed after freeze")
    truth = json.loads(truth_raw)
    if truth["inputs_lock_sha256"] != digest(read_safe(suite / "inputs.lock.json")):
        raise ValueError("Frozen truth refers to different features")
    scenarios = scenario_ids(suite)
    if set(truth["scenarios"]) != set(scenarios):
        raise ValueError("Frozen scenario set does not match registered suite")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for scenario in ("C02", "C06", *(s for s in scenarios if s not in {"C02", "C06"})):
        started = time.perf_counter()
        if blocked_error is not None:
            # A broken freeze is an execution failure, not a model abstention.
            # Do not inspect the supplied APK or start prediction subprocesses.
            record = {
                "scenario_id": scenario,
                "analysis": {"status": "FAILED", "errors": [{"code": blocked_error}]},
                "predictions": None,
                "elapsed_seconds": None,
            }
        else:
            try:
                process = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "privacytrace.benchmark",
                        "predict",
                        "--features",
                        str(suite / "features" / (scenario + ".json")),
                        "--suite",
                        next(name for name, path in SUITES.items() if path == suite),
                        "--artifacts",
                        str(artifacts),
                        "--store-dir",
                        str(output / "jobs"),
                        "--timeout",
                        str(timeout),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=timeout + 60,
                )
                record = json.loads(process.stdout)
                if record["scenario_id"] != scenario:
                    raise ValueError("Prediction scenario identity mismatch")
            except (ValueError, OSError, subprocess.SubprocessError, KeyError):
                record = {
                    "scenario_id": scenario,
                    "analysis": {"status": "FAILED", "errors": [{"code": "PREDICTOR_FAILED"}]},
                    "predictions": None,
                    "elapsed_seconds": time.perf_counter() - started,
                }
        records.append(record)
        (output / (scenario + ".prediction.json")).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    rows, summaries = score(records, truth)
    implementation_files = sorted((ROOT / "apps/api/src/privacytrace").glob("*.py")) + [
        ROOT / "rules/taxonomy.v0.3.json",
        ROOT / SDK_SIGNATURE_FILES[ACTIVE_SDK_SIGNATURES_VERSION],
        ROOT / "scripts/build-controlled-apks.py",
        ROOT / "scripts/controlled/compile.py",
        ROOT / "scripts/controlled/location_reference.py",
        ROOT / "scripts/verify-controlled-locations.py",
        ROOT / "scripts/validate-spec30.py",
        ROOT / "scripts/verify-controlled-browser.cjs",
    ]
    location_reference = load_reference()
    result = {
        "implementation_hashes": {
            path.relative_to(ROOT).as_posix(): digest(read_safe(path))
            for path in implementation_files
        },
        "schema_version": 3,
        "api_location_reference": {
            "version": location_reference["reference_version"],
            "sha256": digest(read_safe(REFERENCE)),
            "path": REFERENCE.relative_to(ROOT).as_posix(),
            "limitations": location_reference["limitations"],
        },
        "suite": next(name for name, path in SUITES.items() if path == suite),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "truth_sha256": digest(truth_raw),
        "prediction_sha256": {
            scenario: digest(read_safe(output / (scenario + ".prediction.json")))
            for scenario in scenarios
        },
        "protocol": truth,
        "scheme_inputs": SCHEME_INPUTS,
        "rows": rows,
        "summaries": summaries,
        "diagnostics": diagnostics(rows),
        "limitations": [
            f"{len(scenarios)} authored source scenarios; no held-out generalization claim.",
            "Manual agent-assisted candidates; no automatic extraction accuracy claim.",
            "Static invoke never proves execution, collection, safety or illegality.",
            "Baseline status names are nominal experimental predictions, not user findings.",
        ],
    }
    (output / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "comparison.md").write_text(comparison_markdown(result), encoding="utf-8")
    passed = all(
        row["agreement"]
        and row["shared_scanner_api_evidence_verified"]
        and row["scheme_prediction_evidence_locator_validated"] is not False
        and row["scheme_evidence_references_resolved"]
        and row["shared_policy_spans_validated"]
        and row["truth_files_absent"]
        and row["coverage"]["status"] == "COMPLETE"
        for row in rows
        if row["scheme"] == "privacytrace"
    )
    return {
        "status": "COMPARED",
        "scenarios_passed": passed,
        "scenario_count": len(scenarios),
        # Deprecated alias retained identically for both suites until a breaking CLI version.
        "six_scenarios_passed": passed,
        "deprecated_fields": {"six_scenarios_passed": "Use scenarios_passed; see scenario_count"},
        "summaries": summaries,
        "comparison": str(output / "comparison.json"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    predictor = sub.add_parser("predict")
    predictor.add_argument("--features", type=Path, required=True)
    predictor.add_argument("--store-dir", type=Path, required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument(
        "--blocked-error",
        choices=("BUILD_A_FAILED", "BUILD_B_FAILED", "WORKER_BUILD_FAILED",
                 "BUILD_ARTIFACT_HASH_MISMATCH", "BUILD_ARTIFACT_RECEIPT_INVALID"),
        help="Record all scenarios as failed without scanning untrusted artifacts",
    )
    for child in (predictor, runner):
        child.add_argument("--suite", choices=SUITES, default="spec30")
        child.add_argument("--artifacts", type=Path, required=True)
        child.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        output = (
            predict(args.features, args.artifacts, args.store_dir, args.timeout, SUITES[args.suite])
            if args.mode == "predict"
            else run_benchmark(args.artifacts, args.output, args.timeout, args.blocked_error,
                               suite=SUITES[args.suite])
        )
    except (ValueError, OSError, KeyError, TypeError):
        output = {
            "scenario_id": getattr(args, "features", Path("invalid")).stem,
            "analysis": {"status": "FAILED", "errors": [{"code": "BENCHMARK_INPUT_INVALID"}]},
            "predictions": None,
        }
    print(json.dumps(output, ensure_ascii=True))
    return (
        0
        if (
            output.get("scenarios_passed")
            or output.get("analysis", {}).get("status") == "SUCCEEDED"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
