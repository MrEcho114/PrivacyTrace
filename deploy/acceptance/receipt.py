"""Evidence receipt skeleton shared by every R2/R4/R5/R6 collector.

A receipt is intentionally boring and auditable:

* ``source_sha`` binds every check to one commit.
* ``environment`` records the machine the evidence came from.
* ``checks`` is the flat list of observations, each with a command, a wall-clock
  duration, a result digest and notes.
* ``untested`` is the top-level list of scopes nobody measured this round.

The aggregation helpers are the contract that keeps a SKIP from being read as a
PASS: :func:`summarize` counts the four statuses independently and
:func:`is_evidence_free` decides whether a receipt is allowed to claim results.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .redaction import RECEIPT_AUDIT_CATEGORIES, find_secret_markers, redact_value

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
NOT_TESTED = "NOT_TESTED"
STATUSES = (PASS, FAIL, SKIP, NOT_TESTED)
STATUS_RANK = {PASS: 0, FAIL: 1, NOT_TESTED: 2, SKIP: 3}

RECEIPT_VERSION = 1
DIGEST_LENGTH = 16


class RedactionLeak(RuntimeError):
    """A receipt still contained a credential after redaction; refuse to write it."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest_of(value: Any) -> str:
    """Stable short digest of any JSON-compatible observation."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def command_digest(command: Sequence[str] | str, *, started_at: str, duration_s: float) -> str:
    """Digest binding the exact command, its start time and its wall clock."""
    return digest_of(
        {
            "command": list(command) if not isinstance(command, str) else command,
            "started_at": started_at,
            "duration_s": round(duration_s, 3),
        }
    )


@dataclass
class Check:
    """One asserted observation."""

    name: str
    status: str
    command: str
    started_at: str
    duration_s: float
    result_digest: str
    notes: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    ticket: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"Unknown check status {self.status!r}")
        if not self.name:
            raise ValueError("A check needs a name")

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ticket": self.ticket,
            "status": self.status,
            "command": self.command,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
            "result_digest": self.result_digest,
            "notes": self.notes,
            "detail": self.detail,
        }


class CheckRecorder:
    """Times one check and mints its receipt entry.

    ``skip``/``not_tested`` exist so a collector can state exactly why it did
    not observe anything without inventing a result digest.
    """

    def __init__(self, name: str, command: str, *, ticket: str = "") -> None:
        self.name, self.command, self.ticket = name, command, ticket
        self.started_at = utc_now()
        self._started = time.monotonic()

    @property
    def duration_s(self) -> float:
        return time.monotonic() - self._started

    def _finish(self, status: str, notes: str, detail: Mapping[str, Any] | None = None) -> Check:
        duration = self.duration_s
        return Check(
            name=self.name,
            status=status,
            command=self.command,
            started_at=self.started_at,
            duration_s=duration,
            result_digest=digest_of(
                {
                    "command": self.command,
                    "status": status,
                    "notes": notes,
                    "observations": dict(detail or {}),
                }
            ),
            notes=notes,
            detail=dict(detail or {}),
            ticket=self.ticket,
        )

    def pass_(self, notes: str = "", **detail: Any) -> Check:
        return self._finish(PASS, notes, detail)

    def fail(self, notes: str = "", **detail: Any) -> Check:
        return self._finish(FAIL, notes, detail)

    def skip(self, reason: str, **detail: Any) -> Check:
        if not reason.strip():
            raise ValueError("A SKIP must state its reason")
        return self._finish(SKIP, reason, detail)

    def not_tested(self, reason: str, **detail: Any) -> Check:
        if not reason.strip():
            raise ValueError("A NOT_TESTED must state its scope")
        return self._finish(NOT_TESTED, reason, detail)

    def run(
        self,
        action: Callable[[], str],
        *,
        failures: Sequence[type[BaseException]] = (),
    ) -> Check:
        """Run ``action``; PASS when it returns, SKIP on ``failures``.

        ``action`` returns the success note. Any exception it raises becomes a
        FAIL unless listed in ``failures`` (an expected precondition miss).
        """
        try:
            notes = action()
        except tuple(failures) as exc:  # type: ignore[misc]
            return self.skip(f"{type(exc).__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 - collectors must never abort a run
            return self.fail(f"{type(exc).__name__}: {exc}")
        return self.pass_(notes)


def summarize(checks: Iterable[Check | Mapping[str, Any]]) -> dict[str, Any]:
    """Count every status separately; nothing is collapsed into PASS."""
    counts = {status: 0 for status in STATUSES}
    per_ticket: dict[str, dict[str, int]] = {}
    for check in checks:
        status = check["status"] if isinstance(check, Mapping) else check.status
        if status not in counts:
            raise ValueError(f"Unknown status {status!r} in summary")
        ticket = (check.get("ticket") if isinstance(check, Mapping) else check.ticket) or ""
        counts[status] += 1
        bucket = per_ticket.setdefault(ticket, {name.lower(): 0 for name in STATUSES})
        bucket[status.lower()] += 1
    verified = counts[PASS] + counts[FAIL]
    return {
        "total": sum(counts.values()),
        "pass": counts[PASS],
        "fail": counts[FAIL],
        "skip": counts[SKIP],
        "not_tested": counts[NOT_TESTED],
        # PASS rate is over checks that actually ran. It is None when none did,
        # so a fully skipped round cannot render as "0% pass" or "100% pass".
        "verified": verified,
        "pass_rate_of_verified": (round(counts[PASS] / verified, 4) if verified else None),
        "by_ticket": per_ticket,
        "conclusion": conclusion(counts),
    }


def conclusion(counts: Mapping[str, int]) -> str:
    """One of ``NO_REAL_EVIDENCE``/``FAILURES``/``PARTIAL``/``ALL_PASS``."""
    if counts.get(FAIL, 0):
        return "FAILURES"
    if counts.get(PASS, 0) == 0:
        return "NO_REAL_EVIDENCE"
    if counts.get(SKIP, 0) or counts.get(NOT_TESTED, 0):
        return "PARTIAL"
    return "ALL_PASS"


def is_evidence_free(summary: Mapping[str, Any]) -> bool:
    """True when this round observed nothing (every check skipped/untested)."""
    return summary.get("pass", 0) == 0 and summary.get("fail", 0) == 0


def read_source_sha(root: Path) -> str:
    if os.environ.get("PT_ACCEPTANCE_SOURCE_SHA"):
        return os.environ["PT_ACCEPTANCE_SOURCE_SHA"]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    return result.stdout.strip() or "UNKNOWN"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _cpu_model() -> str:
    text = _read_text(Path("/proc/cpuinfo"))
    for line in text.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor() or "UNKNOWN"


def _memory_bytes() -> int | None:
    text = _read_text(Path("/proc/meminfo"))
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            try:
                return int(line.split()[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


def _disk_for(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return {"path": str(path), "total_bytes": None, "free_bytes": None}
    return {
        "path": str(path),
        "total_bytes": usage.total,
        "free_bytes": usage.free,
        "filesystem": _filesystem_for(path),
    }


def _filesystem_for(path: Path) -> str:
    if os.name != "posix":
        return "UNKNOWN"
    try:
        result = subprocess.run(
            ["stat", "-f", "-c", "%T", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"
    return result.stdout.strip() or "UNKNOWN"


def version_of(command: Sequence[str]) -> str:
    """Version string for a tool, or ``UNAVAILABLE`` when it cannot be executed."""
    try:
        result = subprocess.run(
            list(command), capture_output=True, text=True, timeout=20, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return "UNAVAILABLE"
    first = result.stdout.strip().splitlines()
    return redact_value(first[0] if first else "")


def collect_environment(
    root: Path,
    *,
    tools: Mapping[str, str] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Machine facts recorded once per receipt.

    ``tools`` carries pre-collected version strings (Docker may live behind a
    WSL wrapper), so this function never assumes the CLI is on ``PATH``.
    """
    merged_tools = {
        "git": version_of(["git", "--version"]),
        "python": version_of(["python3", "--version"]),
    }
    merged_tools.update(tools or {})
    document: dict[str, Any] = {
        "os": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "kernel": _read_text(Path("/proc/sys/kernel/osrelease")) or platform.release(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
        "disk": _disk_for(root),
        "tools": merged_tools,
        "cwd": str(root),
        "wsl": bool(os.environ.get("WSL_DISTRO_NAME")),
    }
    document.update(dict(extra or {}))
    return document


@dataclass
class Receipt:
    """A full acceptance round for one or more tickets."""

    scope: str
    source_sha: str
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    environment: dict[str, Any] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)
    untested: list[str] = field(default_factory=list)
    notes: str = ""
    redaction_paths: list[str] = field(default_factory=list)

    def add(self, check: Check) -> Check:
        self.checks.append(check)
        return check

    def extend(self, checks: Iterable[Check]) -> None:
        for check in checks:
            self.add(check)

    def untested_scope(self, reason: str) -> None:
        if reason not in self.untested:
            self.untested.append(reason)

    def summary(self) -> dict[str, Any]:
        summary = summarize(self.checks)
        summary["untested_scopes"] = len(self.untested)
        summary["evidence_free"] = is_evidence_free(summary)
        return summary

    def to_dict(self) -> dict[str, Any]:
        summary = self.summary()
        document = {
            "receipt_version": RECEIPT_VERSION,
            "scope": self.scope,
            "source_sha": self.source_sha,
            "started_at": self.started_at,
            "finished_at": self.finished_at or utc_now(),
            "environment": self.environment,
            "summary": summary,
            "checks": [check.as_dict() for check in self.checks],
            "untested": list(self.untested),
            "notes": self.notes,
        }
        return redact_value(document, extra_paths=self.redaction_paths)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    def write(self, target: Path) -> Path:
        """Write the receipt; refuse to publish a receipt that still leaks."""
        text = self.to_json()
        markers = find_secret_markers(text, categories=RECEIPT_AUDIT_CATEGORIES)
        # The receipt intentionally records documented secret *paths*
        # (PRIVACYTRACE_DATABASE_URL_FILE=...). Only credential categories block.
        blocking = {
            key: value
            for key, value in markers.items()
            if key in {"capability-token", "private-key-block", "url-credentials"}
        }
        if blocking:
            raise RedactionLeak(
                "Receipt still matched credential markers: " + ", ".join(sorted(blocking))
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target


def render_summary(summary: Mapping[str, Any], *, scope: str, source_sha: str) -> str:
    """Human-readable block printed by every collector and by ``run.py``."""
    lines = [
        f"scope          : {scope}",
        f"source_sha     : {source_sha}",
        f"checks         : {summary['total']}",
        f"  PASS         : {summary['pass']}",
        f"  FAIL         : {summary['fail']}",
        f"  SKIP         : {summary['skip']}",
        f"  NOT_TESTED   : {summary['not_tested']}",
        f"verified(PASS+FAIL) : {summary['verified']}",
        f"untested scopes     : {summary.get('untested_scopes', 0)}",
        f"conclusion     : {summary['conclusion']}",
    ]
    if summary.get("evidence_free"):
        lines.append("NOTE           : NO_REAL_EVIDENCE - this round produced no PASS/FAIL")
    rate = summary.get("pass_rate_of_verified")
    if rate is not None:
        lines.append(f"pass/verified  : {rate:.1%}")
    for ticket, counts in sorted(summary.get("by_ticket", {}).items()):
        label = ticket or "unassigned"
        rendered = " ".join(f"{name}={counts[name.lower()]}" for name in STATUSES)
        lines.append(f"  [{label}] {rendered}")
    return "\n".join(lines)
