"""Validate the PrivacyTrace analysis run ledger (Issue #23).

One row per analysis run links a sample to its job and report hash, and records
the outcome and limitations honestly (partial or failed runs stay in the
ledger). A successful run must carry the SHA-256 of the report it points at;
a failed run that produced no report may leave the hash empty. Run against
``samples/real-world/runs.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path

REQUIRED = {
    "run_id",
    "sample_id",
    "job_id",
    "report_sha256",
    "outcome",
    "limitations",
    "scanned_at",
}
OUTCOMES = {"success", "partial", "failed"}
ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")
HASH_PATTERN = re.compile(r"[a-f0-9]{64}")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))


def parse_optional_int(value: str, field: str) -> int | None:
    token = value.strip()
    if not token:
        return None
    if not token.isdigit():
        raise ValueError(f"{field} must be a non-negative integer")
    return int(token)


def load_manifest(path: Path) -> list[dict]:
    """Read the sample manifest, validating identity and recorded hashes.

    The manifest is the second source of truth for sample identity, so it is
    checked as strictly as the ledger: the ``sample_id`` column must exist, and
    every value must be non-empty, match ``ID_PATTERN`` and be unique. A
    recorded ``apk_sha256`` must be a lowercase SHA-256; an empty value, or a
    missing column, means "not recorded" and stays acceptable. Two rows sharing
    a ``sample_id`` are always rejected, even with different hashes, because the
    dataset could not say which APK the sample refers to.

    The returned dicts keep the five keys and stripped values the builder always
    produced, so valid manifests yield the same dataset and ``dataset_sha256``.
    This is the single definition of the manifest contract;
    ``scripts/build-dataset.py`` delegates to it instead of parsing again.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "sample_id" not in (reader.fieldnames or []):
            raise ValueError("Sample manifest is missing required columns")
        rows = [
            {
                "sample_id": row.get("sample_id", "").strip(),
                "package_name": row.get("package_name", "").strip(),
                "version_name": row.get("version_name", "").strip(),
                "version_code": row.get("version_code", "").strip(),
                "apk_sha256": row.get("apk_sha256", "").strip(),
            }
            for row in reader
        ]
    seen_hashes: dict[str, str] = {}
    for row in rows:
        sample_id = row["sample_id"]
        if not sample_id or not ID_PATTERN.fullmatch(sample_id):
            raise ValueError(f"Invalid sample_id in manifest: {sample_id!r}")
        if sample_id in seen_hashes:
            raise ValueError(
                f"Manifest has a duplicate sample_id {sample_id!r} "
                f"(apk_sha256 {seen_hashes[sample_id]!r} and "
                f"{row['apk_sha256']!r})"
            )
        seen_hashes[sample_id] = row["apk_sha256"]
        apk_hash = row["apk_sha256"]
        if apk_hash and not HASH_PATTERN.fullmatch(apk_hash):
            raise ValueError(
                f"apk_sha256 must be lowercase SHA-256 for {sample_id}: {apk_hash!r}"
            )
    return rows


def _sample_ids(manifest: Path) -> set[str]:
    return {row["sample_id"] for row in load_manifest(manifest)}


def verify(ledger: Path, manifest: Path | None = None) -> list[dict]:
    with ledger.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not REQUIRED <= set(reader.fieldnames or []):
            raise ValueError("Run ledger is missing required columns")
        rows = list(reader)
    if not rows:
        raise ValueError("Run ledger has no rows")
    known_samples = _sample_ids(manifest) if manifest is not None else set()
    seen: set[str] = set()
    seen_jobs: dict[tuple[str, str], str] = {}
    results = []
    for row in rows:
        run_id = row["run_id"].strip()
        if not ID_PATTERN.fullmatch(run_id) or run_id in seen:
            raise ValueError(f"Invalid or duplicate run_id: {run_id}")
        seen.add(run_id)
        sample_id = row["sample_id"].strip()
        if not ID_PATTERN.fullmatch(sample_id):
            raise ValueError(f"Invalid sample_id for {run_id}")
        if manifest is not None and sample_id not in known_samples:
            raise ValueError(f"Unknown sample_id for {run_id}: {sample_id}")
        job_id = row["job_id"].strip()
        if not job_id:
            raise ValueError(f"Missing job_id for {run_id}")
        job_key = (sample_id, job_id)
        if job_key in seen_jobs:
            raise ValueError(
                f"Duplicate (sample_id, job_id) for {run_id}: "
                f"{job_key} already used by {seen_jobs[job_key]}"
            )
        seen_jobs[job_key] = run_id
        outcome = row["outcome"].strip()
        if outcome not in OUTCOMES:
            raise ValueError(f"Unknown outcome for {run_id}: {outcome}")
        report_hash = row["report_sha256"].strip()
        if report_hash:
            if not HASH_PATTERN.fullmatch(report_hash):
                raise ValueError(f"report_sha256 must be lowercase SHA-256: {run_id}")
        elif outcome == "success":
            raise ValueError(f"Successful run must carry report_sha256: {run_id}")
        scanned = parse_iso(row["scanned_at"])
        if scanned.tzinfo is None:
            raise ValueError(f"scanned_at must include timezone: {run_id}")
        counts = {
            key: parse_optional_int(row.get(key, ""), key)
            for key in ("evidence_count", "behavior_count", "claim_count")
        }
        limitations = [
            part.strip()
            for part in row["limitations"].split(";")
            if part.strip()
        ]
        results.append(
            {
                "run_id": run_id,
                "sample_id": sample_id,
                "job_id": row["job_id"].strip(),
                "report_sha256": report_hash,
                "outcome": outcome,
                "limitations": limitations,
                "scanned_at": scanned.isoformat(),
                **counts,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("samples/real-world/runs.csv"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("samples/real-world/manifest.csv"),
    )
    args = parser.parse_args()
    verified = verify(args.ledger, args.manifest)
    print(json.dumps({"verified": verified}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
