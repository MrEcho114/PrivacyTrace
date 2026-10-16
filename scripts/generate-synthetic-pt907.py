"""Generate a clearly labeled synthetic PT-907 rehearsal fixture.

The generated package mirrors the real-world field structure used by Issue #23:
sample manifest, run ledger, trace logs, policy source metadata, and user-study
answers plus the question bank, the independent answer key, and the balanced
reading-order assignment. Every value is intentionally synthetic: app names,
packages, URLs, hashes, timestamps, and participant IDs are fictitious and
deterministic.

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

SAMPLE_IDS = [sample["sample_id"] for sample in SAMPLES]

SYNTHETIC_NOTE = "SYNTHETIC_REHEARSAL"

COMMENT_LINE = (
    "# SYNTHETIC_REHEARSAL：由 scripts/generate-synthetic-pt907.py 生成；"
    "非真实证据，不得用于 Issue #23 验收。"
)

# One equivalent set pairs the material-A question with its material-B twin, so
# the two readings of the same slot stay comparable (`user-study-comparison`
# section 4: "A、B 用不同但难度等价的 App/题目").
DIMENSION_SETS = [
    ("eq-01", "location", "定位"),
    ("eq-02", "contacts", "联系人"),
    ("eq-03", "camera", "相机"),
    ("eq-04", "other", "设备标识"),
    ("eq-05", "location", "定位"),
    ("eq-06", "contacts", "联系人"),
]

STEM_TEMPLATES = [
    "这个 App 会不会用到你的【{label}】？请说明依据。",
    "你认为这个 App 是否涉及【{label}】？请说明依据。",
]

# Synthetic ground truth: which data types each sample is taken to use.
SAMPLE_DIMENSIONS = {
    "syn-map-v1": {"location", "other"},
    "syn-cam-v1": {"camera", "location"},
    "syn-contact-v1": {"contacts", "other"},
    "syn-wallet-v1": {"other"},
}

SCORING_RULE = (
    "answer 与 expected_answer 相同记 true、不同记 false"
    "（A=该样本会用到该类别，B=不会用到该类别）"
)

ASSIGNMENT_SETS = ("eq-01", "eq-02", "eq-03")


def question_bank_rows() -> list[dict]:
    """Return the 12 rehearsal questions grouped into six A/B equivalent sets."""
    rows = []
    for index, (set_id, dimension, label) in enumerate(DIMENSION_SETS):
        for offset, template in enumerate(STEM_TEMPLATES):
            rows.append(
                {
                    "question_id": f"q{index + 1 + offset * 6:02d}",
                    "dimension": dimension,
                    "equivalent_set": set_id,
                    "stem": template.format(label=label),
                    "notes": SYNTHETIC_NOTE,
                }
            )
    return rows


QUESTION_SETS = {
    row["question_id"]: row["equivalent_set"] for row in question_bank_rows()
}
QUESTION_DIMENSIONS = {
    row["question_id"]: row["dimension"] for row in question_bank_rows()
}


def expected_answer(sample_id: str, question_id: str) -> str:
    """Synthetic ground truth for one cell: A (uses it) or B (does not)."""
    dimension = QUESTION_DIMENSIONS[question_id]
    return "A" if dimension in SAMPLE_DIMENSIONS[sample_id] else "B"


def modeled_slip(participant_index: int, question_index: int) -> bool:
    """Deterministic error model: 12 of the 72 observations are typed wrong.

    It decides only whether the synthetic participant typed the other letter;
    correctness is then derived by comparing the answer with expected_answer.
    """
    return (participant_index + question_index) % 6 == 0


def evidence_locations(sample_id: str, question_id: str) -> tuple[str, str]:
    """Deterministic synthetic pointers; never quoted as real policy text."""
    sample_index = SAMPLE_IDS.index(sample_id)
    question_index = int(question_id[1:])
    paragraph = (sample_index + question_index) % 5 + 1
    report_row = (sample_index * 3 + question_index) % 7 + 1
    return (
        f"SYNTHETIC: baseline §2 第{paragraph}段",
        f"SYNTHETIC: report §1 证据行 {report_row}",
    )


def assignment_rows() -> list[dict]:
    """Six synthetic participants: 3/3 per reading order, 1/1 inside each set."""
    rows = []
    for index in range(1, 7):
        condition = "baseline_first" if index <= 3 else "report_first"
        order = (
            "baseline;privacyTrace"
            if condition == "baseline_first"
            else "privacyTrace;baseline"
        )
        rows.append(
            {
                "participant_id": f"syn-user-{index:02d}",
                "condition": condition,
                "material_order": order,
                "equivalent_set": ASSIGNMENT_SETS[
                    (index - 1) % len(ASSIGNMENT_SETS)
                ],
                "notes": SYNTHETIC_NOTE,
            }
        )
    return rows


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
            question_id = f"q{question_index:02d}"
            material = (
                "baseline"
                if (condition == "baseline_first") == (question_index <= 6)
                else "privacyTrace"
            )
            sample_id = sample_cycle[
                (participant_index + question_index) % len(sample_cycle)
            ]
            # The observation is derived from the answer key: the expected answer
            # comes from the key, the modeled slip decides whether the synthetic
            # participant typed it, and is_correct is their comparison.
            expected = expected_answer(sample_id, question_id)
            answer = expected
            if modeled_slip(participant_index, question_index):
                answer = "B" if expected == "A" else "A"
            is_correct = answer == expected
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
                    sample_id,
                    "synthetic-0.1.0",
                    question_id,
                    answer,
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


def write_question_bank(root: Path) -> Path:
    fieldnames = ["question_id", "dimension", "equivalent_set", "stem", "notes"]
    path = root / "evidence" / "synthetic" / "user-study-question-bank.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(COMMENT_LINE + "\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(question_bank_rows())
    return path


def write_answer_key(root: Path) -> Path:
    fieldnames = [
        "sample_id",
        "question_id",
        "equivalent_set",
        "scorable",
        "expected_answer",
        "evidence_location_baseline",
        "evidence_location_report",
        "scoring",
    ]
    rows = []
    for question_id in sorted(QUESTION_SETS):
        for sample_id in sorted(SAMPLE_IDS):
            baseline, report = evidence_locations(sample_id, question_id)
            rows.append(
                {
                    "sample_id": sample_id,
                    "question_id": question_id,
                    "equivalent_set": QUESTION_SETS[question_id],
                    "scorable": "true",
                    "expected_answer": expected_answer(sample_id, question_id),
                    "evidence_location_baseline": baseline,
                    "evidence_location_report": report,
                    "scoring": SCORING_RULE,
                }
            )
    path = root / "evidence" / "synthetic" / "user-study-answer-key.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(COMMENT_LINE + "\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_assignment(root: Path) -> Path:
    fieldnames = [
        "participant_id",
        "condition",
        "material_order",
        "equivalent_set",
        "notes",
    ]
    path = root / "evidence" / "synthetic" / "user-study-assignment.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(COMMENT_LINE + "\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(assignment_rows())
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

Three of the files carry the independent reference the answers are graded
against: `user-study-question-bank.csv` (12 questions, six `equivalent_set`
pairs), `user-study-answer-key.csv` (one row per observed
`(sample_id, question_id)` with the synthetic `expected_answer` and the
synthetic evidence pointers in both materials) and `user-study-assignment.csv`
(six participants, balanced 1/1 inside each assigned set). `answer` and
`is_correct` in `user-study.csv` are derived from that key, so every row
satisfies `is_correct == (answer == expected_answer)`. The `#`-prefixed first
line of the three reference files marks them as synthetic and is not part of
the CSV header.

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
    question_bank = write_question_bank(root)
    answer_key = write_answer_key(root)
    assignment = write_assignment(root)
    readme = write_readme(root)
    evidence_readme = write_evidence_readme(root)
    return {
        "root": str(root),
        "manifest": str(manifest),
        "runs": str(runs),
        "trace_dir": str(trace_dir),
        "policies": str(policies),
        "user_study": str(user_study),
        "question_bank": str(question_bank),
        "answer_key": str(answer_key),
        "assignment": str(assignment),
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