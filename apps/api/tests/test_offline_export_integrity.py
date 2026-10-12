"""Offline packages require six unique trusted reports and exactly 18 comparisons."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from privacytrace.resources import ROOT


@pytest.fixture
def exporter():
    spec = importlib.util.spec_from_file_location(
        "offline_export_integrity", ROOT / "scripts/export-offline.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(module):
    truth = "a" * 64
    build = "b" * 64
    expected = "INSUFFICIENT_EVIDENCE"
    reports = {}
    rows = []
    scenarios = {f"C0{i}": {"expected": expected} for i in range(1, 7)}
    for scenario in scenarios:
        job_id = "job-" + scenario
        report = {
            "job": {
                "id": job_id, "sample_id": scenario, "state": "SUCCEEDED",
                "input_mode": "CONTROLLED_APK", "source_origin": "CONTROLLED",
            },
            "sample": {"permissions": []},
            "evidence": [], "behaviors": [], "policy_documents": [], "policy_claims": [],
            "tools": {"controlled_scenario": scenario, "controlled_build_sha256": build},
        }
        reports[job_id] = report
        material = module._material_digest(report)
        for scheme in sorted(module.SCHEMES):
            rows.append({
                "scenario_id": scenario, "scheme": scheme, "expected": expected,
                "actual": expected, "agreement": True, "material_sha256": material,
            })
    comparison = {
        "truth_sha256": truth, "protocol": {"scenarios": scenarios}, "rows": rows,
    }
    return comparison, reports, truth, build


def test_full_controlled_replay_set_is_accepted(exporter):
    comparison, reports, truth, build = _fixture(exporter)
    assert exporter.validate_replay_set(comparison, reports, truth, build) is None
    # Bad baseline prediction is evidence to retain, never a completeness failure.
    comparison["rows"][0]["actual"] = "NOT_DECLARED"
    comparison["rows"][0]["agreement"] = False
    assert exporter.validate_replay_set(comparison, reports, truth, build) is None


@pytest.mark.parametrize("problem", [
    "missing-report", "duplicate-scenario", "wrong-sample", "wrong-origin",
    "wrong-build", "missing-row", "duplicate-row", "unknown-scheme",
    "wrong-material", "wrong-truth", "wrong-protocol",
])
def test_offline_export_rejects_partial_or_inconsistent_replay(exporter, problem):
    comparison, reports, truth, build = _fixture(exporter)
    if problem == "missing-report":
        del reports["job-C05"]
    elif problem == "duplicate-scenario":
        del reports["job-C03"]
        extra = json.loads(json.dumps(reports["job-C02"]))
        extra["job"]["id"] = "job-duplicate"
        reports["job-duplicate"] = extra
    elif problem == "wrong-sample":
        reports["job-C03"]["job"]["sample_id"] = "C04"
    elif problem == "wrong-origin":
        reports["job-C03"]["job"]["source_origin"] = "REAL_SCAN"
    elif problem == "wrong-build":
        reports["job-C03"]["tools"]["controlled_build_sha256"] = "c" * 64
    elif problem == "missing-row":
        comparison["rows"].pop()
    elif problem == "duplicate-row":
        comparison["rows"][-1] = dict(comparison["rows"][0])
    elif problem == "unknown-scheme":
        comparison["rows"][0]["scheme"] = "unknown"
    elif problem == "wrong-material":
        comparison["rows"][0]["material_sha256"] = "0" * 64
    elif problem == "wrong-truth":
        comparison["truth_sha256"] = "0" * 64
    elif problem == "wrong-protocol":
        del comparison["protocol"]["scenarios"]["C03"]
    with pytest.raises(ValueError):
        exporter.validate_replay_set(comparison, reports, truth, build)
