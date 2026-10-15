"""Build a normalized, hashable dataset from the #23 run ledger and trace logs.

The dataset has four parts: ``samples`` (from the manifest), ``runs`` (from the
run ledger), ``evidence`` and ``conclusions`` (both normalized from trace
lines). Private material such as APK bytes, full policy text and decompiled
sources never enters the dataset; only location summaries do.

Trace input is validated against the contract in ``scripts/validate-trace.py``
(single definition, loaded from the sibling file) and closed over the ledger:
every line must belong to a run that exists in the ledger, every
``evidence_ref`` may only appear on an ``event=evidence`` line and may not
repeat inside one run, and no line is dropped silently. Each line is normalized
into ``evidence`` or ``conclusions``, or counted as a lifecycle event in
``trace_events``; the builder asserts that the counts add up to the number of
lines read, so an unhandled event fails the build instead of vanishing.

The ``dataset_sha256`` is computed over ``schema_version``, ``trace_events`` and
the four dimensions, so the same inputs always produce the same hash (the
``generated_at`` timestamp is deliberately excluded from the hash).
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

SCHEMA_VERSION = "0.2.0"
TRACE_CONTRACT = Path(__file__).with_name("validate-trace.py")
LIFECYCLE_EVENTS = {"start", "error", "done"}


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _trace_contract():
    """Load the sibling trace validator so trace rules have one definition."""
    spec = importlib.util.spec_from_file_location(
        "pt907_trace_contract", TRACE_CONTRACT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    """Read every JSONL trace file, validated, with per-line provenance."""
    contract = _trace_contract()
    traces = []
    for path in sorted(directory.glob("*.jsonl")):
        lines = contract.validate(contract.load_lines(path))
        for number, line in enumerate(lines, start=1):
            traces.append({"source": f"{path.name}#{number}", "line": line})
    return traces


def normalize_traces(traces: list[dict], known_samples: set[str], runs: list[dict]):
    """Normalize validated trace lines into evidence, conclusions and counts."""
    run_index = {(run["sample_id"], run["job_id"]) for run in runs}
    if len(run_index) != len(runs):
        raise ValueError("run ledger has duplicate (sample_id, job_id) rows")
    evidence: list[dict] = []
    conclusions: list[dict] = []
    seen_refs: set[tuple[str, str, str]] = set()
    lifecycle: Counter[str] = Counter()
    for entry in traces:
        source = entry["source"]
        line = entry["line"]
        sample_id = line["sample_id"]
        job_id = line["job_id"]
        if sample_id not in known_samples:
            raise ValueError(f"trace {source} references unknown sample: {sample_id!r}")
        if (sample_id, job_id) not in run_index:
            raise ValueError(
                f"trace {source} references a run missing from the ledger: "
                f"sample_id={sample_id!r} job_id={job_id!r}"
            )
        event = line["event"]
        reference = line.get("evidence_ref")
        if event == "evidence":
            key = (sample_id, job_id, reference)
            if key in seen_refs:
                raise ValueError(
                    f"trace {source} repeats evidence_ref {reference!r} "
                    f"inside run {job_id!r}"
                )
            seen_refs.add(key)
            evidence.append(
                {
                    "event": event,
                    "sample_id": sample_id,
                    "job_id": job_id,
                    "evidence_ref": reference,
                    "data_type": line.get("data_type", ""),
                    "location": line.get("location", ""),
                    "stage": line["stage"],
                }
            )
        elif event == "conclusion":
            conclusions.append(
                {
                    "event": event,
                    "sample_id": sample_id,
                    "job_id": job_id,
                    "status": line["status"],
                    "detail": line.get("detail", ""),
                }
            )
        elif event in LIFECYCLE_EVENTS:
            lifecycle[event] += 1
        else:
            raise ValueError(f"trace {source} has unhandled event {event!r}")
    evidence.sort(key=lambda e: (e["sample_id"], e["job_id"], e["evidence_ref"]))
    conclusions.sort(key=lambda c: (c["sample_id"], c["job_id"], c["status"]))
    trace_events = {
        "total": len(traces),
        "evidence": len(evidence),
        "conclusions": len(conclusions),
        "lifecycle": dict(sorted(lifecycle.items())),
    }
    accounted = len(evidence) + len(conclusions) + sum(lifecycle.values())
    if accounted != trace_events["total"]:
        raise ValueError(
            f"trace convergence failed: read {trace_events['total']} lines but "
            f"accounted for {accounted}"
        )
    return evidence, conclusions, trace_events


def build(manifest: Path | None, ledger: Path, trace_dir: Path) -> dict:
    if manifest is not None:
        samples = sorted(load_manifest(manifest), key=lambda s: s["sample_id"])
    else:
        samples = [
            {"sample_id": sample_id}
            for sample_id in sorted({r["sample_id"] for r in load_ledger(ledger)})
        ]
    runs = sorted(load_ledger(ledger), key=lambda r: r["run_id"])
    evidence, conclusions, trace_events = normalize_traces(
        load_traces(trace_dir), {sample["sample_id"] for sample in samples}, runs
    )
    content = {
        "schema_version": SCHEMA_VERSION,
        "trace_events": trace_events,
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
        "trace_events": trace_events,
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
