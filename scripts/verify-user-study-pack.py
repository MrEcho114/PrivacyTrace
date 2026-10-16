"""Verify the frozen PT-907 user-study preparation pack (Issue #62 items 3/4).

The pack freezes four machine-checkable artifacts -- the question bank, the
independent answer key, the balanced assignment table and the observation sheet
-- together with a freeze manifest that pins every covered file by SHA-256. This
script re-derives every one of those guarantees from the files on disk, so a
reviewer can recompute the result instead of trusting the generator.

Freeze-hash口径: the raw bytes are read, CRLF is normalized to LF, and the
SHA-256 of the normalized bytes is recorded; ``files[].bytes`` counts the
normalized bytes as well, so a checkout with different line endings still
verifies. The dataset digest is never trusted from the pack:
``scripts/build-dataset.py`` is re-run over ``samples/synthetic`` and its output
is written into a temporary directory, so a stale or hand-edited
``dataset_sha256`` cannot survive verification.

Pairing: template and synthetic files are two halves of each contract artifact.
Both are checked; the synthetic row wins when both define a question id.
Synthetic observation rows MUST participate in semantic checks, including
answer-key correctness, duplicates and assignment consistency. The
``SYNTHETIC_REHEARSAL`` marker identifies fictional data, not an exemption.
Only CSV comment lines starting with ``#`` are skipped.

Exit codes: 0 = every check passed, 1 = at least one issue, 2 = usage or
environment error. Output is deterministic: issues are sorted by
``(code, path, detail)``.
"""

from __future__ import annotations

import argparse
import csv
import glob as glob_module
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent

QUESTION_BANK_FILES = (
    "evidence/user-study-question-bank.template.csv",
    "evidence/synthetic/user-study-question-bank.csv",
)
ANSWER_KEY_FILES = (
    "evidence/user-study-answer-key.template.csv",
    "evidence/synthetic/user-study-answer-key.csv",
)
ASSIGNMENT_FILES = (
    "evidence/user-study-assignment.template.csv",
    "evidence/synthetic/user-study-assignment.csv",
)
OBSERVATIONS = "evidence/synthetic/user-study.csv"
MANIFEST = "evidence/synthetic/freeze-manifest.json"

QUESTION_HEADER = ["question_id", "dimension", "equivalent_set", "stem", "notes"]
ANSWER_HEADER = [
    "sample_id",
    "question_id",
    "equivalent_set",
    "scorable",
    "expected_answer",
    "evidence_location_baseline",
    "evidence_location_report",
    "scoring",
]
ASSIGNMENT_HEADER = [
    "participant_id",
    "condition",
    "material_order",
    "equivalent_set",
    "notes",
]
OBSERVATION_REQUIRED = [
    "participant_id",
    "condition",
    "material",
    "sample_id",
    "question_id",
    "answer",
    "is_correct",
]

CONDITION_ORDERS = {
    "baseline_first": "baseline;privacyTrace",
    "report_first": "privacyTrace;baseline",
}
MATERIALS = ("baseline", "privacyTrace")
SCORABLE_VALUES = ("true", "false")
EXPECTED_ANSWERS = ("A", "B")
IS_CORRECT_VALUES = ("", "true", "false")
STEM_FORBIDDEN = ("正确", "错误", "答案", "expected")
REHEARSAL_MARKER = "SYNTHETIC_REHEARSAL"

