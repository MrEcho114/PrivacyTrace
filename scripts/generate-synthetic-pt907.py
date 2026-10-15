"""Generate a clearly labeled synthetic PT-907 rehearsal fixture.

The generated package mirrors the real-world field structure used by Issue #23:
sample manifest, run ledger, trace logs, policy source metadata, and user-study
answers. Every value is intentionally synthetic: app names, packages, URLs,
hashes, timestamps, and participant IDs are fictitious and deterministic.

This fixture exists only to rehearse and validate tooling. It MUST NOT be used
as Issue #23 acceptance evidence and MUST NOT be presented as real sample
analysis, a real privacy policy, or a real user study.
"""

from __future__ import annotations

import argparse
import csv
import json
from hashlib import sha256
from pathlib import Path

GENERATED_AT = "2026-10-13T00:00:00+00:00"
SYNTHETIC_COMMIT = "synthetic-pt907-v1"

SAMPLES = [
    {
        "sample_id": "syn-map-v1",
        "role": "PRIMARY",
        "app_name": "MapNav Synthetic",
        "package_name": "com.synth.mapnav",
        "version_name": "3.2.1",
        "version_code": "321",
        "official_source_url": "https://synthetic.example.invalid/releases/syn-map-v3.2.1.apk",
        "acquired_at": "2026-10-13T00:10:00+00:00",
        "policy_source_type": "OFFICIAL_POLICY_URL",
        "policy_version": "synthetic-1",
        "policy_captured_at": "2026-10-13T00:20:00+00:00",
        "reviewer": "SYNTHETIC",
        "status": "SYNTHETIC_READY",
    },
    {
        "sample_id": "syn-cam-v1",
        "role": "PRIMARY",
        "app_name": "CameraMemo Synthetic",
        "package_name": "com.synth.cameramemo",
        "version_name": "2.0.4",
        "version_code": "204",
        "official_source_url": "https://synthetic.example.invalid/releases/syn-cam-v2.0.4.apk",
        "acquired_at": "2026-10-13T00:30:00+00:00",
        "policy_source_type": "OFFICIAL_POLICY_URL",
        "policy_version": "synthetic-1",
        "policy_captured_at": "2026-10-13T00:40:00+00:00",
        "reviewer": "SYNTHETIC",
        "status": "SYNTHETIC_READY",
    },
    {
        "sample_id": "syn-contact-v1",
        "role": "PRIMARY",
        "app_name": "ContactsSync Synthetic",
        "package_name": "com.synth.contactssync",
        "version_name": "4.1.0",
        "version_code": "410",
        "official_source_url": "https://synthetic.example.invalid/releases/syn-contact-v4.1.0.apk",
        "acquired_at": "2026-10-13T00:50:00+00:00",
        "policy_source_type": "OFFICIAL_POLICY_URL",
        "policy_version": "synthetic-1",
        "policy_captured_at": "2026-10-13T01:00:00+00:00",
        "reviewer": "SYNTHETIC",
        "status": "SYNTHETIC_READY",
    },
    {
        "sample_id": "syn-wallet-v1",
        "role": "CHALLENGE",
        "app_name": "PackedWallet Synthetic",
        "package_name": "com.synth.packedwallet",
        "version_name": "5.0.1",
        "version_code": "501",
        "official_source_url": "https://synthetic.example.invalid/releases/syn-wallet-v5.0.1.apk",
        "acquired_at": "2026-10-13T01:10:00+00:00",
        "policy_source_type": "OFFICIAL_POLICY_URL",
        "policy_version": "synthetic-1",
        "policy_captured_at": "2026-10-13T01:20:00+00:00",
        "reviewer": "SYNTHETIC",
        "status": "SYNTHETIC_READY",
    },
]

RUNS = [
    {
        "run_id": "run-syn-map-1",
        "sample_id": "syn-map-v1",
        "job_id": "job-syn-map-1",
        "outcome": "success",
        "limitations": "",
        "scanned_at": "2026-10-13T01:30:00+00:00",
        "evidence_count": "3",
        "behavior_count": "2",
        "claim_count": "1",
        "notes": "SYNTHETIC_REHEARSAL",
    },
    {
        "run_id": "run-syn-cam-1",
        "sample_id": "syn-cam-v1",
        "job_id": "job-syn-cam-1",
        "outcome": "partial",
        "limitations": "加固;反编译不完整",
        "scanned_at": "2026-10-13T01:40:00+00:00",
        "evidence_count": "2",
        "behavior_count": "1",
        "claim_count": "2",
        "notes": "SYNTHETIC_REHEARSAL",
    },
    {
        "run_id": "run-syn-contact-1",
        "sample_id": "syn-contact-v1",
        "job_id": "job-syn-contact-1",
        "outcome": "success",
        "limitations": "SDK映射缺失",
        "scanned_at": "2026-10-13T01:50:00+00:00",
        "evidence_count": "4",
        "behavior_count": "3",
        "claim_count": "2",
        "notes": "SYNTHETIC_REHEARSAL",
    },
    {
        "run_id": "run-syn-wallet-1",
        "sample_id": "syn-wallet-v1",
        "job_id": "job-syn-wallet-1",
        "outcome": "failed",
        "limitations": "加固;反编译不完整;权限映射缺失",
        "scanned_at": "2026-10-13T02:00:00+00:00",
        "evidence_count": "1",
        "behavior_count": "0",
        "claim_count": "0",
        "notes": "SYNTHETIC_REHEARSAL",
    },
]

