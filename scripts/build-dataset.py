"""Build a normalized, hashable dataset from the #23 run ledger and trace logs.

The dataset has four parts: ``samples`` (from the manifest), ``runs`` (from the
run ledger), ``evidence`` and ``conclusions`` (both normalized from trace
lines). Private material such as APK bytes, full policy text and decompiled
sources never enters the dataset; only location summaries do.

The ``dataset_sha256`` is computed over ``schema_version`` plus the four
dimensions, so the same inputs always produce the same hash (the ``generated_at``
timestamp is deliberately excluded from the hash).
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

SCHEMA_VERSION = "0.1.0"


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_manifest(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "sample_id": row["sample_id"].strip(),
                "package_name": row.get("package_name", "").strip(),
                "version_name": row.get("version_name", "").strip(),
                "version_code": row.get("version_code", "").strip(),
                "apk_sha256": row.get("apk_sha256", "").strip(),
            }
            for row in reader
        ]


def load_ledger(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "run_id": row["run_id"].strip(),
                "sample_id": row["sample_id"].strip(),
                "job_id": row["job_id"].strip(),
                "report_sha256": row.get("report_sha256", "").strip(),
                "outcome": row["outcome"].strip(),
                "limitations": [
                    part.strip()
                    for part in row.get("limitations", "").split(";")
                    if part.strip()
                ],
            }
            for row in reader
        ]


def load_traces(directory: Path) -> list[dict]:
    traces = []
    for path in sorted(directory.glob("*.jsonl")):
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.strip():
                traces.append(json.loads(raw))
    return traces


def build(manifest: Path | None, ledger: Path, trace_dir: Path) -> dict:
    if manifest is not None:
        samples = sorted(load_manifest(manifest), key=lambda s: s["sample_id"])
    else:
        samples = [
            {"sample_id": sample_id}
            for sample_id in sorted({r["sample_id"] for r in load_ledger(ledger)})
        ]
    runs = sorted(load_ledger(ledger), key=lambda r: r["run_id"])
    evidence: list[dict] = []
    conclusions: list[dict] = []
    for line in load_traces(trace_dir):
        reference = line.get("evidence_ref")
        if reference:
            evidence.append(
                {
                    "sample_id": line["sample_id"],
                    "job_id": line["job_id"],
                    "evidence_ref": reference,
                    "data_type": line.get("data_type", ""),
                    "location": line.get("location", ""),
                    "stage": line["stage"],
                }
            )
        if line.get("event") == "conclusion":
            conclusions.append(
                {
                    "sample_id": line["sample_id"],
                    "job_id": line["job_id"],
                    "status": line["status"],
                    "detail": line.get("detail", ""),
                }
            )
    evidence.sort(key=lambda e: (e["sample_id"], e["job_id"], e["evidence_ref"]))
    conclusions.sort(key=lambda c: (c["sample_id"], c["job_id"], c["status"]))
    content = {
        "schema_version": SCHEMA_VERSION,
        "samples": samples,
        "runs": runs,
        "evidence": evidence,
        "conclusions": conclusions,
    }
    digest = sha256(_canonical(content).encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": digest,
        "samples": samples,
        "runs": runs,
        "evidence": evidence,
        "conclusions": conclusions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    dataset = build(args.manifest, args.ledger, args.trace_dir)
    rendered = json.dumps(dataset, ensure_ascii=False, indent=2)
    if args.out is None:
        print(rendered)
    else:
        args.out.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
