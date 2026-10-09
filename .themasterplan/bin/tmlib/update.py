"""Safe plan-update/apply-update for TheMasterplan."""

from __future__ import annotations

import re
from pathlib import Path

from .apply import (
    BLOCK_BEGIN_BYTES,
    BLOCK_END_BYTES,
    _apply_block,
    _current_hash,
    _executor_state,
    _make_minimal_agents,
    _prepare_sources,
    _render_template,
    install_executor,
    prepare_executor_bundle,
)
from .manifest import ALLOWED_OWNERSHIPS, FULL_SHA_RE, select_files
from .source import Source, package_manifest
from .util import (
    TheMasterplanError,
    read_json,
    safe_join,
    sha256_of_block,
    sha256_of_file,
    write_bytes_atomic,
    write_json_atomic,
)

CLASSIFICATIONS = {
    "ADD",
    "UPDATE_SAFE",
    "UNCHANGED",
    "LOCAL_MODIFIED",
    "REMOVED_UPSTREAM",
    "PROJECT_OWNED",
    "SELECTION_CHANGED",
}
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class UpdateError(TheMasterplanError):
    """Raised when an update cannot be planned or applied safely."""


def _managed_entry(state: dict, relative: str) -> dict | None:
    managed = state.get("managed_files", {})
    if not isinstance(managed, dict):
        return None
    entry = managed.get(relative)
    return entry if isinstance(entry, dict) else None


def _recorded_hash(state: dict, relative: str) -> str | None:
    entry = _managed_entry(state, relative)
    value = entry.get("installed_sha256") if entry else None
    return value if isinstance(value, str) else None


def _recorded_ownership(state: dict, relative: str) -> str:
    entry = _managed_entry(state, relative)
    ownership = entry.get("ownership") if entry else None
    if ownership in ALLOWED_OWNERSHIPS:
        return ownership
    return "managed-replace"


def _local_hash(
    project_root: Path,
    relative: str,
    ownership: str,
) -> str | None:
    target = safe_join(project_root, relative)
    if not target.is_file():
        return None
    if ownership == "managed-block":
        return sha256_of_block(target)
    return sha256_of_file(target)


def _validate_source_identity(source: object) -> None:
    if not isinstance(source, dict):
        raise UpdateError("plan source must be an object")
    repository = source.get("repository")
    version = source.get("version")
    commit = source.get("commit")
    if (
        not isinstance(repository, str)
        or REPOSITORY_RE.fullmatch(repository) is None
    ):
        raise UpdateError("plan source.repository must be owner/repo")
    if not isinstance(version, str) or not version:
        raise UpdateError("plan source.version must be non-empty")
    if (
        not isinstance(commit, str)
        or FULL_SHA_RE.fullmatch(commit) is None
    ):
        raise UpdateError("plan source.commit must be a full SHA")


