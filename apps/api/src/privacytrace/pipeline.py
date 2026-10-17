"""Single-sample CLI: validated offline policy and container-only APK scan."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .isolated_scan import ROOT, ScanError, scan_isolated, validate_input
from .job_store import JobStore
from .models import AnalysisJob, EvaluationInput
from .policy_intake import TEAM_REVIEW_GATE, load_policy
from .resources import taxonomy

def registered_package_set_matches(scanned, registered):
    """Validate complete immutable APK-set identity before any report is stored."""
    if not isinstance(registered, dict) or not isinstance(scanned, dict):
        return False
    observed = scanned.get("package_set")
    if not isinstance(observed, dict):
        return False
    if (
        scanned.get("package_name") != registered.get("package_name")
        or scanned.get("version_code") != registered.get("version_code")
        or scanned.get("version_name") != registered.get("version_name")
    ):
        return False
    expected = [registered.get("base"), *(registered.get("splits") or [])]
    actual = observed.get("files")
    if not isinstance(actual, list) or len(actual) != len(expected):
        return False

    def index(items):
        indexed = {}
        for entry in items:
            if not isinstance(entry, dict):
                return None
            name = entry.get("file_name")
            if not isinstance(name, str) or not name or name in indexed:
                return None
            indexed[name] = tuple(
                entry.get(key) for key in ("part", "split_name", "sha256", "size_bytes")
            )
        return indexed

    expected_files, actual_files = index(expected), index(actual)
    return (
        expected_files is not None
        and expected_files == actual_files
        and observed.get("total_size_bytes") == registered.get("total_size_bytes")
        and observed.get("split_count") == len(registered.get("splits") or [])
    )


def run(
    apk,
    policy,
    name,
    job_id=None,
    timeout=120,
    store_dir=None,
    product_scope=None,
    *,
    controlled=None,
    captured_policies=None,
    existing_job=None,
    on_stage=None,
    extra_tools=None,
    package_set=None,
    scanner=None,
    job_store=None,
    expected_apk_sha256=None,
):
    store = job_store if job_store is not None else JobStore(store_dir or ROOT / "data" / "jobs")
    job = existing_job or AnalysisJob(
        id=job_id or uuid4().hex,
        sample_id=name,
        input_mode="CONTROLLED_APK" if controlled else "APK",
        source_origin="CONTROLLED" if controlled else "REAL_SCAN",
        state="QUEUED",
        ruleset_version=taxonomy()["version"],
        created_at=datetime.now(timezone.utc),
        product_scope=product_scope,
    )
    if existing_job is None:
        store.create_if_absent(job)

    def cancelled():
        try:
            return store.get_job(job.id).state == "CANCELLED"
        except KeyError:
            if store.is_tombstoned(job.id):
                return True
            raise

    def transition(state):
        if cancelled():
            raise ScanError("CANCELLED", "Job cancelled")
        job.state = state
        if store.save_job(job).state == "CANCELLED":
            raise ScanError("CANCELLED", "Job cancelled")
        if on_stage:
            on_stage(state)

    try:
        transition("INTAKE")
        if not name.strip() or len(name) > 200 or not 1 <= timeout <= 180:
            raise ScanError("INVALID_ARGUMENT", "Name or timeout outside allowed range")
        if not (hasattr(apk, "is_dir") and apk.is_dir()):
            validate_input(apk)
        try:
            captures = captured_policies if captured_policies is not None else [load_policy(policy)]
            if not captures:
                raise ValueError("At least one captured policy is required")
            if controlled and captured_policies is not None:
                raise ValueError("Web captures cannot supply controlled facts")
            if controlled:
                from .controlled import adapt_policy

                captures = [adapt_policy(captures[0], controlled)]
        except (ValueError, OSError, KeyError, TypeError) as exc:
            raise ScanError("POLICY_INPUT_INVALID", "Policy capture failed validation") from exc
        transition("STATIC_ANALYSIS")
        if scanner is not None:
            scanned = scanner(apk, timeout=timeout, cancelled=cancelled)
        elif package_set is not None or (hasattr(apk, "is_dir") and apk.is_dir()):
            packages_dir = apk if apk.is_dir() else apk.parent / "packages"
            scanned = scan_isolated(packages_dir, timeout=timeout, cancelled=cancelled)
        else:
            scanned = scan_isolated(apk, timeout=timeout, cancelled=cancelled)
        if expected_apk_sha256 is not None and scanned["apk_sha256"] != expected_apk_sha256:
            raise ScanError("INPUT_DIGEST_MISMATCH", "Scanned APK differs from registered input")
        if package_set is not None and not registered_package_set_matches(scanned, package_set):
            raise ScanError("INPUT_DIGEST_MISMATCH", "Scanned APK set differs from registered input")
        if controlled and (
            scanned["apk_sha256"] != controlled["apk_sha256"]
            or scanned["package_name"] != controlled["package_name"]
            or scanned["version_code"] != 1
        ):
            raise ScanError("CONTROLLED_IDENTITY_MISMATCH", "Controlled build identity differs")
        transition("POLICY_PARSING")
        job.package_name = scanned["package_name"]
        job.version_code = scanned["version_code"]
        # An unconfirmed policy region must not become an asserted APK location.
        job.region = "CONTROLLED_TEST" if controlled and controlled["scope_known"] else None
        transition("EVALUATING")
        bundle = EvaluationInput.model_validate(
            {
                "job": job,
                "evidence": scanned["evidence"] + [e for c in captures for e in c["evidence"]],
                "behaviors": scanned["behaviors"],
                "policy_documents": [c["document"] for c in captures],
                "policy_claims": [claim for c in captures for claim in c["claims"]],
            }
        )
        transition("REPORTING")
        metadata = {
            key: scanned[key]
            for key in (
                "package_name",
                "version_name",
                "version_code",
                "apk_sha256",
                "permissions",
                "dex_entries",
            )
        }
        metadata["name"] = name
        if "package_set" in scanned and scanned["package_set"] is not None:
            metadata["package_set"] = scanned["package_set"]
        coverage = {**scanned["coverage"]}
        coverage["status"] = coverage.pop("completeness")
        tools = {
            "analysis_generated_at": datetime.now(timezone.utc).isoformat(),
            **scanned["tools"],
            "human_review_gate": TEAM_REVIEW_GATE,
            "scan_errors": json.dumps(scanned.get("errors", []), ensure_ascii=True),
        }
        if captured_policies is None:
            tools.update({
                "policy_capture_path": str(Path(policy).absolute()),
                "policy_initial_audit_sha256": captures[0]["files"]["audits"]["sha256"],
                "policy_initial_audit_path": str(
                    Path(policy).absolute().parent / captures[0]["files"]["audits"]["path"]
                ),
            })
        tools.update(extra_tools or {})
        if controlled:
            tools.update(
                {
                    "controlled_scenario": controlled["scenario_id"],
                    "controlled_features_sha256": controlled["features_sha256"],
                    "controlled_build_sha256": controlled["build_sha256"],
                    "policy_preparation": "AUTHORED_CONTROLLED_FIXTURE_AGENT_ASSISTED",
                }
            )
        if cancelled():
            raise ScanError("CANCELLED", "Job cancelled before report publication")
        job.state = "SUCCEEDED"
        bundle.job = job
        report = store.save(bundle, metadata, coverage, tools)
        return {
            "job_id": job.id,
            "status": "SUCCEEDED",
            "report_path": (
                None if getattr(store, "uses_postgres", False)
                else str(store.root / f"{job.id}.json")
            ),
            "coverage": report.coverage.status,
            "counts": {
                "evidence": len(report.evidence),
                "behaviors": len(report.behaviors),
                "claims": len(report.policy_claims),
                "issues": len(report.result.issues),
            },
            "human_review_gate": TEAM_REVIEW_GATE,
        }
    except (ScanError, ValueError, OSError, KeyError, TypeError) as exc:
        is_cancelled = cancelled() or (isinstance(exc, ScanError) and exc.code == "CANCELLED")
        job.state = "CANCELLED" if is_cancelled else "FAILED"
        code = exc.code if isinstance(exc, ScanError) else "PIPELINE_FAILED"
        # Validation exceptions may embed policy text. Do not echo private input.
        message = (
            "Job cancelled"
            if is_cancelled
            else "Pipeline failed; inspect input and tool prerequisites"
        )
        diagnostic = {"errors": [{"code": code, "message": message}]}
        if isinstance(exc, ScanError):
            diagnostic = exc.record()
            # Keep diagnostics and receipt locator, never echo private input.
            if diagnostic["primary_error"]:
                diagnostic["primary_error"]["message"] = message
        job.error = json.dumps({"code": code, "message": message, **diagnostic})
        store.save_job(job)
        return {
            "job_id": job.id,
            "status": job.state,
            **diagnostic,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--store-dir", type=Path)
    parser.add_argument("--product-scope")
    args = parser.parse_args()
    try:
        output = run(
            args.apk,
            args.policy,
            args.name,
            args.job_id,
            args.timeout,
            args.store_dir,
            args.product_scope,
        )
    except (ValueError, OSError, KeyError, TypeError):
        output = {
            "status": "FAILED",
            "errors": [
                {
                    "code": "PIPELINE_INPUT_INVALID",
                    "message": "Invalid job ID, duplicate job, or unsafe storage directory",
                }
            ],
        }
    print(json.dumps(output, ensure_ascii=True))
    return 0 if output["status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
