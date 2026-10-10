"""Build the checked-in browser-acceptance job fixtures.

The fixtures are derived from the synthetic demo bundle so a clean checkout can
reproduce the browser acceptance run without any machine-local `data/jobs`
directory. Every fixture is written as a `StoredJob` record, validated by the
same Pydantic models the API serves, and stamped with an explicit
`source_origin` so nothing has to be inferred from sample naming.

Run from the repository root:

    uv run --project apps/api python scripts/build_acceptance_fixtures.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from privacytrace.models import EvaluationInput, SourceOrigin
from privacytrace.resources import taxonomy
from privacytrace.runtime_models import ScanCoverage, StoredJob

FIXTURE_DIR = ROOT / "fixtures" / "acceptance-jobs"
CREATED_AT = datetime(2026, 10, 3, 12, 48, 35, 211974, tzinfo=timezone.utc)


def base_bundle() -> dict:
    return json.loads(
        (ROOT / "samples" / "demo" / "evaluation-input.json").read_text(encoding="utf-8")
    )


def controlled_input(job_id: str, sample_id: str) -> EvaluationInput:
    """Controlled contract facts: synthetic-only mappings are removed."""
    data = base_bundle()
    synthetic_rules = {r["rule_id"] for r in taxonomy()["api_mappings"] if r.get("synthetic_only")}
    removed = {
        e["id"] for e in data["evidence"] if e.get("api_call", {}).get("rule_id") in synthetic_rules
    }
    data["evidence"] = [e for e in data["evidence"] if e["id"] not in removed]
    data["behaviors"] = [b for b in data["behaviors"] if not removed.intersection(b["evidence_ids"])]
    data["job"] = {
        **data["job"],
        "id": job_id,
        "sample_id": sample_id,
        "input_mode": "APK",
        "source_origin": "CONTROLLED",
        "state": "SUCCEEDED",
        "created_at": CREATED_AT.isoformat().replace("+00:00", "Z"),
        "package_name": "org.privacytrace.fixture",
        "version_code": 1,
        "region": None,
        "product_scope": None,
        "error": None,
    }
    return EvaluationInput.model_validate(data)


def write_record(name: str, record: StoredJob) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / f"{name}.json"
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"[fixture] {path.relative_to(ROOT)}")


def main() -> None:
    # 1. Partial coverage with a failed DEX entry and bytecode-only tooling.
    partial = controlled_input("ui-controlled-partial", "CONTROLLED-PARTIAL")
    write_record(
        "ui-controlled-partial",
        StoredJob(
            job=partial.job,
            bundle=partial,
            sample={
                "name": "受控评测样本（部分 DEX 失败）",
                "package_name": "org.privacytrace.fixture",
                "version_name": "1",
                "version_code": 1,
                "apk_sha256": "b" * 64,
                "permissions": ["android.permission.ACCESS_FINE_LOCATION"],
                "dex_entries": ["classes.dex", "classes2.dex"],
            },
            coverage=ScanCoverage(
                status="PARTIAL",
                limitations=["classes2.dex bytecode evidence retained"],
                scanned_dex=["classes.dex"],
                failed_dex=["classes2.dex"],
            ),
            tools={"jadx": "UNAVAILABLE_BYTECODE_FALLBACK", "scanner": "CONTROLLED_FIXTURE"},
        ),
    )

    # 2. Hard failure carrying a structured ZIP_INVALID error.
    failed_bundle = controlled_input("ui-controlled-failed", "CONTROLLED-FAILED")
    failed_job = failed_bundle.job.model_copy(
        update={
            "state": "FAILED",
            "error": json.dumps(
                {"code": "ZIP_INVALID", "message": "Pipeline failed", "primary_error": "APK container is not a valid zip archive"}
            ),
        }
    )
    write_record("ui-controlled-failed", StoredJob(job=failed_job))

    # 3. A real timeout: the job stopped after exceeding its scan budget.
    timeout_bundle = controlled_input("ui-controlled-timeout", "CONTROLLED-TIMEOUT")
    timeout_job = timeout_bundle.job.model_copy(
        update={
            "state": "FAILED",
            "error": json.dumps(
                {
                    "code": "SCAN_TIMEOUT",
                    "message": "Static analysis exceeded the configured timeout budget",
                    "primary_error": "worker killed after 120s",
                }
            ),
        }
    )
    write_record("ui-controlled-timeout", StoredJob(job=timeout_job))

    # 4. Cancelled job.
    cancelled_bundle = controlled_input("ui-controlled-cancel", "CONTROLLED-CANCEL")
    cancelled_job = cancelled_bundle.job.model_copy(update={"state": "CANCELLED"})
    write_record("ui-controlled-cancel", StoredJob(job=cancelled_job))

    # 5. Cancellable job left running so the cancel path can be exercised.
    running_bundle = controlled_input("ui-running-cancel", "CONTROLLED-RUNNING")
    running_job = running_bundle.job.model_copy(update={"state": "STATIC_ANALYSIS"})
    write_record("ui-running-cancel", StoredJob(job=running_job))

    # 6. Offline replay of a completed real-APK scan (evidence chain audit target).
    #    Carries the Dalvik bytecode evidence shape the acceptance suite audits:
    #    a SCREEN_CAPTURE behavior backed by a bytecode-offset API evidence record.
    replay_bundle = controlled_input("gkd-s1-first", "gkd-s1-first")
    replay_data = replay_bundle.model_dump(mode="json")
    screenshot_evidence = {
        "id": "ev-dex-screenshot-api",
        "kind": "API",
        "status": "STATIC_POTENTIAL",
        "source": "bytecode/classes.dex",
        "locator": "dex=classes.dex;offset_bytes=0x1a2b",
        "excerpt": "invoke-static {}, Landroid/app/UiAutomation;->takeScreenshot()Landroid/graphics/Bitmap;",
        "api_call": {
            "rule_id": "android.screen.automation-screenshot",
            "target_descriptor": "Landroid/app/UiAutomation;->takeScreenshot()Landroid/graphics/Bitmap;",
            "ruleset_version": "0.3.0",
            "context": {},
        },
    }
    replay_data["evidence"].append(screenshot_evidence)
    replay_data["behaviors"].append(
        {"id": "behavior-screen-capture", "data_type": "SCREEN_CAPTURE", "action": "ACCESS", "evidence_ids": ["ev-dex-screenshot-api"]}
    )
    replay_bundle = EvaluationInput.model_validate(replay_data)
    # The data came from a real APK scan, so its immutable origin is REAL_SCAN.
    # That this fixture is served from persisted storage is a property of the
    # loading path, reported per response as Report.delivery_mode, not of the data.
    replay_job = replay_bundle.job.model_copy(update={"source_origin": SourceOrigin.REAL_SCAN})
    replay_bundle = replay_bundle.model_copy(update={"job": replay_job})
    write_record(
        "gkd-s1-first",
        StoredJob(
            job=replay_job,
            bundle=replay_bundle,
            sample={
                "name": "持久化回放样本（真实 APK 静态报告）",
                "package_name": "org.privacytrace.fixture",
                "version_name": "1",
                "version_code": 1,
                "apk_sha256": "edcc03be24bc54d44c04746b46e2e33244120638e2199450b4407195447466a6",
                "permissions": ["android.permission.ACCESS_FINE_LOCATION"],
                "dex_entries": ["classes.dex"],
            },
            coverage=ScanCoverage(
                status="COMPLETE",
                limitations=[],
                scanned_dex=["classes.dex"],
                failed_dex=[],
            ),
            tools={"scanner": "REAL_SCAN_FIXTURE", "jadx": "UNAVAILABLE_BYTECODE_FALLBACK"},
        ),
    )


if __name__ == "__main__":
    main()