def plan_update(project_root: Path, source: Source, state: dict) -> dict:
    manifest = package_manifest(source.package_root)
    if manifest["source_repository"] != source.repository:
        raise UpdateError("resolver/manifest repository mismatch")
    if manifest["distribution_version"] != source.version:
        raise UpdateError("resolver/manifest version mismatch")

    selection = state.get("selection", {})
    if not isinstance(selection, dict):
        raise UpdateError("state selection must be an object")
    profile = selection.get("profile")
    if not isinstance(profile, str):
        raise UpdateError("state selection missing profile")

    # v5 removes the Adapter abstraction. A v4 generic Adapter is a known
    # no-op and is normalized away. Unknown historical values remain
    # fail-closed instead of being silently reinterpreted.
    legacy_adapter = selection.get("adapter")
    if legacy_adapter not in (None, "generic"):
        return {
            "schema_version": 1,
            "plan_type": "update",
            "source": source.as_dict(),
            "selection": selection,
            "files": [],
            "notes": [],
            "stop_conditions": [
                "selection no longer supported by v5: "
                f"adapter={legacy_adapter}"
            ],
        }

    normalized_selection = dict(selection)
    normalized_selection.pop("adapter", None)

    components = manifest.get("components", {})
    profile_names = set(components.get("profiles", []))
    if profile not in profile_names:
        return {
            "schema_version": 1,
            "plan_type": "update",
            "source": source.as_dict(),
            "selection": normalized_selection,
            "files": [],
            "notes": [],
            "stop_conditions": [
                "selection no longer supported by manifest: "
                f"profile={profile}"
            ],
        }

    entries = [
        entry
        for entry in select_files(manifest, profile)
        if entry["destination"]
        not in (".github/workflows/check.yml", "scripts/check.sh")
    ]
    operations: list[dict] = []
    stop_conditions: list[str] = []
    notes: list[str] = []

    for entry in entries:
        destination = entry["destination"]
        ownership = entry["ownership"]
        operation = {
            "source": entry["source"],
            "destination": destination,
            "ownership": ownership,
            "required": entry.get("required", False),
        }

        recorded = _recorded_hash(state, destination)
        local = _local_hash(project_root, destination, ownership)
        if ownership == "project-owned":
            operation["classification"] = "PROJECT_OWNED"
            if local is not None:
                operation["observed_sha256"] = local
            operations.append(operation)
            continue

        source_target = safe_join(source.package_root, entry["source"])
        if not source_target.is_file():
            raise UpdateError(f"package source missing: {entry['source']}")
        source_hash = sha256_of_file(source_target)
        operation["source_sha256"] = source_hash

        if local is None:
            if recorded is None:
                operation["classification"] = "ADD"
            else:
                operation["classification"] = "LOCAL_MODIFIED"
                operation["observed_sha256"] = recorded
                stop_conditions.append(
                    f"locally deleted managed file: {destination}"
                )
            operations.append(operation)
            continue

        operation["observed_sha256"] = local
        if ownership == "managed-block":
            source_block = sha256_of_block(source_target)
            if not source_block:
                raise UpdateError(
                    f"invalid managed-block source: {entry['source']}"
                )
            if local == source_block:
                operation["classification"] = "UNCHANGED"
            elif recorded is not None and local == recorded:
                operation["classification"] = "UPDATE_SAFE"
            else:
                operation["classification"] = "LOCAL_MODIFIED"
                stop_conditions.append(
                    f"locally modified managed block: {destination}"
                )
        elif ownership == "managed-replace":
            if local == source_hash:
                operation["classification"] = "UNCHANGED"
            elif recorded is not None and local == recorded:
                operation["classification"] = "UPDATE_SAFE"
            else:
                operation["classification"] = "LOCAL_MODIFIED"
                stop_conditions.append(
                    f"locally modified managed file: {destination}"
                )
        else:
            # generated-if-missing remains project-controlled after creation.
            operation["classification"] = "UNCHANGED"
        operations.append(operation)

    managed_files = state.get("managed_files", {})
    if not isinstance(managed_files, dict):
        raise UpdateError("state managed_files must be an object")
    state_destinations = set(managed_files)
    target_destinations = {op["destination"] for op in operations}

    for destination in sorted(state_destinations - target_destinations):
        if destination.startswith(".themasterplan/bin/"):
            continue
        ownership = _recorded_ownership(state, destination)
        recorded = _recorded_hash(state, destination)
        local = _local_hash(project_root, destination, ownership)
        operation = {
            "source": None,
            "destination": destination,
            "ownership": ownership,
            "required": False,
        }
        if local is not None and recorded is not None and local == recorded:
            operation["classification"] = "REMOVED_UPSTREAM"
            operation["observed_sha256"] = local
        else:
            operation["classification"] = "LOCAL_MODIFIED"
            operation["observed_sha256"] = local
            stop_conditions.append(
                f"upstream removed but local differs: {destination}"
            )
        operations.append(operation)

    if source.as_dict() != state.get("source", {}):
        old_version = state.get("source", {}).get("version")
        notes.append(
            f"update {old_version} -> {source.version} ({source.commit})"
        )

    return {
        "schema_version": 1,
        "plan_type": "update",
        "source": source.as_dict(),
        "selection": normalized_selection,
        "files": operations,
        "notes": notes,
        "stop_conditions": stop_conditions,
    }