MANIFEST_KIND = "user-study-pack-freeze"
MANIFEST_SCHEMA_VERSION = "1.0.0"
HASH_NORMALIZATION = "crlf-to-lf"
DATASET_SCHEMA_VERSION = "0.3.0"
DATASET_DIR = "samples/synthetic"
MANIFEST_FIELDS = (
    ("kind", MANIFEST_KIND, "manifest-kind"),
    ("schema_version", MANIFEST_SCHEMA_VERSION, "manifest-schema-version"),
    ("synthetic_only", True, "manifest-synthetic-only"),
    ("hash_normalization", HASH_NORMALIZATION, "manifest-hash-normalization"),
    ("dataset_schema_version", DATASET_SCHEMA_VERSION, "manifest-dataset-schema-version"),
)
DEFAULT_EXCLUDED = [
    "evidence/synthetic/freeze-manifest.json",
    "evidence/synthetic/rehearsal-walkthrough.md",
]
DEFAULT_COVERED_GLOBS = [
    "evidence/user-study-*.template.*",
    # the 17-column records template: "user-study." carries no dash, so the glob above
    # never matches it and it needs its own literal pattern.
    "evidence/user-study.template.csv",
    "evidence/synthetic/*.csv",
    "evidence/synthetic/*.md",
    "evidence/synthetic/README.md",
    "evidence/trace.schema.md",
    "samples/synthetic/**",
    "scripts/build-dataset.py",
    "scripts/validate-trace.py",
    "scripts/verify-run-ledger.py",
    "scripts/metrics-user-study.py",
    "scripts/generate-synthetic-pt907.py",
    "scripts/verify-user-study-pack.py",
]
# Pack materials that must appear in files[] even when the frozen covered_globs (which
# verification honours) do not reach them: a stale glob list must not freeze silently.
REQUIRED_MANIFEST_PATHS = (
    "evidence/user-study.template.csv",
    *QUESTION_BANK_FILES,
    *ANSWER_KEY_FILES,
    *ASSIGNMENT_FILES,
    "evidence/user-study-comparison.template.md",
    "evidence/user-study-consent.template.md",
    "evidence/user-study-facilitator-script.template.md",
    "evidence/user-study-records-policy.template.md",
    "evidence/user-study-rehearsal-checklist.template.md",
    "evidence/trace.schema.md",
    "evidence/synthetic/README.md",
    OBSERVATIONS,
    "samples/synthetic/README.md",
    "samples/synthetic/manifest.csv",
    "samples/synthetic/policies.csv",
    "samples/synthetic/runs.csv",
    "scripts/build-dataset.py",
    "scripts/validate-trace.py",
    "scripts/verify-run-ledger.py",
    "scripts/metrics-user-study.py",
    "scripts/generate-synthetic-pt907.py",
    "scripts/verify-user-study-pack.py",
)


def required_manifest_paths(root: Path) -> list[str]:
    """Mandatory contracts plus every existing synthetic trace used by the builder."""
    trace_dir = root / DATASET_DIR / "trace"
    trace_files = (
        [path.relative_to(root).as_posix() for path in trace_dir.glob("*.jsonl")]
        if trace_dir.is_dir()
        else []
    )
    return sorted(set(REQUIRED_MANIFEST_PATHS).union(trace_files))
HEX_DIGITS = "0123456789abcdef"


class UsageError(Exception):
    """Raised for usage or environment errors (CLI exit code 2)."""


class Issue(NamedTuple):
    """One deterministic verification finding; sorts by (code, path, detail)."""

    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


def normalize_path(value: str) -> str:
    """Normalize a pack path to forward slashes without a leading './'."""
    token = value.replace("\\", "/").strip()
    while token.startswith("./"):
        token = token[2:]
    return token


def normalized_bytes(data: bytes) -> bytes:
    """Freeze hash口径: CRLF is normalized to LF before hashing."""
    return data.replace(b"\r\n", b"\n")


def digest_file(path: Path) -> tuple[str, int]:
    """Return (sha256, byte count) of a file under the freeze hash口径."""
    data = normalized_bytes(path.read_bytes())
    return hashlib.sha256(data).hexdigest(), len(data)


