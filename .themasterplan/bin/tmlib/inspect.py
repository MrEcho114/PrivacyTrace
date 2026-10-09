"""Machine-checkable project state detection for the /TheMasterplan executor.

Classifies a project as one of ABSENT / INCOMPLETE / CURRENT / OUTDATED /
MODIFIED / BROKEN based on file presence, state.json and content hashes.
The classification must be mechanical, not agent-asserted.
"""

from __future__ import annotations

from pathlib import Path

from .manifest import load_manifest
from .util import (
    TheMasterplanError,
    is_volatile_executor_artifact,
    read_json,
    safe_join,
    sha256_of_block,
    sha256_of_file,
)

STATUSES = ("ABSENT", "INCOMPLETE", "CURRENT", "OUTDATED", "MODIFIED", "BROKEN")

STATE_PATH = Path(".themasterplan/state.json")
CORE_PATHS = (Path("core/policy.md"), Path("core/workflow.md"))


def _managed_entries(state: dict) -> dict:
    return state.get("managed_files", {})


def _installed_hash_matches(project_root: Path, relative: str, recorded: dict) -> bool:
    try:
        target = safe_join(project_root, relative)
    except TheMasterplanError:
        return False
    if not target.is_file():
        return False
    if recorded.get("ownership") == "managed-block":
        # managed-block: compare only the managed block hash, never the
        # whole file (content outside the block belongs to the project).
        return sha256_of_block(target) == recorded.get("installed_sha256")
    return sha256_of_file(target) == recorded.get("installed_sha256")


def _has_core_files(project_root: Path) -> bool:
    for p in CORE_PATHS:
        try:
            target = safe_join(project_root, str(p))
        except TheMasterplanError:
            return False
        if not target.is_file():
            return False
    return True


def _missing_required(project_root: Path, state: dict | None) -> list[str]:
    missing: list[str] = []
    if state is None:
        if not _has_core_files(project_root):
            for p in CORE_PATHS:
                try:
                    target = safe_join(project_root, str(p))
                except TheMasterplanError:
                    missing.append(str(p))
                    continue
                if not target.is_file():
                    missing.append(str(p))
        return missing
    for relative, recorded in _managed_entries(state).items():
        if is_volatile_executor_artifact(relative):
            continue
        try:
            target = safe_join(project_root, relative)
        except TheMasterplanError:
            missing.append(relative)
            continue
        if not target.is_file():
            missing.append(relative)
    return missing


def detect_status(project_root: Path, target_version: str | None = None) -> tuple[str, list[str]]:
    """Return (status, issues). `target_version` enables OUTDATED detection."""
    issues: list[str] = []
    state_path = project_root / STATE_PATH
    state: dict | None = None
    if state_path.is_file():
        try:
            state = read_json(state_path)
        except TheMasterplanError as exc:
            return "BROKEN", [f"state.json unreadable: {exc}"]

    if state is None:
        core_present = [str(p) for p in CORE_PATHS if (project_root / p).is_file()]
        if not core_present:
            return "ABSENT", _missing_required(project_root, None)
        return "INCOMPLETE", _missing_required(project_root, None)

    # state exists: validate minimal structure
    source = state.get("source", {})
    if not isinstance(source, dict) or not source.get("version"):
        return "BROKEN", ["state.json missing source.version"]
    managed = _managed_entries(state)
    if not isinstance(managed, dict):
        return "BROKEN", ["state.json managed_files must be an object"]

    missing = _missing_required(project_root, state)
    modified: list[str] = []
    for relative, recorded in managed.items():
        if is_volatile_executor_artifact(relative):
            continue
        if not isinstance(recorded, dict) or "installed_sha256" not in recorded:
            issues.append(f"state entry malformed: {relative}")
            continue
        if not _installed_hash_matches(project_root, relative, recorded):
            modified.append(relative)
    if missing or issues:
        return "BROKEN", missing + issues

    # MODIFIED takes precedence over OUTDATED: local divergence is the
    # higher-risk condition and must be surfaced first.
    if modified:
        return "MODIFIED", [f"locally modified managed file(s): {', '.join(modified)}"]
    version = source["version"]
    if target_version is not None and version != target_version:
        return "OUTDATED", [f"installed {version}, target {target_version}"]
    return "CURRENT", []


def detect_profile(project_root: Path) -> str:
    """Detect the VCS profile: jj when a .jj dir exists, else git."""
    if (project_root / ".jj").exists():
        return "jj"
    return "git"


def inspect(project_root: Path, target_version: str | None = None) -> dict:
    """Produce the inspect JSON result."""
    status, issues = detect_status(project_root, target_version)
    return {
        "status": status,
        "root": str(project_root),
        "git": (project_root / ".git").exists(),
        "jj": (project_root / ".jj").exists(),
        "detected_profile": detect_profile(project_root),
        "issues": issues,
    }
