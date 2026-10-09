"""Read-only TheMasterplan installation diagnostics."""

from __future__ import annotations

import re
from pathlib import Path

from .apply import EXECUTOR_FILES
from .manifest import FULL_SHA_RE
from .util import (
    TheMasterplanError,
    is_volatile_executor_artifact,
    read_json,
    safe_join,
    sha256_of_block,
    sha256_of_file,
)

CORE_PATHS = ("core/policy.md", "core/workflow.md")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _check_managed(
    project_root: Path,
    relative: str,
    recorded: dict,
) -> list[str]:
    try:
        target = safe_join(project_root, relative)
    except TheMasterplanError as exc:
        return [f"unsafe path in state: {relative} ({exc})"]
    if not target.is_file():
        return [f"missing managed file: {relative}"]

    expected = recorded.get("installed_sha256")
    if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
        return [f"invalid installed hash in state: {relative}"]

    if recorded.get("ownership") == "managed-block":
        current = sha256_of_block(target)
        if not current:
            return [f"managed block missing or malformed: {relative}"]
    else:
        current = sha256_of_file(target)
    if current != expected:
        return [f"hash mismatch (managed file modified): {relative}"]
    return []


def _deduplicate(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def doctor(project_root: Path) -> dict:
    issues: list[str] = []
    suggestions: list[str] = []
    state_path = project_root / ".themasterplan/state.json"
    if not state_path.is_file():
        return {
            "ok": False,
            "status": "ABSENT",
            "issues": ["missing .themasterplan/state.json (TheMasterplan not adopted)"],
            "suggestions": ["run plan-adopt + apply-adopt"],
        }
    try:
        state = read_json(state_path)
    except TheMasterplanError as exc:
        return {
            "ok": False,
            "status": "BROKEN",
            "issues": [f"state.json unreadable: {exc}"],
            "suggestions": ["repair or re-adopt .themasterplan/state.json"],
        }

    if state.get("schema_version") != 1:
        issues.append("state.json schema_version is unsupported")

    source = state.get("source", {})
    if not isinstance(source, dict):
        issues.append("state.json source must be an object")
    else:
        repository = source.get("repository")
        commit = source.get("commit")
        version = source.get("version")
        if not isinstance(repository, str) or "/" not in repository:
            issues.append("state.json source.repository missing or malformed")
        if (
            not isinstance(commit, str)
            or FULL_SHA_RE.fullmatch(commit) is None
        ):
            issues.append("state.json source.commit missing or malformed")
        if not isinstance(version, str) or not version:
            issues.append("state.json source.version missing")

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
                suggestions.append(f"restore {validation_path}")

    for relative in CORE_PATHS:
        target = safe_join(project_root, relative)
        if not target.is_file():
            issues.append(f"missing required: {relative}")
            suggestions.append(f"restore {relative}")

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
            current_issues = _check_managed(
                project_root,
                relative,
                recorded,
            )
            issues.extend(current_issues)
            if any(
                issue.startswith("hash mismatch")
                for issue in current_issues
            ):
                suggestions.append(
                    f"review or revert local changes to {relative}"
                )

    bin_root = safe_join(project_root, ".themasterplan/bin")
    for relative in EXECUTOR_FILES:
        destination = f".themasterplan/bin/{relative}"
        target = safe_join(bin_root, relative)
        if not target.is_file():
            issues.append(f"missing executor file: {destination}")
            continue
        if destination not in managed:
            issues.append(f"untracked executor file in state: {destination}")
            suggestions.append(
                "run a repaired apply-update to rebuild executor state hashes"
            )

    if not issues:
        return {
            "ok": True,
            "status": "OK",
            "issues": [],
            "suggestions": [],
        }
    return {
        "ok": False,
        "status": "ISSUES_FOUND",
        "issues": _deduplicate(issues),
        "suggestions": _deduplicate(suggestions),
    }