POLICIES = [
    {
        "sample_id": sample["sample_id"],
        "app_name": sample["app_name"],
        "policy_source_url": f"https://synthetic.example.invalid/privacy/{sample['sample_id']}",
        "policy_version": sample["policy_version"],
        "policy_captured_at": sample["policy_captured_at"],
    }
    for sample in SAMPLES
]

TRACE_STAGES = {
    "syn-map-v1": ("dex", "定位"),
    "syn-cam-v1": ("dex", "相机"),
    "syn-contact-v1": ("dex", "联系人"),
    "syn-wallet-v1": ("dex", "设备标识"),
}


def digest(value: str) -> str:
    """Return a deterministic lowercase SHA-256 for synthetic identifiers."""
    return sha256(value.encode("utf-8")).hexdigest()


def dataset_digest(rows: list[dict]) -> dict:
    """Attach deterministic hashes to synthetic metadata rows."""
    rows = [dict(row) for row in rows]
    for row in rows:
        ident = f"synthetic:{row['sample_id']}"
        row["apk_sha256"] = digest(ident + ":apk")
        row["policy_sha256"] = digest(ident + ":policy")
    return rows


def write_manifest(root: Path) -> Path:
    fieldnames = [
        "sample_id",
        "role",
        "app_name",
        "package_name",
        "version_name",
        "version_code",
        "official_source_url",
        "acquired_at",
        "apk_sha256",
        "policy_source_type",
        "policy_version",
        "policy_captured_at",
        "policy_sha256",
        "reviewer",
        "status",
    ]
    rows = sorted(SAMPLES, key=lambda row: row["sample_id"])
    path = root / "samples" / "synthetic" / "manifest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in dataset_digest(rows):
            writer.writerow(row)
    return path


def write_runs(root: Path) -> Path:
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
    rows = sorted(RUNS, key=lambda row: row["run_id"])
    path = root / "samples" / "synthetic" / "runs.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            report_hash = ""
            if row["outcome"] != "failed":
                report_hash = digest(f"synthetic:{row['run_id']}:report")
            writer.writerow(
                {
                    **row,
                    "report_sha256": report_hash,
                }
            )
    return path


def write_traces(root: Path) -> Path:
    trace_dir = root / "samples" / "synthetic" / "trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    for run in RUNS:
        sample_id = run["sample_id"]
        job_id = run["job_id"]
        stage, data_type = TRACE_STAGES[sample_id]
        outcome_status = run["outcome"]
        if outcome_status == "success":
            outcome_status = "ok"
        ts = run["scanned_at"]
        content = [
            {
                "ts": ts,
                "sample_id": sample_id,
                "job_id": job_id,
                "stage": "intake",
                "event": "start",
                "status": "ok",
                "detail": "synthetic rehearsal",
            },
            {
                "ts": ts,
                "sample_id": sample_id,
                "job_id": job_id,
                "stage": stage,
                "event": "evidence",
                "status": "ok",
                "evidence_ref": "ev-syn-1",
                "data_type": data_type,
                "location": f"com.synth.{sample_id}.Main",
                "duration_ms": 120,
            },
            {
                "ts": ts,
                "sample_id": sample_id,
                "job_id": job_id,
                "stage": "consistency",
                "event": "conclusion",
                "status": outcome_status,
                "detail": "synthetic conclusion; not real acceptance evidence",
            },
            {
                "ts": ts,
                "sample_id": sample_id,
                "job_id": job_id,
                "stage": "report",
                "event": "done",
                "status": outcome_status,
                "detail": "synthetic rehearsal complete",
            },
        ]
        path = trace_dir / f"{sample_id}.jsonl"
        path.write_text(
            "\n".join(json.dumps(line, ensure_ascii=False) for line in content)
            + "\n",
            encoding="utf-8",
        )
    return trace_dir


def write_policies(root: Path) -> Path:
    fieldnames = [
        "sample_id",
        "app_name",
        "policy_source_url",
        "policy_version",
        "policy_captured_at",
        "policy_sha256",
        "is_synthetic",
    ]
    path = root / "samples" / "synthetic" / "policies.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(POLICIES, key=lambda item: item["sample_id"]):
            writer.writerow(
                {
                    **row,
                    "policy_sha256": digest(f"synthetic:{row['sample_id']}:policy"),
                    "is_synthetic": "true",
                }
            )
    return path


