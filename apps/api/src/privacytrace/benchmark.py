"""Three schemes on identical scanned materials; scoring reads frozen labels afterwards."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .controlled import SUITE, analyze
from .isolated_scan import docker_prefix
from .job_store import JobStore
from .policy_intake import digest, read_safe
from .resources import ACTIVE_SDK_SIGNATURES_VERSION, ROOT, SDK_SIGNATURE_FILES, taxonomy

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
                ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-a", str(path)], text=True
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


def predict(features, artifacts, store_dir, timeout):
    started = time.perf_counter()
    output = analyze(features, artifacts, store_dir, timeout, "controlled-" + uuid4().hex)
    record = {
        "scenario_id": features.stem,
        "analysis": output,
        "elapsed_seconds": time.perf_counter() - started,
        "predictions": None,
    }
    if output["status"] == "SUCCEEDED":
        report = JobStore(store_dir).report(output["job_id"])
        record.update(
            **schemes(report),
            coverage=report.coverage.model_dump(),
            api_evidence=[
                item.model_dump(mode="json") for item in report.evidence if item.api_call
            ],
            policy_spans_validated=True,
            features_sha256=digest(read_safe(features)),
        )
    record["elapsed_seconds"] = time.perf_counter() - started
    return record


def score(records, truth):
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
            rules = taxonomy()
            expected_caller = (
                "Lorg/privacytrace/controlled/"
                + scenario.lower()
                + "/MainActivity;->readLocation(Landroid/location/LocationManager;)"
                "Landroid/location/Location;"
            )
            located = len(api) == label["api_count"] and all(
                item["api_call"]["target_descriptor"] == label["target_descriptor"]
                and item["api_call"]["context"] == {"provider": "gps"}
                and any(
                    rule["rule_id"] == item["api_call"]["rule_id"]
                    and rule["data_type"] == label["data_type"]
                    and rule["target_descriptor"] == item["api_call"]["target_descriptor"]
                    and rule["context"] == item["api_call"]["context"]
                    for rule in rules["api_mappings"]
                )
                and "caller=" + expected_caller in item["locator"]
                and "offset_bytes=4;" in item["locator"]
                and item["source"] == "classes.dex"
                for item in api
            )
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
                    "api_mapping_and_locator_checked": success and located,
                    "policy_spans_validated": record.get("policy_spans_validated", False)
                    if record
                    else False,
                    "elapsed_seconds": record.get("elapsed_seconds") if record else None,
                    "scheme_elapsed_seconds": record.get("scheme_elapsed_seconds", {}).get(scheme)
                    if record
                    else None,
                    "coverage": record.get("coverage") if record else None,
                    "truth_files_absent": record.get("truth_files_absent", False)
                    if record
                    else False,
                    "material_sha256": record.get("material_sha256") if record else None,
                    "evidence_ids": sorted(
                        {ref for item in matching for ref in item["evidence_ids"]}
                    ),
                    "errors": record["analysis"].get("errors", [])
                    if record
                    else [{"code": "MISSING_RECORD"}],
                }
            )
    return rows, summaries


def run_benchmark(artifacts, output, timeout):
    # Verify the freeze before execution; prediction subprocesses never receive truth paths/labels.
    truth_raw = read_safe(SUITE / "ground-truth.json")
    if digest(truth_raw) != (SUITE / "ground-truth.sha256").read_text().strip():
        raise ValueError("Ground truth changed after freeze")
    truth = json.loads(truth_raw)
    if truth["inputs_lock_sha256"] != digest(read_safe(SUITE / "inputs.lock.json")):
        raise ValueError("Frozen truth refers to different features")
    if set(truth["scenarios"]) != {f"C0{i}" for i in range(1, 7)}:
        raise ValueError("Six scenario minimum required")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for scenario in ("C02", "C06", "C01", "C03", "C04", "C05"):
        started = time.perf_counter()
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "privacytrace.benchmark",
                    "predict",
                    "--features",
                    str(SUITE / "features" / (scenario + ".json")),
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
    ]
    result = {
        "implementation_hashes": {
            path.relative_to(ROOT).as_posix(): digest(read_safe(path))
            for path in implementation_files
        },
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "truth_sha256": digest(truth_raw),
        "protocol": truth,
        "scheme_inputs": SCHEME_INPUTS,
        "rows": rows,
        "summaries": summaries,
        "limitations": [
            "Six authored fixtures; no held-out generalization claim.",
            "Manual agent-assisted candidates; no automatic extraction accuracy claim.",
            "Static invoke never proves execution, collection, safety or illegality.",
            "Baseline status names are nominal experimental predictions, not user findings.",
        ],
    }
    (output / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    passed = all(
        row["agreement"]
        and row["api_mapping_and_locator_checked"]
        and row["policy_spans_validated"]
        and row["truth_files_absent"]
        and row["coverage"]["status"] == "COMPLETE"
        for row in rows
        if row["scheme"] == "privacytrace"
    )
    return {
        "status": "COMPARED",
        "six_scenarios_passed": passed,
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
    for child in (predictor, runner):
        child.add_argument("--artifacts", type=Path, required=True)
        child.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        output = (
            predict(args.features, args.artifacts, args.store_dir, args.timeout)
            if args.mode == "predict"
            else run_benchmark(args.artifacts, args.output, args.timeout)
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
            output.get("six_scenarios_passed")
            or output.get("analysis", {}).get("status") == "SUCCEEDED"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
