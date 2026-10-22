"""Existing intake semantics backed by transactional PostgreSQL material manifests."""

import hashlib
import json
import os
import stat
from uuid import uuid4

from .capacity import CapacityRefused
from .deletion_journal import fsync_directory
from .policy_intake import read_safe
from .web_intake import WebIntake


class PostgresWebIntake(WebIntake):
    # Per-instance immutable objects, including replaced pointers and crash residue.
    # Bound file count as well as bytes so empty/very small objects cannot grow forever.
    MAX_OBJECT_BYTES = 1536 * 1024 * 1024
    MAX_OBJECTS = 16384

    def __init__(self, store):
        super().__init__(store)
        self.data_store = store
        self.materials = self._safe(self.root / ".objects")
        self.materials.mkdir(mode=0o700, exist_ok=True)

    def _key(self, path):
        return self._safe(path).relative_to(self.root).as_posix()

    def _document_exists(self, path):
        try:
            self.store.document(self._key(path))
            return True
        except KeyError:
            return False

    def _draft_directories(self):
        # Orphan directories from aborted transactions are not authorized drafts.
        return [self.directory(draft_id) for draft_id in self.store.draft_ids()]

    def _touch(self, draft_id):
        # Markers can be reconstructed after a committed DB write/crash; their
        # bytes cannot grant access or replace the indexed immutable material.
        path = self._safe(self.directory(draft_id) / "current.json")
        path.parent.mkdir(mode=0o700, exist_ok=True)
        path.touch(mode=0o600, exist_ok=True)

    def _read(self, path):
        manifest = self.store.document(self._key(path))
        raw = read_safe(
            self._safe(self.materials / manifest["material_ref"]), max_bytes=8 * 1024 * 1024
        )
        if (
            len(raw) != manifest["byte_count"]
            or hashlib.sha256(raw).hexdigest() != manifest["sha256"]
        ):
            raise ValueError("Private material integrity check failed")
        return json.loads(raw)

    def _write_private(self, path, value):
        """Flush an immutable object before committing its database reference.

        Logical files are existence/activity markers only. They carry no private
        input and are never used as a source of authority. A rolled-back write
        can leave an unreferenced object; it cannot replace committed contents.
        """
        # The instance advisory lock covers measurement through publication, even
        # when a caller has not opened an outer transaction. Never delete an old
        # object here: its reference may still be committed or needed for recovery.
        with self.store._transaction():
            key = self._key(path)
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError("Input revision too large")
            self._check_object_capacity(len(raw))
            reference = uuid4().hex
            target = self._safe(self.materials / reference)
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            fsync_directory(self.materials)
            self.store.save_document(
                key,
                reference,
                hashlib.sha256(raw).hexdigest(),
                len(raw),
                token_digest=(
                    value.get("token_digest") if key.endswith("/capability.json") else None
                ),
            )
            # Retain the single-host intake's directory/mtime/upload bookkeeping.
            self._safe(path).touch(mode=0o600, exist_ok=True)

    def _check_object_capacity(self, incoming_bytes):
        used, count = 0, 0
        for path in self._safe(self.materials).iterdir():
            info = self._safe(path).stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Unexpected private material entry")
            used += info.st_size
            count += 1
            if count >= self.MAX_OBJECTS or used + incoming_bytes > self.MAX_OBJECT_BYTES:
                raise CapacityRefused(
                    "PRIVATE_MATERIAL_CAPACITY_REACHED",
                    "Private material capacity reached; operator action required",
                )
        if incoming_bytes > self.MAX_OBJECT_BYTES:
            raise CapacityRefused(
                "PRIVATE_MATERIAL_CAPACITY_REACHED",
                "Private material capacity reached; operator action required",
            )

    def _save(self, draft):
        if self.store.document_bytes(draft["id"]) > 128 * 1024 * 1024:
            raise CapacityRefused(
                "INPUT_HISTORY_QUOTA_REACHED", "Input history quota reached; create a new draft"
            )
        return super()._save(draft)

    def get_draft_token_digest(self, draft_id):
        self.directory(draft_id)  # Validate the ID before looking up a scope.
        return self.store.draft_digest(draft_id)

    def _cleanup_expired_drafts(self):
        # PostgreSQL materials retain their references until explicit lifecycle
        # handling is implemented. Capacity exhaustion rejects new intake; it
        # must not silently shorten official material retention.
        return