def write_user_study(root: Path) -> Path:
    header = [
        "participant_id",
        "background",
        "condition",
        "material",
        "sample_id",
        "ground_truth_version",
        "question_id",
        "answer",
        "is_correct",
        "evidence_loc_seconds",
        "misconception",
        "start_time",
        "end_time",
        "subjective_understanding",
        "evidence_located",
        "git_commit",
        "notes",
    ]
    path = root / "evidence" / "synthetic" / "user-study.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    sample_cycle = [sample["sample_id"] for sample in SAMPLES]
    for participant_index in range(1, 7):
        participant_id = f"syn-user-{participant_index:02d}"
        condition = (
            "baseline_first" if participant_index <= 3 else "report_first"
        )
        for question_index in range(1, 13):
            material = (
                "baseline"
                if (condition == "baseline_first") == (question_index <= 6)
                else "privacyTrace"
            )
            is_correct = (participant_index + question_index) % 6 != 0
            misconception = ""
            if question_index == 3 and participant_index % 2 == 0:
                misconception = "权限=调用"
            elif question_index == 7 and participant_index % 3 == 0:
                misconception = "权限=实际收集;法律判定"
            start_minute = participant_index - 1
            end_minute = start_minute + 1
            rows.append(
                [
                    participant_id,
                    "ordinary-user",
                    condition,
                    material,
                    sample_cycle[(participant_index + question_index) % len(sample_cycle)],
                    "synthetic-0.1.0",
                    f"q{question_index:02d}",
                    "A",
                    "true" if is_correct else "false",
                    str(12 + participant_index * 2 + question_index % 8),
                    misconception,
                    f"2026-10-13T03:{start_minute:02d}:00+00:00",
                    f"2026-10-13T03:{end_minute:02d}:15+00:00",
                    "",
                    "true" if is_correct else "false",
                    SYNTHETIC_COMMIT,
                    "SYNTHETIC_REHEARSAL",
                ]
            )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def write_readme(root: Path) -> Path:
    content = """# PT-907 Synthetic Rehearsal Pack

Status: **SYNTHETIC ONLY**.

This directory and `evidence/synthetic/` contain deterministic rehearsal fixture
data for the Issue #23 tooling. App names, package names, URLs, hashes,
timestamps, policies, runs, traces, and participant answers are all fictional.

Use cases:
- Validate the PT-907 scripts end to end.
- Rehearse the real-data workflow before actual acquisition.
- Provide a clearly labeled `Refs #23` technical-side PR smoke fixture.

Must NOT do:
- Present this as real sample analysis.
- Present this as a real privacy policy or real user test.
- Use this to close Issue #23 or to claim its acceptance criteria were met.
- Run `scripts/verify-real-samples.py` against this directory; no APK files exist.

The generator is deterministic: `python scripts/generate-synthetic-pt907.py`.
"""
    path = root / "samples" / "synthetic" / "README.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_evidence_readme(root: Path) -> Path:
    content = """# PT-907 Synthetic User-Study Evidence

Status: **SYNTHETIC ONLY**.

The CSV files in this directory are generated rehearsal fixtures for
`scripts/metrics-user-study.py` and the dataset builder. Participant IDs are
anonymous synthetic identifiers; all answers, durations, misconceptions, and
timestamps are fictional.

`condition` records the reading order (`baseline_first` / `report_first`);
`material` records which material that answer was given against (`baseline` /
`privacyTrace`). Each synthetic participant answers the first six questions
against the first material and the last six against the second one. The fixture
is deliberately not tuned to produce a material effect: it exercises the
grouping, the effect logic is covered by unit tests.

This is not real evidence. It must not be cited, merged into `evidence/` as a
completed study, or used to close Issue #23. Regenerate with
`python scripts/generate-synthetic-pt907.py`.
"""
    path = root / "evidence" / "synthetic" / "README.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def generate(root: Path) -> dict:
    root = root.resolve()
    manifest = write_manifest(root)
    runs = write_runs(root)
    trace_dir = write_traces(root)
    policies = write_policies(root)
    user_study = write_user_study(root)
    readme = write_readme(root)
    evidence_readme = write_evidence_readme(root)
    return {
        "root": str(root),
        "manifest": str(manifest),
        "runs": str(runs),
        "trace_dir": str(trace_dir),
        "policies": str(policies),
        "user_study": str(user_study),
        "readme": str(readme),
        "evidence_readme": str(evidence_readme),
        "generated_at": GENERATED_AT,
        "synthetic_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root to write samples/synthetic and evidence/synthetic",
    )
    args = parser.parse_args()
    result = generate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()