#!/usr/bin/env python3
"""Deterministic review gates: the mechanical half of code review.

These gates encode review findings that are decidable from the source text, so a
reviewer never has to re-derive them and a regression fails the build instead of
slipping through. Judgement-dependent review stays human (or model) work; see
docs/agents/review-rubric.md.

Rules
  RG001  bulk filesystem move while holding the shared data-store transaction
  RG002  skip inside an end-to-end test
  RG003  absolute completion claim in a tracked document

Two ways to accept an exception:

* inline, on the offending line or the line above:
  ``# review-gates: allow RG001 - <reason>``
* centrally in ``scripts/review_gates_allowlist.json``, matched by path plus a
  substring of the line.

Both require a reason, and a stale allowlist entry is itself a failure, so the
exception file cannot silently rot into a blanket mute.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SUPPRESS_RE = re.compile(r"#\s*review-gates:\s*allow\s+(RG\d{3})\s*(?:-\s*(\S.*))?$")
BULK_IO_RE = re.compile(r"\bshutil\.(?:rmtree|copyfile|copy2|copytree|move)\s*\(")
TRANSACTION_RE = re.compile(r"^\s*with\b.*_transaction\(\)")
SKIP_RE = re.compile(r"\bpytest\.skip\w*\s*\(")
ABSOLUTE_CLAIM_RE = re.compile(
    r"\b(?:100\s*%\s*(?:of\s*)?(?:all\s+)?(?:required\s+)?(?:features|acceptance|coverage)\b"
    r"|full(?:y)?\s+implemented\s+and\s+validated"
    r"|all\s+required\s+features\s+implemented)",
    re.IGNORECASE,
)

SKIP_SCAN_PREFIX = "test_e2e_"
MIN_REASON_LEN = 8
IGNORED_DIRS = {".git", "node_modules", ".themasterplan", "__pycache__", ".venv"}


@dataclass
class Finding:
    rule: str
    severity: str
    path: str
    line: int
    message: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    suppressed: list[Finding] = field(default_factory=list)
    used_allowlist: set[int] = field(default_factory=set)
    scanned: int = 0

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]


def iter_files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and not (set(path.relative_to(root).parts[:-1]) & IGNORED_DIRS)
    )


def load_allowlist(root: Path, explicit: str | None) -> tuple[list[dict], str | None]:
    path = Path(explicit) if explicit else root / "scripts" / "review_gates_allowlist.json"
    if not path.is_file():
        return [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], f"allowlist is not valid JSON: {exc}"
    entries: list[dict] = []
    for rule, items in data.items():
        for item in items:
            missing = {"path", "match", "reason"} - item.keys()
            if missing:
                return [], f"allowlist entry for {rule} missing {sorted(missing)}"
            entries.append({"rule": rule, **item})
    return entries, None


def allowlist_hit(entries: list[dict], index_of: dict[int, int], rule: str, rel: str, text: str) -> bool:
    for position, entry in enumerate(entries):
        if entry["rule"] != rule or entry["path"] != rel:
            continue
        if entry["match"] in text:
            index_of[position] = index_of.get(position, 0) + 1
            return True
    return False


def record(
    report: Report,
    finding: Finding,
    lines: list[str],
    index: int,
    entries: list[dict],
    used: dict[int, int],
) -> None:
    reason_missing = False
    for probe in (index, index - 1):
        if probe < 0:
            continue
        match = SUPPRESS_RE.search(lines[probe])
        if not match or match.group(1) != finding.rule:
            continue
        reason = (match.group(2) or "").strip()
        if len(reason) >= MIN_REASON_LEN:
            report.suppressed.append(finding)
            return
        reason_missing = True
    if allowlist_hit(entries, used, finding.rule, finding.path, lines[index]):
        report.suppressed.append(finding)
        return
    if reason_missing:
        finding.message = f"{finding.message} (inline suppression needs a reason of {MIN_REASON_LEN}+ chars)"
    report.findings.append(finding)


def gate_transaction_io(root: Path, report: Report, entries: list[dict], used: dict[int, int]) -> None:
    for path in iter_files(root / "apps/api/src", {".py"}):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        rel = str(path.relative_to(root)).replace("\\", "/")
        block_indent: int | None = None
        for index, line in enumerate(lines):
            if TRANSACTION_RE.match(line):
                block_indent = len(line) - len(line.lstrip())
                continue
            if block_indent is None:
                continue
            stripped = line.strip()
            if stripped and (len(line) - len(line.lstrip())) <= block_indent:
                block_indent = None
                continue
            if BULK_IO_RE.search(line):
                record(
                    report,
                    Finding(
                        "RG001",
                        "error",
                        rel,
                        index + 1,
                        "bulk filesystem move while holding the shared data-store transaction; "
                        "every request on every draft queues behind it",
                    ),
                    lines,
                    index,
                    entries,
                    used,
                )


def gate_e2e_skips(root: Path, report: Report, entries: list[dict], used: dict[int, int]) -> None:
    for path in iter_files(root / "apps/api/tests", {".py"}):
        if not path.name.startswith(SKIP_SCAN_PREFIX):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        rel = str(path.relative_to(root)).replace("\\", "/")
        for index, line in enumerate(lines):
            if SKIP_RE.search(line):
                record(
                    report,
                    Finding(
                        "RG002",
                        "error",
                        rel,
                        index + 1,
                        "skip in an end-to-end test turns a regression into a green run; "
                        "use xfail(strict=True) with an issue reference instead",
                    ),
                    lines,
                    index,
                    entries,
                    used,
                )


def gate_absolute_claims(root: Path, report: Report, entries: list[dict], used: dict[int, int]) -> None:
    for path in iter_files(root, {".md"}):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        rel = str(path.relative_to(root)).replace("\\", "/")
        for index, line in enumerate(lines):
            if ABSOLUTE_CLAIM_RE.search(line):
                record(
                    report,
                    Finding(
                        "RG003",
                        "warn",
                        rel,
                        index + 1,
                        "absolute completion claim; repository rules require facts, claims and "
                        "inferences to stay separate",
                    ),
                    lines,
                    index,
                    entries,
                    used,
                )


GATES = (gate_transaction_io, gate_e2e_skips, gate_absolute_claims)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--allowlist", default=None, help="path to review_gates_allowlist.json")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "apps").is_dir():
        print(f"review gates: no apps/ under {root}; pass --root", file=sys.stderr)
        return 2

    entries, load_error = load_allowlist(root, args.allowlist)
    if load_error:
        print(f"review gates: {load_error}", file=sys.stderr)
        return 2

    report = Report()
    report.scanned = len(iter_files(root, {".py", ".md", ".json", ".ts"}))
    used: dict[int, int] = {}
    for gate in GATES:
        gate(root, report, entries, used)

    stale = [entry for position, entry in enumerate(entries) if position not in used]
    for entry in stale:
        report.findings.append(
            Finding(
                entry["rule"],
                "error",
                entry["path"],
                0,
                f"stale allowlist entry ({entry['match']!r} no longer occurs); "
                "remove it so the exception cannot outlive the debt",
            )
        )

    if args.json:
        print(
            json.dumps(
                {
                    "errors": [f.__dict__ for f in report.errors],
                    "warnings": [f.__dict__ for f in report.findings if f.severity == "warn"],
                    "suppressed": [f.__dict__ for f in report.suppressed],
                    "scanned": report.scanned,
                },
                indent=2,
            )
        )
    else:
        for finding in report.findings:
            print(f"{finding.severity}: {finding.path}:{finding.line}: [{finding.rule}] {finding.message}")
        for finding in report.suppressed:
            print(f"note: suppressed {finding.rule} at {finding.path}:{finding.line}")
        warnings = [f for f in report.findings if f.severity == "warn"]
        print(
            f"\nreview gates: {len(report.errors)} error(s), {len(warnings)} warning(s), "
            f"{len(report.suppressed)} suppressed, {report.scanned} file(s) scanned"
        )
        if not report.findings:
            print("review gates: clean")

    failing = len(report.errors) + (len(report.findings) - len(report.errors) if args.strict else 0)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
