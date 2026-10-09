"""Strict local file-layer verification for TheMasterplan."""

from __future__ import annotations

from pathlib import Path

from .apply import EXECUTOR_FILES
from .util import (
    TheMasterplanError,
    is_volatile_executor_artifact,
    read_json,
    safe_join,
    sha256_of_block,
    sha256_of_file,
)

CORE_PATHS = ("core/policy.md", "core/workflow.md")


def _check_hash(project_root: Path, relative: str, recorded: dict) -> list[str]:
    try:
        target = safe_join(project_root, relative)
    except TheMasterplanError as exc:
        return [f"unsafe path in state: {relative} ({exc})"]
    if not target.is_file():
        return [f"missing: {relative}"]
    if recorded.get("ownership") == "managed-block":
        current = sha256_of_block(target)
        if not current:
            return [f"managed block missing in: {relative}"]
    else:
        current = sha256_of_file(target)
    if current != recorded.get("installed_sha256"):
        return [f"hash mismatch: {relative}"]
    return []


def verify(project_root: Path) -> dict:
    issues: list[str] = []
    state_path = project_root / ".themasterplan/state.json"
    if not state_path.is_file():
        return {
            "ok": False,
            "status": "ABSENT",
            "issues": ["missing .themasterplan/state.json"],
        }
    try:
        state = read_json(state_path)
    except TheMasterplanError as exc:
        return {
            "ok": False,
            "status": "BROKEN",
            "issues": [str(exc)],
        }

    for relative in CORE_PATHS:
        if not safe_join(project_root, relative).is_file():
            issues.append(f"missing required: {relative}")

    managed = state.get("managed_files", {})
    if not isinstance(managed, dict):
        issues.append("state.json managed_files must be an object")
        managed = {}
    else:
        for relative, recorded in managed.items():
            if is_volatile_executor_artifact(relative):
                continue
            if not isinstance(recorded, dict):
                issues.append(f"malformed state entry: {relative}")
                continue
            issues.extend(_check_hash(project_root, relative, recorded))

    agents = project_root / "AGENTS.md"
    if agents.is_file():
        text = agents.read_text(encoding="utf-8", errors="replace")
        begin = text.count("<!-- THEMASTERPLAN:BEGIN MANAGED -->")
        end = text.count("<!-- THEMASTERPLAN:END MANAGED -->")
        if begin != 1 or end != 1:
            issues.append(
                "AGENTS.md managed block markers invalid "
                f"(begin={begin}, end={end})"
            )
    else:
        issues.append("missing AGENTS.md")

    selection = state.get("selection", {})
    validation_path = (
        selection.get("validation_path")
        if isinstance(selection, dict)
        else None
    )
    if not validation_path:
        issues.append("state.json selection.validation_path missing")
    else:
        try:
            validation_target = safe_join(project_root, validation_path)
        except TheMasterplanError:
            issues.append(f"unsafe validation_path: {validation_path}")
        else:
            if not validation_target.is_file():
                issues.append(
                    f"missing validation entrypoint: {validation_path}"
                )

    bin_root = safe_join(project_root, ".themasterplan/bin")
    for relative in EXECUTOR_FILES:
        destination = f".themasterplan/bin/{relative}"
        if not safe_join(bin_root, relative).is_file():
            issues.append(f"missing executor file: {destination}")
        elif destination not in managed:
            issues.append(f"executor hash not tracked: {destination}")

    ok = not issues
    return {
        "ok": ok,
        "status": "OK" if ok else "BROKEN",
        "issues": issues,
    }