def _validate_hash(value: object, label: str) -> None:
    if not isinstance(value, str) or HASH_RE.fullmatch(value) is None:
        raise UpdateError(f"{label} must be a lowercase SHA-256")


def _validate_update_plan(plan: dict) -> None:
    if not isinstance(plan, dict):
        raise UpdateError("plan must be an object")
    if plan.get("schema_version") != 1 or plan.get("plan_type") != "update":
        raise UpdateError("unsupported plan schema/type")
    for key in ("source", "selection", "files"):
        if key not in plan:
            raise UpdateError(f"plan missing key: {key}")
    _validate_source_identity(plan["source"])
    if not isinstance(plan["selection"], dict):
        raise UpdateError("plan selection must be an object")
    if plan.get("stop_conditions"):
        raise UpdateError(f"plan has stop conditions: {plan['stop_conditions']}")

    files = plan["files"]
    if not isinstance(files, list) or not files:
        raise UpdateError("plan files must be a non-empty list")
    seen: set[str] = set()
    for operation in files:
        if not isinstance(operation, dict):
            raise UpdateError("plan file entry must be an object")
        for key in ("destination", "ownership", "classification"):
            if key not in operation:
                raise UpdateError(f"plan file entry missing key: {key}")
        destination = operation["destination"]
        if not isinstance(destination, str) or not destination:
            raise UpdateError("destination must be non-empty")
        safe_join(Path("."), destination)
        if destination in seen:
            raise UpdateError(f"duplicate destination: {destination}")
        seen.add(destination)

        ownership = operation["ownership"]
        classification = operation["classification"]
        if ownership not in ALLOWED_OWNERSHIPS:
            raise UpdateError(f"unknown ownership: {ownership}")
        if classification not in CLASSIFICATIONS:
            raise UpdateError(f"unknown classification: {classification}")
        if classification in {"LOCAL_MODIFIED", "SELECTION_CHANGED"}:
            raise UpdateError(
                f"non-applicable classification: {classification}"
            )

        source = operation.get("source")
        if classification in {"ADD", "UPDATE_SAFE", "UNCHANGED"}:
            if not isinstance(source, str) or not source:
                raise UpdateError(
                    f"{classification} requires a package source"
                )
            safe_join(Path("."), source)
            _validate_hash(
                operation.get("source_sha256"),
                f"{destination}.source_sha256",
            )
        if classification in {
            "UPDATE_SAFE",
            "UNCHANGED",
            "REMOVED_UPSTREAM",
        }:
            _validate_hash(
                operation.get("observed_sha256"),
                f"{destination}.observed_sha256",
            )


def _check_update_target(project_root: Path, operation: dict) -> None:
    destination = safe_join(project_root, operation["destination"])
    classification = operation["classification"]
    if classification == "ADD":
        if destination.exists():
            raise UpdateError(
                f"plan says ADD but target exists: {operation['destination']}"
            )
        return
    if classification == "PROJECT_OWNED":
        return
    if classification in {
        "UPDATE_SAFE",
        "UNCHANGED",
        "REMOVED_UPSTREAM",
    }:
        if not destination.is_file():
            raise UpdateError(
                f"plan says {classification} but target is missing: "
                f"{operation['destination']}"
            )
        current = _current_hash(destination, operation["ownership"])
        if current != operation.get("observed_sha256"):
            raise UpdateError(
                "target changed since plan; refusing update: "
                f"{operation['destination']}"
            )
        return
    raise UpdateError(f"cannot apply classification {classification}")


