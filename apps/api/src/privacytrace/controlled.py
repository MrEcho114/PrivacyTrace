"""Explicit controlled-scenario CLI. Prediction never accepts ground-truth labels."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .controlled_inputs import input_hashes, load_controlled
from .job_store import JobStore
from .pipeline import run as run_pipeline
from .policy_intake import capture, digest, read_safe
from .resources import taxonomy


def predictions(report):
    """Independent baselines consume the same report inputs, never expected labels."""
    rules = taxonomy(report.job.ruleset_version)
    text = "\n".join(doc.artifact.text for doc in report.policy_documents)
    keyword_types = {m["data_type"] for m in rules["policy_phrase_mappings"] if m["phrase"] in text}
    permission_types = {
        m["data_type"]
        for m in rules["permission_mappings"]
        if m["permission"] in report.sample.permissions
    }
    permissions = [
        {
            "data_type": kind,
            "statuses": ["EXACT_MATCH" if kind in keyword_types else "NOT_DECLARED"],
        }
        for kind in sorted(permission_types)
    ]
    evidence = {e.id: e for e in report.evidence}
    api_rows, system_rows = [], []
    for behavior in report.behaviors:
        if behavior.action != "ACCESS":
            continue  # Capability rows remain in the full report, outside ACCESS scoring.
        calls = [evidence[ref] for ref in behavior.evidence_ids if evidence[ref].api_call]
        if not calls:
            continue
        # Report validation has verified the complete descriptor, rule ID and context.
        matched = any(
            c.data_type == behavior.data_type
            and c.action == "ACCESS"
            and c.polarity == "AFFIRMATIVE"
            and c.subject == "HOST_APP"
            and not c.condition
            and not c.ambiguity_flags
            for c in report.policy_claims
        )
        api_rows.append(
            {
                "data_type": behavior.data_type,
                "behavior_id": behavior.id,
                "statuses": ["EXACT_MATCH" if matched else "NOT_DECLARED"],
                "evidence_ids": [e.id for e in calls],
                "descriptors": [e.api_call.target_descriptor for e in calls],
            }
        )
        system_rows.append(
            {
                "data_type": behavior.data_type,
                "behavior_id": behavior.id,
                "statuses": sorted(
                    {i.status.value for i in report.result.issues if i.behavior_id == behavior.id}
                ),
                "evidence_ids": behavior.evidence_ids,
            }
        )
    return {
        "permission_keywords": {
            "uses": ["permissions", "policy artifact text", "versioned permission/phrase mappings"],
            "rows": permissions,
        },
        "api_flat": {
            "uses": ["same API evidence and complete descriptors", "same candidates"],
            "rows": api_rows,
        },
        "privacytrace": {
            "uses": ["same evidence/candidates", "applicability", "policy states"],
            "rows": system_rows,
        },
    }


def run_case(args):
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    context, apk, hashes = load_controlled(args.case_dir, args.build_receipt)
    out = args.output_dir.absolute()
    if any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (out, *out.parents)
    ):
        raise ValueError("Linked output is not allowed")
    # Every run gets a fresh directory; published predictions cannot be overwritten.
    out.mkdir(parents=True, exist_ok=False)
    receipt_bytes = read_safe(args.build_receipt)
    if digest(receipt_bytes) != context.build_receipt_sha256:
        raise ValueError("Build receipt changed during intake")
    (out / "build.json").write_bytes(receipt_bytes)
    case = context.case
    candidates = json.loads(read_safe(args.case_dir / "candidates.json"))
    if not isinstance(candidates, list):
        raise ValueError("Candidates must be a list")
    policy = capture(
        args.case_dir / "policy.txt",
        "https://example.invalid/privacytrace-controlled/" + case.case_id,
        str(case.version_code),
        out / "capture",
        candidates,
        case.package_name,
        case.version_code,
        case.product_scope,
        case.policy_regions,
        actor="Codex-assisted controlled authoring",
        reason="Source-owned test text, not a fetched real policy or human review",
    )
    if hashes != input_hashes(args.case_dir):
        raise ValueError("Inputs changed during capture")
    summary = run_pipeline(
        apk,
        policy,
        case.name,
        args.job_id,
        store_dir=args.store_dir,
        product_scope=case.product_scope,
        controlled=context,
    )
    result = {
        "schema_version": 1,
        "case_id": case.case_id,
        "job_id": args.job_id,
        "analysis_context": "CONTROLLED_EVALUATION",
        "status": summary["status"],
        "started_at": started_at,
        "input_hashes": hashes,
        "apk_sha256": context.apk_sha256,
        "source_hashes": context.source_hashes,
        "toolchain_sha256": context.toolchain_sha256,
        "build_receipt_sha256": context.build_receipt_sha256,
        "preparation": case.preparation,
        "counting_unit": "case_id + data_type + ACCESS; retain all report rows",
        "failure_policy": "Retain FAILED/PARTIAL/empty predictions; missing target is ABSTAIN",
        "schemes": {},
        "errors": summary.get("errors", []),
    }
    if summary["status"] == "SUCCEEDED":
        report = JobStore(args.store_dir).report(args.job_id)
        # Strip local private capture paths only from this exported controlled artifact.
        exported = report.model_dump(mode="json")
        exported["tools"] = {
            k: v
            for k, v in exported["tools"].items()
            if not k.endswith("_path") and k != "isolation_receipt"
        }
        report_bytes = json.dumps(exported, ensure_ascii=False, indent=2).encode("utf-8")
        (out / "report.json").write_bytes(report_bytes)
        result.update(
            report_sha256=digest(report_bytes),
            ruleset_version=report.job.ruleset_version,
            coverage=report.coverage.model_dump(mode="json"),
            schemes=predictions(report),
        )
    # Include capture, isolation, report export and all three schemes in the interval.
    result.update(
        generated_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=round(time.perf_counter() - started, 3),
    )
    (out / "predictions.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--case-dir", required=True, type=Path)
    run.add_argument("--build-receipt", required=True, type=Path)
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--store-dir", required=True, type=Path)
    run.add_argument("--job-id", required=True)
    args = parser.parse_args()
    try:
        result = run_case(args)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "case_id": result["case_id"],
                    "job_id": result["job_id"],
                    "errors": result["errors"],
                }
            )
        )
        return 0 if result["status"] == "SUCCEEDED" else 1
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({"status": "FAILED", "error": "CONTROLLED_INPUT_INVALID"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
