import csv
import importlib.util

import pytest

from privacytrace.resources import ROOT

spec = importlib.util.spec_from_file_location(
    "verify_run_ledger", ROOT / "scripts/verify-run-ledger.py"
)
ledger_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger_mod)


def write_manifest(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_id", "package_name"])
        writer.writerow(["app-1", "com.example.app"])


def write_ledger(path, row):
    fieldnames = [
        "run_id",
        "sample_id",
        "job_id",
        "report_sha256",
        "outcome",
        "limitations",
        "scanned_at",
        "evidence_count",
        "behavior_count",
        "claim_count",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)


def base_row():
    return {
        "run_id": "run-1",
        "sample_id": "app-1",
        "job_id": "job-1",
        "report_sha256": "a" * 64,
        "outcome": "partial",
        "limitations": "加固;反编译不完整",
        "scanned_at": "2026-10-10T01:00:00Z",
        "evidence_count": "3",
        "behavior_count": "",
        "claim_count": "",
        "notes": "",
    }


def test_verify_accepts_valid_row(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger, base_row())
    rows = ledger_mod.verify(ledger, manifest)
    assert rows[0]["run_id"] == "run-1"
    assert rows[0]["limitations"] == ["加固", "反编译不完整"]


def test_verify_rejects_duplicate_run_id(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    row = base_row()
    write_ledger(ledger, row)
    with ledger.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writerow({**row, "job_id": "job-2"})
    with pytest.raises(ValueError, match="duplicate run_id"):
        ledger_mod.verify(ledger, manifest)


def test_verify_rejects_unknown_outcome(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger, {**base_row(), "outcome": "maybe"})
    with pytest.raises(ValueError, match="Unknown outcome"):
        ledger_mod.verify(ledger, manifest)


def test_verify_rejects_bad_report_hash(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger, {**base_row(), "report_sha256": "not-a-hash"})
    with pytest.raises(ValueError, match="SHA-256"):
        ledger_mod.verify(ledger, manifest)


def test_verify_rejects_unknown_sample_id(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger, {**base_row(), "sample_id": "missing"})
    with pytest.raises(ValueError, match="Unknown sample_id"):
        ledger_mod.verify(ledger, manifest)


def test_verify_rejects_timestamp_without_timezone(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger, {**base_row(), "scanned_at": "2026-10-10T01:00:00"})
    with pytest.raises(ValueError, match="timezone"):
        ledger_mod.verify(ledger, manifest)


def test_verify_rejects_success_without_report_hash(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger, {**base_row(), "outcome": "success", "report_sha256": ""})
    with pytest.raises(ValueError, match="must carry report_sha256"):
        ledger_mod.verify(ledger, manifest)


def test_verify_allows_failed_run_without_report_hash(tmp_path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest)
    ledger = tmp_path / "runs.csv"
    write_ledger(ledger, {**base_row(), "outcome": "failed", "report_sha256": ""})
    rows = ledger_mod.verify(ledger, manifest)
    assert rows[0]["outcome"] == "failed"
    assert rows[0]["report_sha256"] == ""