def _remove_managed_block(destination: Path) -> None:
    data = destination.read_bytes()
    if data.count(BLOCK_BEGIN_BYTES) != 1 or data.count(BLOCK_END_BYTES) != 1:
        raise UpdateError(f"managed block markers invalid: {destination}")
    begin = data.find(BLOCK_BEGIN_BYTES)
    end = data.find(BLOCK_END_BYTES)
    if end < begin:
        raise UpdateError(f"managed block marker order invalid: {destination}")
    end += len(BLOCK_END_BYTES)
    remaining = data[:begin] + data[end:]
    if remaining.strip():
        write_bytes_atomic(destination, remaining)
    else:
        destination.unlink()


def apply_update(
    project_root: Path,
    plan_path: Path,
    source: Source | None = None,
) -> dict:
    plan = read_json(plan_path)
    _validate_update_plan(plan)
    if source is None:
        raise UpdateError(
            "apply-update requires --source for immutable identity verification"
        )
    if source.as_dict() != plan["source"]:
        raise UpdateError("resolver source does not match plan source")

    prepared_sources = _prepare_sources(plan, source.package_root)
    prepared_executor = prepare_executor_bundle(source)

    for operation in plan["files"]:
        _check_update_target(project_root, operation)

    written: list[str] = []
    unchanged: list[str] = []
    removed: list[str] = []

    for operation in plan["files"]:
        destination = safe_join(project_root, operation["destination"])
        classification = operation["classification"]
        if classification in {"UNCHANGED", "PROJECT_OWNED"}:
            unchanged.append(operation["destination"])
        elif classification == "ADD":
            content = prepared_sources[operation["destination"]]
            if operation.get("render"):
                content = _render_template(content, plan)
            if operation["destination"] == "AGENTS.md":
                content = _make_minimal_agents(content)
            write_bytes_atomic(destination, content)
            written.append(operation["destination"])
        elif classification == "UPDATE_SAFE":
            content = prepared_sources[operation["destination"]]
            if operation.get("render"):
                content = _render_template(content, plan)
            if operation["ownership"] == "managed-block":
                _apply_block(project_root, operation, content)
            else:
                write_bytes_atomic(destination, content)
            written.append(operation["destination"])
        elif classification == "REMOVED_UPSTREAM":
            if operation["ownership"] == "managed-block":
                _remove_managed_block(destination)
            else:
                destination.unlink()
            removed.append(operation["destination"])
        else:
            raise UpdateError(
                f"cannot apply classification {classification}"
            )

    written, unchanged = install_executor(
        project_root,
        written,
        unchanged,
        source=source,
        prepared=prepared_executor,
    )
    state = _build_updated_state(project_root, plan)
    write_json_atomic(project_root / ".themasterplan/state.json", state)
    return {
        "written": written,
        "unchanged": unchanged,
        "removed": removed,
    }


def _build_updated_state(project_root: Path, plan: dict) -> dict:
    managed: dict[str, dict] = {}
    for operation in plan["files"]:
        destination = operation["destination"]
        if operation["classification"] == "REMOVED_UPSTREAM":
            continue
        if operation["ownership"] not in {
            "managed-replace",
            "managed-block",
        }:
            continue
        target = safe_join(project_root, destination)
        if not target.is_file():
            continue
        installed = (
            sha256_of_block(target)
            if operation["ownership"] == "managed-block"
            else sha256_of_file(target)
        )
        managed[destination] = {
            "source": operation.get("source"),
            "source_sha256": operation.get("source_sha256"),
            "installed_sha256": installed,
            "ownership": operation["ownership"],
        }

    managed.update(_executor_state(project_root))

    return {
        "schema_version": 1,
        "source": plan["source"],
        "selection": plan["selection"],
        "managed_files": managed,
        "adoption": {
            "date": None,
            "platform": None,
            "git_version": None,
            "jj_version": None,
            "status": "PARTIAL",
        },
    }
