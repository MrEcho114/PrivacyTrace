"""TheMasterplan distribution manifest validation."""

from __future__ import annotations

import re
from pathlib import Path

from .util import TheMasterplanError, SCHEMA_VERSION, read_json, safe_join

ALLOWED_OWNERSHIPS = (
    "managed-replace",
    "managed-block",
    "generated-if-missing",
    "project-owned",
)
REQUIRED_KEYS = (
    "schema_version",
    "distribution_version",
    "source_repository",
    "files",
)

FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?$")


class ManifestError(TheMasterplanError):
    """Raised when a manifest is structurally invalid or unsafe."""


def load_manifest(path: Path) -> dict:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ManifestError("manifest must be an object")
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ManifestError(f"manifest missing required key: {key}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ManifestError(
            f"unsupported manifest schema_version: {data['schema_version']}"
        )
    version = data["distribution_version"]
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        raise ManifestError(
            "manifest distribution_version must be a vX.Y.Z-style tag"
        )
    repository = data["source_repository"]
    if (
        not isinstance(repository, str)
        or REPOSITORY_RE.fullmatch(repository) is None
    ):
        raise ManifestError("manifest source_repository must be owner/repo")
    files = data["files"]
    if not isinstance(files, list) or not files:
        raise ManifestError("manifest files must be a non-empty list")
    validate_files(files)
    return data


def validate_files(files: list) -> None:
    seen_destinations: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ManifestError("manifest file entry must be an object")
        for key in ("source", "destination", "ownership"):
            if key not in entry:
                raise ManifestError(f"manifest file entry missing key: {key}")
        source = entry["source"]
        destination = entry["destination"]
        ownership = entry["ownership"]
        if not isinstance(source, str) or not source:
            raise ManifestError("manifest source must be a non-empty string")
        if not isinstance(destination, str) or not destination:
            raise ManifestError(
                "manifest destination must be a non-empty string"
            )
        if ownership not in ALLOWED_OWNERSHIPS:
            raise ManifestError(f"unknown ownership type: {ownership}")
        for label, relative in (
            ("source", source),
            ("destination", destination),
        ):
            try:
                safe_join(Path("."), relative)
            except TheMasterplanError as exc:
                raise ManifestError(
                    f"manifest {label} {relative!r}: {exc}"
                ) from exc
        if destination in seen_destinations:
            raise ManifestError(
                f"duplicate destination in manifest: {destination}"
            )
        seen_destinations.add(destination)
        if "required" in entry and not isinstance(entry["required"], bool):
            raise ManifestError(
                "manifest file entry 'required' must be a boolean"
            )


def select_files(manifest: dict, profile: str) -> list[dict]:
    """Select managed files for the requested VCS profile.

    v5 removes the runtime Adapter abstraction. A legacy
    components.adapters field may remain in a distribution manifest only as
    an update-compatibility bridge for v4 executors; v5 selection ignores it.
    """
    profile_names = set(manifest.get("components", {}).get("profiles", []))
    selected: list[dict] = []
    for entry in manifest["files"]:
        destination = entry["destination"]
        if destination.startswith("profiles/"):
            if (
                profile not in profile_names
                or not destination.startswith(f"profiles/{profile}.")
            ):
                continue
        if destination.startswith("adapters/"):
            continue
        selected.append(entry)
    return selected
