"""Utility helpers for the /TheMasterplan executor: path safety, hashing, atomic writes.

Only the Python standard library is used; no third-party dependencies.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1


class TheMasterplanError(Exception):
    """Base error for the /TheMasterplan executor; message is user-facing."""


class PathSafetyError(TheMasterplanError):
    """Raised when a target path escapes the repository root."""


def is_volatile_executor_artifact(relative: str) -> bool:
    """Return whether a state path is disposable Python bytecode.

    State paths are serialized with forward slashes. Only bytecode inside
    `.themasterplan/bin` is ignored; source files and other unexpected executor files
    remain subject to normal integrity checks.
    """
    if not isinstance(relative, str):
        return False
    path = PurePosixPath(relative)
    parts = path.parts
    return (
        len(parts) >= 3
        and parts[:2] == (".themasterplan", "bin")
        and (
            "__pycache__" in parts
            or path.suffix in {".pyc", ".pyo"}
        )
    )


def safe_join(root: Path, relative: str) -> Path:
    """Resolve root/relative and reject escapes, absolute paths and symlinks.

    `relative` must use forward slashes and must not contain ``..`` segments
    or be absolute. The resolved path must stay inside `root`.
    """
    rel = Path(relative)
    if rel.is_absolute():
        raise PathSafetyError(f"absolute path not allowed: {relative}")
    parts = rel.parts
    if any(part == ".." for part in parts):
        raise PathSafetyError(f"path traversal not allowed: {relative}")
    root_resolved = root.resolve()
    target = (root / rel).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        raise PathSafetyError(f"target escapes repository root: {relative}")
    return target


BLOCK_BEGIN = b"<!-- THEMASTERPLAN:BEGIN MANAGED -->"
BLOCK_END = b"<!-- THEMASTERPLAN:END MANAGED -->"


def sha256_of_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_of_block(path: Path) -> str:
    """Return the SHA-256 of a file's managed block (BEGIN..END markers).

    Returns "" when the block markers are missing, duplicated or malformed
    so the hash can never accidentally match a recorded value.
    """
    data = path.read_bytes()
    if data.count(BLOCK_BEGIN) != 1 or data.count(BLOCK_END) != 1:
        return ""
    begin = data.find(BLOCK_BEGIN)
    end = data.find(BLOCK_END)
    if end < begin:
        return ""
    return hashlib.sha256(data[begin : end + len(BLOCK_END)]).hexdigest()


def read_json(path: Path) -> dict:
    """Read a JSON file; raises TheMasterplanError with a readable message on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TheMasterplanError(f"file not found: {path}")
    except json.JSONDecodeError as exc:
        raise TheMasterplanError(f"invalid JSON in {path}: {exc}")


def write_json_atomic(path: Path, data: dict) -> None:
    """Atomically write a JSON file via a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_bytes_atomic(path: Path, content: bytes) -> None:
    """Atomically write raw bytes via a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