def load_module(name: str, path: Path):
    """Load a sibling script as a module so its rules keep one definition."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_rows(path: Path) -> tuple[list[str] | None, list[list[str]]]:
    """Read a CSV, skipping '#' comment lines and blank lines."""
    text = path.read_text(encoding="utf-8")
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    reader = csv.reader(io.StringIO("\n".join(lines)))
    header = next(reader, None)
    if header is None:
        return None, []
    return list(header), [list(row) for row in reader]


def load_contract_table(
    root: Path, rel: str, header: list[str]
) -> tuple[list[dict[str, str]] | None, list[Issue]]:
    """Load a frozen pack CSV; None means missing, unreadable or wrong header."""
    path = root / rel
    if not path.is_file():
        return None, [Issue("file-missing", rel, "required pack file not found")]
    try:
        actual, rows = read_rows(path)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return None, [Issue("csv-unreadable", rel, f"cannot read CSV: {exc}")]
    if actual != header:
        got = ",".join(actual) if actual else "(no header)"
        return None, [
            Issue("header-mismatch", rel, f"expected header {','.join(header)}; got {got}")
        ]
    issues: list[Issue] = []
    records: list[dict[str, str]] = []
    for number, row in enumerate(rows, start=1):
        if len(row) != len(header):
            issues.append(
                Issue(
                    "row-width-mismatch",
                    rel,
                    f"row {number}: expected {len(header)} fields, got {len(row)}",
                )
            )
            continue
        records.append({name: value.strip() for name, value in zip(header, row)})
    return records, issues


def bank_index(records: Sequence[dict[str, str]]) -> dict[str, str]:
    """Map question_id -> equivalent_set; the later (synthetic) file wins."""
    return {
        record["question_id"]: record["equivalent_set"]
        for record in records
        if record["question_id"]
    }


def answer_key_index(
    records: Sequence[dict[str, str]],
) -> dict[tuple[str, str], dict[str, str]]:
    """Map (sample_id, question_id) -> answer-key row; the synthetic file wins."""
    return {
        (record["sample_id"], record["question_id"]): record for record in records
    }


def check_bank_rows(records: Sequence[dict[str, str]], rel: str) -> list[Issue]:
    """Contract 1: question ids, required fields and leak-free stems."""
    issues: list[Issue] = []
    seen: set[str] = set()
    for number, record in enumerate(records, start=1):
        question_id = record["question_id"]
        if not question_id:
            issues.append(Issue("question-id-empty", rel, f"row {number}: question_id is empty"))
        elif question_id in seen:
            issues.append(
                Issue(
                    "question-id-duplicate",
                    rel,
                    f"row {number}: question_id {question_id!r} is already used in this file",
                )
            )
        else:
            seen.add(question_id)
        for column in ("dimension", "equivalent_set", "stem"):
            if not record[column]:
                issues.append(
                    Issue("question-field-empty", rel, f"row {number}: {column} is empty")
                )
        leaked = [token for token in STEM_FORBIDDEN if token in record["stem"]]
        if leaked:
            issues.append(
                Issue(
                    "stem-leak",
                    rel,
                    f"row {number}: stem carries a leak word: {', '.join(leaked)}",
                )
            )
    return issues


def check_answer_key_rows(
    records: Sequence[dict[str, str]], rel: str, bank: dict[str, str]
) -> list[Issue]:
    """Contract 2: unique keys, bank agreement and scorable/expected coherence."""
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for number, record in enumerate(records, start=1):
        key = (record["sample_id"], record["question_id"])
        if not record["sample_id"] or not record["question_id"]:
            issues.append(
                Issue(
                    "answer-key-key-empty",
                    rel,
                    f"row {number}: sample_id and question_id must both be non-empty",
                )
            )
        elif key in seen:
            issues.append(
                Issue(
                    "answer-key-duplicate",
                    rel,
                    f"row {number}: (sample_id, question_id) {key[0]!r}/{key[1]!r} "
                    "is already used in this file",
                )
            )
        else:
            seen.add(key)
        if bank:
            if record["question_id"] not in bank:
                issues.append(
                    Issue(
                        "answer-key-unknown-question",
                        rel,
                        f"row {number}: question_id {record['question_id']!r} "
                        "is not in the question bank",
                    )
                )
            elif bank[record["question_id"]] != record["equivalent_set"]:
                issues.append(
                    Issue(
                        "answer-key-equivalent-set-mismatch",
                        rel,
                        f"row {number}: equivalent_set {record['equivalent_set']!r} "
                        f"disagrees with the question bank value "
                        f"{bank[record['question_id']]!r}",
                    )
                )
        scorable = record["scorable"]
        if scorable not in SCORABLE_VALUES:
            issues.append(
                Issue(
                    "answer-key-scorable-invalid",
                    rel,
                    f"row {number}: scorable must be true or false, got {scorable!r}",
                )
            )
            continue
        if scorable == "true":
            if record["expected_answer"] not in EXPECTED_ANSWERS:
                issues.append(
                    Issue(
                        "answer-key-expected-invalid",
                        rel,
                        f"row {number}: a scorable row needs expected_answer A or B, "
                        f"got {record['expected_answer']!r}",
                    )
                )
            for column in (
                "evidence_location_baseline",
                "evidence_location_report",
                "scoring",
            ):
                if not record[column]:
                    issues.append(
                        Issue(
                            "answer-key-field-empty",
                            rel,
                            f"row {number}: {column} is empty on a scorable row",
                        )
                    )
        else:
            if record["expected_answer"]:
                issues.append(
                    Issue(
                        "answer-key-expected-not-empty",
                        rel,
                        f"row {number}: an unscorable row must leave expected_answer "
                        f"empty, got {record['expected_answer']!r}",
                    )
                )
            if not record["scoring"]:
                issues.append(
                    Issue(
                        "answer-key-field-empty",
                        rel,
                        f"row {number}: scoring is empty on an unscorable row",
                    )
                )
    return issues


def check_assignment_rows(
    records: Sequence[dict[str, str]], rel: str, bank: dict[str, str]
) -> list[Issue]:
    """Contract 3: condition/order coherence, membership and balancing."""
    issues: list[Issue] = []
    seen: set[str] = set()
    conditions: Counter[str] = Counter()
    per_set: dict[str, Counter[str]] = defaultdict(Counter)
    for number, record in enumerate(records, start=1):
        participant_id = record["participant_id"]
        if not participant_id:
            issues.append(
                Issue("assignment-participant-empty", rel, f"row {number}: participant_id is empty")
            )
        elif participant_id in seen:
            issues.append(
                Issue(
                    "assignment-participant-duplicate",
                    rel,
                    f"row {number}: participant_id {participant_id!r} "
                    "is already used in this file",
                )
            )
        else:
            seen.add(participant_id)
        condition = record["condition"]
        if condition not in CONDITION_ORDERS:
            issues.append(
                Issue(
                    "assignment-condition-invalid",
                    rel,
                    f"row {number}: condition must be baseline_first or report_first, "
                    f"got {condition!r}",
                )
            )
        else:
            conditions[condition] += 1
            per_set[record["equivalent_set"]][condition] += 1
            expected_order = CONDITION_ORDERS[condition]
            if record["material_order"] != expected_order:
                issues.append(
                    Issue(
                        "assignment-order-mismatch",
                        rel,
                        f"row {number}: condition {condition} requires material_order "
                        f"{expected_order!r}, got {record['material_order']!r}",
                    )
                )
        if bank and record["equivalent_set"] not in set(bank.values()):
            issues.append(
                Issue(
                    "assignment-unknown-equivalent-set",
                    rel,
                    f"row {number}: equivalent_set {record['equivalent_set']!r} "
                    "is not in the question bank",
                )
            )
    if records:  # a header-only template skips the balance rule
        if abs(conditions["baseline_first"] - conditions["report_first"]) > 1:
            issues.append(
                Issue(
                    "assignment-unbalanced",
                    rel,
                    f"condition split {conditions['baseline_first']} baseline_first / "
                    f"{conditions['report_first']} report_first is not balanced within one",
                )
            )
        for equivalent_set in sorted(per_set):
            split = per_set[equivalent_set]
            if abs(split["baseline_first"] - split["report_first"]) > 1:
                issues.append(
                    Issue(
                        "assignment-unbalanced-set",
                        rel,
                        f"equivalent_set {equivalent_set!r} split "
                        f"{split['baseline_first']} baseline_first / "
                        f"{split['report_first']} report_first is not balanced within one",
                    )
                )
    return issues


def load_observations(
    root: Path, rel: str
) -> tuple[list[dict[str, str]] | None, int, list[Issue]]:
    """Load all observations, including synthetic ones, for semantic verification."""
    path = root / rel
    if not path.is_file():
        return None, 0, [Issue("file-missing", rel, "required observation file not found")]
    try:
        header, rows = read_rows(path)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return None, 0, [Issue("csv-unreadable", rel, f"cannot read CSV: {exc}")]
    if header is None:
        return None, 0, [Issue("header-mismatch", rel, "observation file has no header")]
    missing = sorted(set(OBSERVATION_REQUIRED) - set(header))
    if missing:
        return None, 0, [
            Issue("header-mismatch", rel, f"missing required columns: {', '.join(missing)}")
        ]
    issues: list[Issue] = []
    records: list[dict[str, str]] = []
    rehearsal_rows = 0
    for number, row in enumerate(rows, start=1):
        if len(row) != len(header):
            issues.append(
                Issue(
                    "row-width-mismatch",
                    rel,
                    f"row {number}: expected {len(header)} fields, got {len(row)}",
                )
            )
            continue
        record = {name: value.strip() for name, value in zip(header, row)}
        if REHEARSAL_MARKER in record.get("notes", ""):
            rehearsal_rows += 1
        records.append(record)
    return records, rehearsal_rows, issues


def check_observation_rows(
    records: Sequence[dict[str, str]],
    rel: str,
    key_index: dict[tuple[str, str], dict[str, str]] | None,
    assignment: list[dict[str, str]] | None,
) -> list[Issue]:
    """Contract 4: coverage, judged correctness, material order and participants."""
    issues: list[Issue] = []
    orders: dict[str, list[str]] = {}
    pairs: set[tuple[str, str]] = set()
    first_answers: dict[tuple[str, str, str, str], int] = {}
    for number, record in enumerate(records, start=1):
        participant_id = record["participant_id"]
        material = record["material"]
        answer_key = (
            participant_id,
            record["sample_id"],
            record["question_id"],
            material,
        )
        previous = first_answers.get(answer_key)
        if previous is not None:
            issues.append(
                Issue(
                    "observation-duplicate",
                    rel,
                    f"row {number}: duplicate answer for {answer_key!r} "
                    f"(first seen in row {previous})",
                )
            )
        else:
            first_answers[answer_key] = number
        if material not in MATERIALS:
            issues.append(
                Issue(
                    "observation-material-invalid",
                    rel,
                    f"row {number}: material must be baseline or privacyTrace, "
                    f"got {material!r}",
                )
            )
        order = orders.setdefault(participant_id, [])
        if material not in order:
            order.append(material)
        pairs.add((participant_id, record["condition"]))
        key = (record["sample_id"], record["question_id"])
        entry = None if key_index is None else key_index.get(key)
        if key_index is not None and entry is None:
            issues.append(
                Issue(
                    "observation-uncovered",
                    rel,
                    f"row {number}: (sample_id, question_id) {key[0]!r}/{key[1]!r} "
                    "has no answer-key row",
                )
            )
            continue
        if entry is None:
            continue
        is_correct = record["is_correct"]
        if is_correct not in IS_CORRECT_VALUES:
            issues.append(
                Issue(
                    "observation-is-correct-invalid",
                    rel,
                    f"row {number}: is_correct must be true, false or empty, "
                    f"got {is_correct!r}",
                )
            )
            continue
        if not is_correct:
            continue
        if entry["scorable"] != "true":
            issues.append(
                Issue(
                    "observation-not-scorable",
                    rel,
                    f"row {number}: is_correct is set but the question is not scorable",
                )
            )
            continue
        expected_correct = record["answer"] == entry["expected_answer"]
        if (is_correct == "true") != expected_correct:
            issues.append(
                Issue(
                    "observation-consistency",
                    rel,
                    f"row {number}: is_correct {is_correct} contradicts answer "
                    f"{record['answer']!r} against expected_answer "
                    f"{entry['expected_answer']!r}",
                )
            )
    if not records:
        return issues
    assignment_by_participant = {
        record["participant_id"]: record["material_order"] for record in (assignment or [])
    }
    for participant_id in sorted(orders):
        expected_order = assignment_by_participant.get(participant_id)
        observed_order = ";".join(orders[participant_id])
        if expected_order is not None and observed_order != expected_order:
            issues.append(
                Issue(
                    "observation-order-mismatch",
                    rel,
                    f"participant {participant_id!r}: observed material order "
                    f"{observed_order!r} != assignment {expected_order!r}",
                )
            )
    if assignment is not None:
        observed_pairs = sorted(pairs)
        assigned_pairs = sorted(
            {(record["participant_id"], record["condition"]) for record in assignment}
        )
        if observed_pairs != assigned_pairs:
            issues.append(
                Issue(
                    "observation-participant-mismatch",
                    rel,
                    f"observed (participant_id, condition) set {observed_pairs} "
                    f"!= assignment {assigned_pairs}",
                )
            )
    return issues


def enumerate_covered(
    root: Path, covered_globs: Sequence[str], excluded: Sequence[str]
) -> list[str]:
    """Expand covered_globs to unique repository-relative paths, minus excluded."""
    excluded_set = {normalize_path(item) for item in excluded}
    covered: set[str] = set()
    for pattern in covered_globs:
        for match in glob_module.glob(pattern, root_dir=root, recursive=True):
            rel = normalize_path(match)
            if rel in excluded_set or not (root / rel).is_file():
                continue
            covered.add(rel)
    return sorted(covered)


def build_manifest_files(
    root: Path, covered_globs: Sequence[str], excluded: Sequence[str]
) -> list[dict[str, object]]:
    """Build the files[] block: path, normalized sha256 and normalized bytes."""
    entries: list[dict[str, object]] = []
    for rel in enumerate_covered(root, covered_globs, excluded):
        digest, size = digest_file(root / rel)
        entries.append({"path": rel, "sha256": digest, "bytes": size})
    return entries


def dataset_builder_path(root: Path, script_dir: Path) -> Path:
    """Prefer the repository's builder; fall back to this script's sibling."""
    candidate = root / "scripts" / "build-dataset.py"
    return candidate if candidate.is_file() else script_dir / "build-dataset.py"


def rebuild_dataset_digest(root: Path, builder: Path) -> tuple[str | None, str | None]:
    """Rebuild the dataset in a temporary directory; return (sha, error)."""
    inputs = [
        root / DATASET_DIR / "manifest.csv",
        root / DATASET_DIR / "runs.csv",
        root / DATASET_DIR / "trace",
    ]
    missing = [path.relative_to(root).as_posix() for path in inputs if not path.exists()]
    if missing:
        return None, "dataset inputs missing: " + ", ".join(missing)
    try:
        module = load_module("pt907_pack_dataset_builder", builder)
        dataset = module.build(inputs[0], inputs[1], inputs[2])
        with tempfile.TemporaryDirectory(prefix="pt907-pack-") as tmp:
            snapshot = Path(tmp) / "dataset.json"
            snapshot.write_text(
                json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            rebuilt = json.loads(snapshot.read_text(encoding="utf-8"))
        return rebuilt["dataset_sha256"], None
    except Exception as exc:  # noqa: BLE001 - every rebuild failure is a reported issue
        return None, f"dataset rebuild failed: {type(exc).__name__}: {exc}"


def check_manifest(root: Path, builder: Path) -> list[Issue]:
    """Contract 5: manifest shape, covered file set, per-file hash and dataset."""
    rel = MANIFEST
    path = root / rel
    if not path.is_file():
        return [Issue("manifest-missing", rel, "freeze manifest not found")]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [Issue("manifest-invalid", rel, f"cannot parse freeze manifest: {exc}")]
    if not isinstance(manifest, dict):
        return [Issue("manifest-invalid", rel, "freeze manifest must be a JSON object")]
    issues: list[Issue] = []
    for field, value, code in MANIFEST_FIELDS:
        if manifest.get(field) != value:
            issues.append(
                Issue(code, rel, f"{field} must be {value!r}, got {manifest.get(field)!r}")
            )
    globs = manifest.get("covered_globs")
    if not isinstance(globs, list) or not all(isinstance(item, str) for item in globs):
        issues.append(
            Issue(
                "manifest-covered-globs",
                rel,
                "covered_globs must be a list of glob strings; "
                "falling back to the default set",
            )
        )
        globs = DEFAULT_COVERED_GLOBS
    excluded = manifest.get("excluded")
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        issues.append(
            Issue(
                "manifest-excluded",
                rel,
                "excluded must be a list of repository-relative paths; "
                "falling back to the default set",
            )
        )
        excluded = DEFAULT_EXCLUDED
    else:
        declared_excluded = {normalize_path(item) for item in excluded}
        for required in DEFAULT_EXCLUDED:
            if required not in declared_excluded:
                issues.append(
                    Issue("manifest-excluded", rel, f"excluded must keep {required!r}")
                )
    expected = enumerate_covered(root, globs, excluded)
    declared = manifest.get("files")
    if not isinstance(declared, list):
        issues.append(Issue("manifest-invalid", rel, "files must be a list of objects"))
        declared = []
    by_path: dict[str, dict] = {}
    for entry in declared:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            issues.append(
                Issue(
                    "manifest-invalid",
                    rel,
                    f"files[] entries need an object with a path: {entry!r}",
                )
            )
            continue
        by_path[normalize_path(entry["path"])] = entry
    for rel_path in expected:
        entry = by_path.get(rel_path)
        if entry is None:
            issues.append(
                Issue(
                    "manifest-missing-file",
                    rel_path,
                    "matched by covered_globs but absent from files[]",
                )
            )
            continue
        digest, size = digest_file(root / rel_path)
        if entry.get("sha256") != digest:
            issues.append(
                Issue(
                    "manifest-hash-mismatch",
                    rel_path,
                    f"declared sha256 {entry.get('sha256')!r} but the normalized file "
                    f"hashes to {digest}",
                )
            )
        if entry.get("bytes") != size:
            issues.append(
                Issue(
                    "manifest-bytes-mismatch",
                    rel_path,
                    f"declared {entry.get('bytes')!r} bytes but the normalized file "
                    f"is {size} bytes",
                )
            )
    for rel_path in sorted(set(by_path) - set(expected)):
        issues.append(
            Issue(
                "manifest-extra-file",
                rel_path,
                "listed in files[] but not matched by covered_globs (or excluded)",
            )
        )
    excluded_set = {normalize_path(item) for item in excluded}
    for rel_path in required_manifest_paths(root):
        if rel_path in excluded_set:
            issues.append(
                Issue(
                    "manifest-required-excluded",
                    rel_path,
                    "mandatory pack material cannot be excluded from freeze coverage",
                )
            )
        if not (root / rel_path).is_file():
            issues.append(
                Issue("file-missing", rel_path, "mandatory pack material not found")
            )
        elif rel_path not in expected:
            issues.append(
                Issue(
                    "manifest-required-uncovered",
                    rel_path,
                    "mandatory pack material is not covered by covered_globs",
                )
            )
    declared_dataset = manifest.get("dataset_sha256")
    dataset_sha, error = rebuild_dataset_digest(root, builder)
    if error is not None:
        issues.append(Issue("manifest-dataset-rebuild", rel, error))
    if (
        not isinstance(declared_dataset, str)
        or len(declared_dataset) != 64
        or any(char not in HEX_DIGITS for char in declared_dataset)
    ):
        issues.append(
            Issue(
                "manifest-dataset-sha",
                rel,
                f"dataset_sha256 must be 64 lowercase hex characters, "
                f"got {declared_dataset!r}",
            )
        )
    elif dataset_sha is not None and dataset_sha != declared_dataset:
        issues.append(
            Issue(
                "manifest-dataset-sha",
                rel,
                f"declared dataset_sha256 {declared_dataset!r} but the rebuild yields "
                f"{dataset_sha}",
            )
        )
    return issues


def verify_root(root: Path) -> tuple[list[Issue], dict[str, int]]:
    """Run every contract check over one pack root; return (issues, summary)."""
    root = Path(root).resolve()
    summary: dict[str, int] = {}
    issues: list[Issue] = []

    bank_records: list[dict[str, str]] = []
    for rel in QUESTION_BANK_FILES:
        records, found = load_contract_table(root, rel, QUESTION_HEADER)
        issues += found
        if records is None:
            continue
        bank_records += records
        issues += check_bank_rows(records, rel)
    summary["question_bank_rows"] = len(bank_records)
    bank = bank_index(bank_records)

    key_records: list[dict[str, str]] = []
    key_loaded = False
    for rel in ANSWER_KEY_FILES:
        records, found = load_contract_table(root, rel, ANSWER_HEADER)
        issues += found
        if records is None:
            continue
        key_loaded = True
        key_records += records
        issues += check_answer_key_rows(records, rel, bank)
    summary["answer_key_rows"] = len(key_records)
    key_index = answer_key_index(key_records) if key_loaded else None

    assignment_records: dict[str, list[dict[str, str]]] = {}
    for rel in ASSIGNMENT_FILES:
        records, found = load_contract_table(root, rel, ASSIGNMENT_HEADER)
        issues += found
        if records is None:
            continue
        assignment_records[rel] = records
        issues += check_assignment_rows(records, rel, bank)
    summary["assignment_rows"] = sum(len(rows) for rows in assignment_records.values())

    observations, rehearsal_rows, found = load_observations(root, OBSERVATIONS)
    issues += found
    if observations is not None:
        rehearsal_assignment = assignment_records.get(ASSIGNMENT_FILES[1])
        issues += check_observation_rows(
            observations, OBSERVATIONS, key_index, rehearsal_assignment
        )
    summary["observation_rows"] = len(observations or [])
    summary["observation_rehearsal_rows"] = rehearsal_rows

    issues += check_manifest(root, dataset_builder_path(root, SCRIPT_DIR))
    return sorted({issue for issue in issues}), summary


def render_json(issues: Sequence[Issue]) -> str:
    """Render the machine-readable report."""
    payload = {"ok": not issues, "issues": [issue.as_dict() for issue in issues]}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_text(
    root: Path,
    issues: Sequence[Issue],
    summary: dict[str, int],
) -> str:
    """Render the deterministic human-readable report."""
    lines = [
        f"verify-user-study-pack: root={root.as_posix()}",
        (
            "rows: question-bank={question_bank_rows} answer-key={answer_key_rows} "
            "assignment={assignment_rows} observations={observation_rows} "
            "(rehearsal-included={observation_rehearsal_rows})"
        ).format(**summary),
        "rehearsal rows: included in semantic verification",
        f"issues: {len(issues)}",
    ]
    lines += [f"  [{issue.code}] {issue.path}: {issue.detail}" for issue in issues]
    lines.append("result: " + ("OK" if not issues else "FAIL"))
    return "\n".join(lines) + "\n"


def write_manifest(root: Path) -> dict:
    """Recompute covered_globs, files[] and dataset_sha256, keeping every other field."""
    root = Path(root).resolve()
    path = root / MANIFEST
    if not path.is_file():
        raise UsageError(
            f"{MANIFEST} is missing; refusing to create it "
            "(the rehearsal walkthrough step creates it)"
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot parse {MANIFEST}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise UsageError(f"{MANIFEST} must contain a JSON object")
    globs = manifest.get("covered_globs")
    if not isinstance(globs, list) or not all(isinstance(item, str) for item in globs):
        globs = list(DEFAULT_COVERED_GLOBS)
    else:
        globs = [normalize_path(item) for item in globs]
        globs += [item for item in DEFAULT_COVERED_GLOBS if item not in globs]
    excluded = manifest.get("excluded")
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        excluded = DEFAULT_EXCLUDED
    mandatory = set(required_manifest_paths(root))
    illegally_excluded = mandatory.intersection(
        {normalize_path(item) for item in excluded}
    )
    if illegally_excluded:
        raise UsageError(
            "cannot exclude mandatory freeze paths: "
            + ", ".join(sorted(illegally_excluded))
        )
    missing = sorted(item for item in mandatory if not (root / item).is_file())
    if missing:
        raise UsageError("mandatory freeze files are missing: " + ", ".join(missing))
    dataset_sha, error = rebuild_dataset_digest(root, dataset_builder_path(root, SCRIPT_DIR))
    if error is not None:
        raise UsageError(f"cannot rebuild the dataset digest: {error}")
    updated = dict(manifest)
    updated["covered_globs"] = globs
    updated["files"] = build_manifest_files(root, globs, excluded)
    updated["dataset_sha256"] = dataset_sha
    text = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return updated


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; see the module docstring for the exit-code contract."""
    parser = argparse.ArgumentParser(
        description="Verify the frozen PT-907 user-study preparation pack (Issue #62)."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root (default: the repository that contains this script)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help='print {"ok": ..., "issues": [...]} instead of the readable report',
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="recompute files[], sha256, bytes and dataset_sha256 in place",
    )
    args = parser.parse_args(argv)
    root = args.root if args.root is not None else SCRIPT_DIR.parent
    if not root.is_dir():
        print(f"error: --root is not a directory: {root}", file=sys.stderr)
        return 2
    root = root.resolve()
    if args.write_manifest:
        try:
            write_manifest(root)
        except UsageError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(f"freeze manifest rewritten: {MANIFEST}")
    issues, summary = verify_root(root)
    if args.as_json:
        print(render_json(issues))
    else:
        sys.stdout.write(render_text(root, issues, summary))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
