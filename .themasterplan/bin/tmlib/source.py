"""Immutable source resolution for the TheMasterplan executor.

Compatibility:
- ``.themasterplan/`` is the adoption state directory; ``/TheMasterplan`` is the protocol entry.
- Remote archives are always addressed by a full commit SHA. A tag is
  resolved first and is never used as the archive/cache identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .manifest import FULL_SHA_RE, load_manifest
from .util import TheMasterplanError, safe_join

DEFAULT_REPOSITORY = "OasisSaber/TheMasterplan"
ARCHIVE_URL = "https://codeload.github.com/{repository}/tar.gz/{commit}"
API_COMMIT_URL = "https://api.github.com/repos/{repository}/commits/{ref}"

REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.-]+)?$")

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024
SOURCE_MARKER = ".themasterplan-source.json"


class SourceError(TheMasterplanError):
    """Raised when a source cannot be resolved or fails identity checks."""


@dataclass(frozen=True)
class Source:
    repository: str
    version: str
    commit: str
    package_root: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "repository": self.repository,
            "version": self.version,
            "commit": self.commit,
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_repository(repository: str) -> None:
    if not REPOSITORY_RE.fullmatch(repository):
        raise SourceError(f"repository must be owner/repo: {repository!r}")


def package_manifest(package_root: Path) -> dict:
    manifest_path = safe_join(package_root, "distribution/manifest.json")
    if not manifest_path.is_file():
        raise SourceError(
            f"package missing distribution/manifest.json at {package_root}"
        )
    return load_manifest(manifest_path)


def read_package_file(package_root: Path, relative: str) -> bytes:
    target = safe_join(package_root, relative)
    if not target.is_file():
        raise SourceError(f"package file missing: {relative}")
    return target.read_bytes()


def _local_git_head(package_root: Path) -> str | None:
    try:
        process = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(package_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if process.returncode != 0:
        return None
    sha = process.stdout.strip()
    return sha if FULL_SHA_RE.fullmatch(sha) else None


def resolve_local(package_root: Path, commit: str | None = None) -> Source:
    """Resolve a local package.

    Explicit ``commit`` is retained for exported trees and test fixtures.
    Normal Git checkouts should omit it and use the detected HEAD.
    """
    package_root = package_root.resolve()
    manifest = package_manifest(package_root)
    repository = manifest["source_repository"]
    _validate_repository(repository)

    resolved_commit = commit or _local_git_head(package_root)
    if resolved_commit is None:
        raise SourceError(
            f"cannot resolve commit for local package {package_root}; pass --commit"
        )
    if not FULL_SHA_RE.fullmatch(resolved_commit):
        raise SourceError(
            f"commit must be a full 40-char lowercase SHA: {resolved_commit!r}"
        )

    return Source(
        repository=repository,
        version=manifest["distribution_version"],
        commit=resolved_commit,
        package_root=package_root,
    )


def _request_bytes(url: str, *, timeout: int, max_bytes: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "themasterplan-updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                remaining = max_bytes - total
                chunk = response.read(min(1024 * 1024, remaining + 1))
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise SourceError(
                        f"download exceeds safety limit ({max_bytes} bytes): {url}"
                    )
                chunks.append(chunk)
            return b"".join(chunks)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"download failed: {url} ({exc})") from exc


def _resolve_tag_commit(repository: str, tag: str, timeout: int = 20) -> str:
    url = API_COMMIT_URL.format(repository=repository, ref=tag)
    raw = _request_bytes(url, timeout=timeout, max_bytes=2 * 1024 * 1024)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceError(f"invalid GitHub response while resolving tag {tag}") from exc
    sha = payload.get("sha") if isinstance(payload, dict) else None
    if not isinstance(sha, str) or not FULL_SHA_RE.fullmatch(sha):
        raise SourceError(f"cannot resolve tag {tag} to a full commit SHA")
    return sha


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _read_digest(path: Path) -> str | None:
    try:
        digest = path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    return digest if re.fullmatch(r"[0-9a-f]{64}", digest) else None


def _download_archive(url: str, cache_path: Path, timeout: int = 45) -> Path:
    """Use a SHA-256 sidecar to detect corrupted local cache entries."""
    digest_path = cache_path.with_suffix(cache_path.suffix + ".sha256")
    if cache_path.is_file():
        expected = _read_digest(digest_path)
        if expected is not None:
            actual = hashlib.sha256(cache_path.read_bytes()).hexdigest()
            if actual == expected:
                return cache_path
        cache_path.unlink(missing_ok=True)
        digest_path.unlink(missing_ok=True)

    data = _request_bytes(url, timeout=timeout, max_bytes=MAX_ARCHIVE_BYTES)
    _write_atomic(cache_path, data)
    _write_atomic(
        digest_path,
        (_sha256_bytes(data) + "\n").encode("ascii"),
    )
    return cache_path


def _safe_member_path(destination: Path, name: str) -> Path:
    if not name or "\x00" in name:
        raise SourceError(f"unsafe archive member: {name!r}")
    target = safe_join(destination, name)
    if target == destination:
        raise SourceError(f"unsafe archive member: {name!r}")
    return target


def _extract_archive(archive: Path, destination: Path) -> None:
    """Reject traversal, links, devices, and oversized archives."""
    destination.mkdir(parents=True, exist_ok=True)
    member_count = 0
    extracted_bytes = 0

    def account(size: int) -> None:
        nonlocal member_count, extracted_bytes
        member_count += 1
        extracted_bytes += max(size, 0)
        if member_count > MAX_ARCHIVE_MEMBERS:
            raise SourceError("archive contains too many members")
        if extracted_bytes > MAX_EXTRACTED_BYTES:
            raise SourceError("archive expands beyond the safety limit")

    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                account(member.file_size)
                target = _safe_member_path(destination, member.filename)
                unix_mode = (member.external_attr >> 16) & 0o170000
                if unix_mode == 0o120000:
                    raise SourceError(
                        f"archive member must not be a symlink: {member.filename}"
                    )
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, open(target, "wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        return

    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            account(member.size)
            target = _safe_member_path(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = bundle.extractfile(member)
                if extracted is None:
                    raise SourceError(
                        f"cannot extract archive member: {member.name}"
                    )
                with extracted, open(target, "wb") as output:
                    shutil.copyfileobj(extracted, output, length=1024 * 1024)
            else:
                raise SourceError(
                    f"unsupported archive member type: {member.name}"
                )


def _single_top_level(extracted_root: Path) -> Path:
    children = list(extracted_root.iterdir())
    if len(children) != 1 or not children[0].is_dir():
        raise SourceError("source archive must contain one top-level directory")
    return children[0]


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.name == SOURCE_MARKER:
            continue
        if path.is_symlink():
            raise SourceError(f"cached source contains symlink: {path}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        if path.is_dir():
            digest.update(b"D\0" + relative + b"\0")
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        else:
            raise SourceError(f"cached source contains unsupported entry: {path}")
    return digest.hexdigest()


def _validate_manifest_identity(
    manifest: dict,
    *,
    requested_repository: str,
    expected_version: str | None,
) -> None:
    manifest_repository = manifest.get("source_repository")
    if manifest_repository != requested_repository:
        raise SourceError(
            "manifest repository mismatch: "
            f"requested {requested_repository}, got {manifest_repository!r}"
        )
    if expected_version is not None:
        actual = manifest.get("distribution_version")
        if actual != expected_version:
            raise SourceError(
                f"manifest version mismatch: expected {expected_version}, got {actual}"
            )


def _load_cached_source(
    source_cache: Path,
    *,
    repository: str,
    version: str | None,
    commit: str,
) -> Source | None:
    marker_path = source_cache / SOURCE_MARKER
    if not marker_path.is_file():
        return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(marker, dict):
        return None
    if marker.get("repository") != repository or marker.get("commit") != commit:
        return None
    if marker.get("tree_sha256") != _tree_digest(source_cache):
        return None

    manifest = package_manifest(source_cache)
    _validate_manifest_identity(
        manifest,
        requested_repository=repository,
        expected_version=version,
    )
    return Source(
        repository=repository,
        version=manifest["distribution_version"],
        commit=commit,
        package_root=source_cache,
    )


def resolve_remote(
    repository: str,
    ref: str,
    cache_dir: Path,
    *,
    commit: str | None = None,
    expected_version: str | None = None,
) -> Source:
    """Resolve a tag/SHA into immutable, commit-addressed package content."""
    _validate_repository(repository)
    cache_dir.mkdir(parents=True, exist_ok=True)

    is_sha = FULL_SHA_RE.fullmatch(ref) is not None
    is_tag = TAG_RE.fullmatch(ref) is not None
    if not is_sha and not is_tag:
        raise SourceError(
            f"ref must be a release tag or full commit SHA: {ref!r}"
        )
    if commit is not None and not FULL_SHA_RE.fullmatch(commit):
        raise SourceError(f"commit must be a full 40-char lowercase SHA: {commit!r}")

    if is_sha:
        resolved_commit = ref
        if commit is not None and commit != resolved_commit:
            raise SourceError(
                f"ref/commit mismatch: ref={resolved_commit}, commit={commit}"
            )
        version_lock = expected_version
    else:
        tag_commit = _resolve_tag_commit(repository, ref)
        if commit is not None and commit != tag_commit:
            raise SourceError(
                f"tag/commit mismatch: tag {ref} resolves to {tag_commit}, "
                f"not {commit}"
            )
        resolved_commit = tag_commit
        version_lock = expected_version or ref

    repository_key = repository.replace("/", "__")
    archive_path = (
        cache_dir / "archives" / f"{repository_key}@{resolved_commit}.tar.gz"
    )
    archive_url = ARCHIVE_URL.format(
        repository=repository,
        commit=resolved_commit,
    )
    archive = _download_archive(archive_url, archive_path)

    source_cache = (
        cache_dir / "sources" / f"{repository_key}@{resolved_commit}"
    )
    if source_cache.exists():
        cached = _load_cached_source(
            source_cache,
            repository=repository,
            version=version_lock,
            commit=resolved_commit,
        )
        if cached is not None:
            return cached
        shutil.rmtree(source_cache, ignore_errors=True)

    temporary = Path(
        tempfile.mkdtemp(prefix="themasterplan-source-", dir=str(cache_dir))
    )
    try:
        extracted_root = temporary / "extract"
        _extract_archive(archive, extracted_root)
        package_root = _single_top_level(extracted_root)
        manifest = package_manifest(package_root)
        _validate_manifest_identity(
            manifest,
            requested_repository=repository,
            expected_version=version_lock,
        )

        source_cache.parent.mkdir(parents=True, exist_ok=True)
        os.replace(package_root, source_cache)
        marker = {
            "repository": repository,
            "version": manifest["distribution_version"],
            "commit": resolved_commit,
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "tree_sha256": _tree_digest(source_cache),
        }
        _write_atomic(
            source_cache / SOURCE_MARKER,
            (json.dumps(marker, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            ),
        )
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    return Source(
        repository=repository,
        version=manifest["distribution_version"],
        commit=resolved_commit,
        package_root=source_cache,
    )


def resolve_source(
    source_ref: str,
    cache_dir: Path | None = None,
    *,
    commit: str | None = None,
    expected_repository: str | None = None,
) -> Source:
    candidate = Path(source_ref)
    if candidate.is_dir():
        source = resolve_local(candidate, commit=commit)
        if (
            expected_repository is not None
            and source.repository != expected_repository
        ):
            raise SourceError(
                "local source repository mismatch: "
                f"expected {expected_repository}, got {source.repository}"
            )
        return source

    if cache_dir is None:
        raise SourceError(f"remote source requires a cache dir: {source_ref}")
    return resolve_remote(
        expected_repository or DEFAULT_REPOSITORY,
        source_ref,
        cache_dir,
        commit=commit,
    )
