"""Read-only update detection for adopted projects (v3.1.1).

Only the Python standard library is used. This module never writes to
managed project files; the only writable location is the disposable
``.themasterplan/cache/update-check.json`` cache.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .source import _resolve_tag_commit
from .util import TheMasterplanError, read_json, write_json_atomic

CACHE_TTL_SECONDS = 6 * 60 * 60
CACHE_FILE_NAME = "update-check.json"
SEMVER_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASES_URL = (
    "https://api.github.com/repos/{repository}/releases?per_page=30"
)
USER_AGENT = "themasterplan-update-check"


class UpdateCheckError(TheMasterplanError):
    """Raised when update detection cannot complete; message is user-facing."""


@dataclass(frozen=True)
class ReleaseIdentity:
    """Identity of a TheMasterplan release (stable or explicitly included)."""

    repository: str
    version: str
    commit: str
    release_url: str | None = None
    published_at: str | None = None
    prerelease: bool = False
    draft: bool = False

    def to_dict(self) -> dict:
        data: dict = {
            "repository": self.repository,
            "version": self.version,
            "commit": self.commit,
        }
        if self.release_url is not None:
            data["release_url"] = self.release_url
        if self.published_at is not None:
            data["published_at"] = self.published_at
        if self.prerelease:
            data["prerelease"] = True
        if self.draft:
            data["draft"] = True
        return data


def parse_semver(version: str) -> tuple[int, int, int] | None:
    """Parse ``vX.Y.Z`` into a comparable tuple; return None if not SemVer."""
    match = SEMVER_TAG_RE.fullmatch(version)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def read_current_identity(project_root: Path) -> ReleaseIdentity | None:
    """Read and validate ``.themasterplan/state.json`` without writing files.

    Returns None when the project is not adopted (no state file). Raises
    ``UpdateCheckError`` when the state file exists but is corrupted or
    its source identity is invalid.
    """
    state_path = project_root / ".themasterplan/state.json"
    if not state_path.is_file():
        return None
    try:
        state = read_json(state_path)
    except (TheMasterplanError, OSError, ValueError) as exc:
        raise UpdateCheckError(f"cannot read .themasterplan/state.json: {exc}") from exc
    if not isinstance(state, dict):
        raise UpdateCheckError(".themasterplan/state.json must be an object")
    source = state.get("source")
    if not isinstance(source, dict):
        raise UpdateCheckError(".themasterplan/state.json is missing source identity")
    repository = source.get("repository")
    version = source.get("version")
    commit = source.get("commit")
    if (
        not isinstance(repository, str)
        or REPOSITORY_RE.fullmatch(repository) is None
    ):
        raise UpdateCheckError("source.repository must be owner/repo")
    if not isinstance(version, str) or parse_semver(version) is None:
        raise UpdateCheckError("source.version must be a vX.Y.Z tag")
    if not isinstance(commit, str) or FULL_SHA_RE.fullmatch(commit) is None:
        raise UpdateCheckError("source.commit must be a full 40-char SHA")
    return ReleaseIdentity(
        repository=repository,
        version=version,
        commit=commit,
    )


def _fetch_releases(repository: str, *, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        RELEASES_URL.format(repository=repository),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                raise UpdateCheckError("release metadata exceeds safety limit")
            return payload
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise UpdateCheckError("GitHub API rate limit exceeded") from exc
        raise UpdateCheckError(
            f"GitHub release query failed (HTTP {exc.code})"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateCheckError("GitHub release query failed") from exc


def _pick_latest_stable(
    releases: list[dict], *, include_prerelease: bool
) -> dict | None:
    """Pick the newest eligible release; ignore draft, prerelease, non-SemVer."""
    best: tuple[int, int, int] | None = None
    best_release: dict | None = None
    for release in releases:
        if not isinstance(release, dict):
            continue
        if release.get("draft"):
            continue
        if not include_prerelease and release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str):
            continue
        parsed = parse_semver(tag)
        if parsed is None:
            continue
        if best is None or parsed > best:
            best = parsed
            best_release = release
    return best_release


def fetch_latest_stable_release(
    repository: str,
    *,
    include_prerelease: bool = False,
    timeout: int = 20,
) -> ReleaseIdentity:
    """Query immutable release metadata and resolve the tag to a full SHA."""
    raw = _fetch_releases(repository, timeout=timeout)
    try:
        releases = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError(
            "invalid GitHub response while listing releases"
        ) from exc
    if not isinstance(releases, list):
        raise UpdateCheckError("invalid GitHub response while listing releases")
    picked = _pick_latest_stable(releases, include_prerelease=include_prerelease)
    if picked is None:
        raise UpdateCheckError("no stable release found for repository")
    version = picked["tag_name"]
    try:
        commit = _resolve_tag_commit(repository, version, timeout=timeout)
    except TheMasterplanError as exc:
        raise UpdateCheckError(
            f"cannot resolve tag {version} to a commit SHA"
        ) from exc
    return ReleaseIdentity(
        repository=repository,
        version=version,
        commit=commit,
        release_url=picked.get("html_url"),
        published_at=picked.get("published_at"),
        prerelease=bool(picked.get("prerelease")),
        draft=bool(picked.get("draft")),
    )


def compare_versions(current: str, latest: str) -> str:
    """Return CURRENT, UPDATE_AVAILABLE, AHEAD, or UNKNOWN."""
    current_parsed = parse_semver(current)
    latest_parsed = parse_semver(latest)
    if current_parsed is None or latest_parsed is None:
        return "UNKNOWN"
    if current_parsed == latest_parsed:
        return "CURRENT"
    if current_parsed < latest_parsed:
        return "UPDATE_AVAILABLE"
    return "AHEAD"


def _cache_file(project_root: Path) -> Path:
    return project_root / ".themasterplan/cache" / CACHE_FILE_NAME


def _read_cache(
    project_root: Path, repository: str, *, include_prerelease: bool
) -> dict | None:
    path = _cache_file(project_root)
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except (TheMasterplanError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("repository") != repository:
        return None
    if bool(data.get("include_prerelease")) != include_prerelease:
        return None
    checked_at = data.get("checked_at")
    if not isinstance(checked_at, (int, float)):
        return None
    if time.time() - checked_at > CACHE_TTL_SECONDS:
        return None
    latest = data.get("latest")
    if (
        not isinstance(latest, dict)
        or not isinstance(latest.get("version"), str)
        or parse_semver(latest["version"]) is None
        or not isinstance(latest.get("commit"), str)
        or FULL_SHA_RE.fullmatch(latest["commit"]) is None
    ):
        return None
    for optional in ("release_url", "published_at"):
        if optional in latest and not isinstance(latest[optional], str):
            return None
    return latest


def _write_cache(
    project_root: Path,
    repository: str,
    latest: dict,
    *,
    include_prerelease: bool,
) -> None:
    """Best-effort cache write; failures never block the detection result."""
    try:
        path = _cache_file(project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            path,
            {
                "checked_at": time.time(),
                "repository": repository,
                "include_prerelease": include_prerelease,
                "latest": latest,
            },
        )
    except OSError:
        pass


def check_update(
    project_root: Path,
    *,
    repository: str | None = None,
    include_prerelease: bool = False,
    use_cache: bool = True,
) -> dict:
    """Return a machine-readable, read-only update status (v3.1.1 schema)."""
    project_root = Path(project_root)
    current = read_current_identity(project_root)

    if current is None:
        return {
            "schema_version": 1,
            "status": "NOT_ADOPTED",
            "current": None,
            "latest": None,
            "recommended_next_step": "continue-current-version",
            "writes_performed": False,
        }

    query_repository = repository or current.repository
    if REPOSITORY_RE.fullmatch(query_repository) is None:
        raise UpdateCheckError("repository must be owner/repo")

    latest: dict | None = None
    used_cache = False
    if use_cache:
        cached = _read_cache(
            project_root, query_repository, include_prerelease=include_prerelease
        )
        if cached is not None:
            latest = cached
            used_cache = True
    if latest is None:
        try:
            release = fetch_latest_stable_release(
                query_repository,
                include_prerelease=include_prerelease,
            )
        except UpdateCheckError as exc:
            return {
                "schema_version": 1,
                "status": "UNAVAILABLE",
                "current": current.to_dict(),
                "latest": None,
                "reason": str(exc),
                "recommended_next_step": "continue-current-version",
                "writes_performed": False,
            }
        latest = {
            "version": release.version,
            "commit": release.commit,
            **{
                key: value
                for key, value in (
                    ("release_url", release.release_url),
                    ("published_at", release.published_at),
                )
                if value is not None
            },
        }
        if release.prerelease:
            latest["prerelease"] = True
        if release.draft:
            latest["draft"] = True
        if use_cache:
            _write_cache(
                project_root,
                query_repository,
                latest,
                include_prerelease=include_prerelease,
            )

    status = compare_versions(current.version, latest["version"])
    if status == "CURRENT" and current.commit != latest["commit"]:
        # A version label alone is not an immutable identity. Treat an equal
        # version with a different SHA as unknown instead of claiming current.
        status = "UNKNOWN"
    recommended = (
        "ask-user" if status == "UPDATE_AVAILABLE" else "continue"
    )
    return {
        "schema_version": 1,
        "status": status,
        "current": current.to_dict(),
        "latest": latest,
        "recommended_next_step": recommended,
        "writes_performed": False,
        **({"cache_used": True} if used_cache else {}),
    }
