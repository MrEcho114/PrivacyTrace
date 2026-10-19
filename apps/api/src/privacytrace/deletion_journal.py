"""Private deletion intents retained independently from an instance backup.

An authenticated intent is flushed before the database tombstone can commit.
Replaying an intent after an uncertain commit is deliberately conservative.
"""

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .job_store import JobStore
from .runner_protocol import canonical_uuid
from .runtime_tls import json_value

MAX_JOURNAL = 32 * 1024 * 1024


def fsync_directory(path):
    # Windows file fsync remains in place. POSIX additionally commits the
    # directory entry before the corresponding database reference is published.
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class DeletionJournal:
    def __init__(self, root, instance_id, signing_key):
        canonical_uuid(instance_id)
        if type(signing_key) is not bytes or len(signing_key) != 32:
            raise ValueError("Private deletion signing key required")
        self.instance_id = instance_id
        self._key = hmac.digest(signing_key, b"privacytrace.deletion.key.v1", "sha256")
        self.root = Path(root).absolute()
        for part in (self.root, *self.root.parents):
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                raise ValueError("Linked deletion journal rejected")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if os.name == "posix" and (
            self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077
        ):
            raise ValueError("Private deletion journal directory required")
        self.lock = JobStore(self.root)
        self.path = self.root / "deletions.jsonl"

    @classmethod
    def for_store(cls, store, signing_key):
        configured = os.environ.get("PRIVACYTRACE_DELETION_JOURNAL_ROOT")
        base = Path(configured) if configured else store.root.parent.parent / "deletion-journal"
        return cls(base / store.instance_id, store.instance_id, signing_key)

    @staticmethod
    def _payload(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    def _read(self):
        if self.path.is_symlink() or getattr(self.path, "is_junction", lambda: False)():
            raise ValueError("Linked deletion journal rejected")
        if not self.path.exists():
            return []
        if (
            self.path.is_symlink()
            or self.path.stat().st_nlink != 1
            or self.path.stat().st_size > MAX_JOURNAL
        ):
            raise ValueError("Deletion journal integrity rejected")
        raw = self.path.read_bytes()
        tail = None
        if raw and not raw.endswith(b"\n"):
            # No DB commit/ack can precede a complete fsynced record. Preserve
            # a torn, unacknowledged tail before repairing it under the lock.
            boundary = raw.rfind(b"\n") + 1
            tail = raw[boundary:]
            raw = raw[:boundary]
        result, previous = [], "0" * 64
        for line in raw.splitlines():
            try:
                if len(line) > 4096:
                    raise ValueError
                value = json_value(line)
                if set(value) != {
                    "version",
                    "instance_id",
                    "sequence",
                    "kind",
                    "scope_id",
                    "at",
                    "previous",
                    "mac",
                }:
                    raise ValueError
                mac = value.pop("mac")
                expected = hmac.digest(self._key, self._payload(value), "sha256").hex()
                if (
                    not hmac.compare_digest(mac, expected)
                    or value["instance_id"] != self.instance_id
                    or type(value["version"]) is not int
                    or value["version"] != 1
                    or type(value["sequence"]) is not int
                    or value["sequence"] != len(result) + 1
                    or value["previous"] != previous
                    or value["kind"] not in {"JOB", "DRAFT"}
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value["scope_id"])
                ):
                    raise ValueError
                if datetime.fromisoformat(value["at"]).tzinfo is None:
                    raise ValueError
                value["mac"] = mac
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                raise ValueError("Deletion journal integrity rejected") from None
            previous = mac
            result.append(value)
        if tail is not None:
            # Authenticate the complete prefix before touching a torn tail.
            saved = self.root / ("torn-" + hashlib.sha256(tail).hexdigest() + ".partial")
            if not saved.exists():
                fd = os.open(saved, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as output:
                    output.write(tail)
                    output.flush()
                    os.fsync(output.fileno())
            with self.path.open("r+b") as output:
                output.truncate(len(raw))
                output.flush()
                os.fsync(output.fileno())
            fsync_directory(self.root)
        return result

    def entries(self):
        with self.lock._transaction():
            return self._read()

    def append(self, kind, scope_id):
        if (
            kind not in {"JOB", "DRAFT"}
            or type(scope_id) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", scope_id)
        ):
            raise ValueError("Invalid deletion scope")
        with self.lock._transaction():
            previous = self._read()
            existing = next(
                (
                    item
                    for item in previous
                    if item["kind"] == kind and item["scope_id"] == scope_id
                ),
                None,
            )
            if existing:
                return existing
            entry = {
                "version": 1,
                "instance_id": self.instance_id,
                "sequence": len(previous) + 1,
                "kind": kind,
                "scope_id": scope_id,
                "at": datetime.now(timezone.utc).isoformat(),
                "previous": previous[-1]["mac"] if previous else "0" * 64,
            }
            entry["mac"] = hmac.digest(self._key, self._payload(entry), "sha256").hex()
            raw = self._payload(entry) + b"\n"
            if (self.path.stat().st_size if self.path.exists() else 0) + len(raw) > MAX_JOURNAL:
                raise ValueError("Deletion journal capacity reached")
            fd = os.open(
                self.path,
                os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(fd, "ab") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            fsync_directory(self.root)
            return entry

    def require_admission_capacity(self):
        with self.lock._transaction():
            self._read()
            # Reserve over 1 MiB for deleting all admitted active scopes after
            # new intake has stopped. Deletion never depends on object quotas.
            if self.path.exists() and self.path.stat().st_size > MAX_JOURNAL - 1024 * 1024:
                raise ValueError("Deletion history capacity requires operator action before intake")
