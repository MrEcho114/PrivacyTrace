"""Authenticated database/material snapshots; offline restore to an empty instance.

No pg_dump subprocess, executable archive entries, server secrets or transient
transfer permits are included. Keep the independent deletion journal and signing
key outside the rollback set. A snapshot cannot recover writes after its RPO.
"""

import argparse
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import struct
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa

from .deletion_journal import DeletionJournal, fsync_directory
from .job_store import JobStore
from .material_lifecycle import MaterialLifecycle
from .postgres_execution import ACTIVE, PostgresExecution
from .postgres_intake import PostgresWebIntake
from .postgres_schema import (
    REVISION,
    audit,
    deletions,
    documents,
    executions,
    jobs,
    outbox,
    runtime_inputs,
    scopes,
    uploads,
)
from .runner_protocol import MAX_INPUT, file_name
from .runtime_tls import json_value, private_file

MAGIC = b"PTBACKUP1\n"
MAX_MANIFEST = 256 * 1024 * 1024
MAX_FILES = 20000
TABLES = (scopes, jobs, audit, documents, outbox, executions, runtime_inputs, deletions)


def encoded(value):
    def scalar(item):
        if isinstance(item, (UUID, datetime)):
            return str(item)
        raise ValueError("Unsupported backup value")

    return json.dumps(
        value, default=scalar, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def safe_path(root, relative):
    if type(relative) is not str:
        raise ValueError("Invalid backup material path")
    parts = relative.split("/")
    if not (
        len(parts) == 3
        and parts[:2] == ["web", ".objects"]
        and re.fullmatch(r"[a-f0-9]{32}", parts[2])
    ):
        if (
            len(parts) not in {3, 4}
            or parts[0] != "web"
            or not re.fullmatch(r"[a-f0-9]{32}", parts[1])
        ):
            raise ValueError("Invalid backup material path")
        if len(parts) == 3 and parts[2] != "input.apk":
            raise ValueError("Invalid backup material path")
        if len(parts) == 4:
            if parts[2] != "packages":
                raise ValueError("Invalid backup material path")
            file_name(parts[3])
    path = root.joinpath(*parts)
    JobStore(root)._safe_root()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("Linked backup material rejected")
    return path


def fingerprint(path, *, linked_to=None):
    info = path.stat(follow_symlinks=False)
    owned_pair = False
    if linked_to is not None and info.st_nlink == 2:
        partner = linked_to.stat(follow_symlinks=False)
        owned_pair = (info.st_dev, info.st_ino) == (partner.st_dev, partner.st_ino)
    if (
        not stat.S_ISREG(info.st_mode)
        or not (info.st_nlink == 1 or owned_pair)
        or not 0 <= info.st_size <= MAX_INPUT
    ):
        raise ValueError("Unsafe backup material")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return {"size": info.st_size, "sha256": digest.hexdigest()}


def private_archive(source):
    path = Path(source).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("Linked backup rejected")
    info = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size > MaterialLifecycle.MAX_BYTES + MAX_MANIFEST + 64
        or (os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077))
    ):
        raise ValueError("Private bounded backup archive required")
    return path


class RuntimeBackup:
    def __init__(self, store, intake, journal, signing_key):
        if type(signing_key) is not bytes or len(signing_key) != 32 or journal is None:
            raise ValueError("Backup requires private signing key and independent deletion journal")
        self.store, self.intake, self.journal = store, intake, journal
        self._key = hmac.digest(signing_key, b"privacytrace.backup.key.v1", "sha256")
        self.lifecycle = MaterialLifecycle(store, intake, journal)
        self.store.deletion_journal = journal
        self._links = {}

    def _material(self, name):
        partner = self._links.get(name)
        return fingerprint(
            safe_path(self.store.root, name),
            linked_to=(safe_path(self.store.root, partner) if partner else None),
        )

    def _snapshot(self, conn):
        self._links = {}
        now = conn.scalar(sa.select(sa.func.clock_timestamp()))
        busy = conn.scalar(
            sa.select(sa.func.count())
            .select_from(executions)
            .where(
                executions.c.instance_id == self.store.instance_id, executions.c.state == "RUNNING"
            )
        ) or conn.scalar(
            sa.select(sa.func.count())
            .select_from(uploads)
            .where(uploads.c.instance_id == self.store.instance_id, uploads.c.expires_at > now)
        )
        if busy:
            raise ValueError("Quiesce running executions and uploads before backup")
        tables = {}
        for table in TABLES:
            query = sa.select(table).where(table.c.instance_id == self.store.instance_id)
            if table is documents:
                # model.json can contain a server API key. Operator configuration
                # is reprovisioned separately, never carried in a user-data snapshot.
                query = query.where(documents.c.scope_id.is_not(None))
            tables[table.name] = [dict(row) for row in conn.execute(query).mappings()]
        files = {}
        for row in tables[documents.name]:
            name = "web/.objects/" + row["material_ref"]
            files[name] = fingerprint(safe_path(self.store.root, name))
            if files[name] != {"size": row["byte_count"], "sha256": row["sha256"]}:
                raise ValueError("Backup document integrity mismatch")
        for draft_id in self.store.draft_ids():
            draft = self.intake._get(draft_id)
            if not draft["uploaded"]:
                continue
            name = f"web/{draft_id}/input.apk"
            if draft.get("package_set"):
                from .package_set import PackageSet

                package = PackageSet.model_validate(draft["package_set"])
                base = f"web/{draft_id}/packages/{file_name(package.base.file_name)}"
                # #70 publishes exactly this owned base/input hardlink pair.
                # Arbitrary hardlinks, extra links and cross-draft pairs remain
                # rejected; restore may safely materialize two independent copies.
                self._links.update({name: base, base: name})
            files[name] = self._material(name)
            if files[name]["sha256"] != draft["apk_sha256"]:
                raise ValueError("Backup APK integrity mismatch")
            directory = self.intake.directory(draft_id) / "packages"
            if directory.exists():
                self.intake._safe(directory)
                for path in directory.iterdir():
                    name = f"web/{draft_id}/packages/{file_name(path.name)}"
                    files[name] = self._material(name)
        if (
            len(files) > MAX_FILES
            or sum(x["size"] for x in files.values()) > self.lifecycle.MAX_BYTES
        ):
            raise ValueError("Backup exceeds instance capacity")
        history = self.journal.entries()
        return {
            "version": 1,
            "schema": REVISION,
            "instance_id": self.store.instance_id,
            "created_at": now.isoformat(),
            "tables": tables,
            "files": dict(sorted(files.items())),
            "deletion_checkpoint": [len(history), history[-1]["mac"] if history else "0" * 64],
        }

    def backup(self, output):
        output = Path(output).absolute()
        # Never put backup bytes within material / deletion roots (GC and RPO).
        for root in (self.store.root, self.journal.root):
            if output.is_relative_to(root):
                raise ValueError("Backup must be outside instance and deletion roots")
        JobStore(output.parent)._safe_root()
        if not output.parent.is_dir() or output.exists() or output.is_symlink():
            raise ValueError("New private backup destination required")
        self.lifecycle.replay()
        self.lifecycle.collect()
        temporary = output.with_name("." + output.name + "." + uuid4().hex)
        try:
            with self.store._transaction() as conn:
                value = self._snapshot(conn)
                raw = encoded(value)
                if len(raw) > MAX_MANIFEST:
                    raise ValueError("Backup manifest capacity reached")
                signature = hmac.digest(self._key, raw, "sha256")
                fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(MAGIC + struct.pack("!Q", len(raw)) + raw + signature)
                    for name, expected in value["files"].items():
                        path = safe_path(self.store.root, name)
                        if self._material(name) != expected:
                            raise ValueError("Material changed during backup")
                        with path.open("rb") as source:
                            shutil.copyfileobj(source, handle, 1024 * 1024)
                    handle.flush()
                    os.fsync(handle.fileno())
            # No overwrite, including racing backups. The file was fully flushed.
            os.link(temporary, output)
            temporary.unlink()
            fsync_directory(output.parent)
            return {
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "files": len(value["files"]),
            }
        finally:
            temporary.unlink(missing_ok=True)

    def _read(self, handle):
        if handle.read(len(MAGIC)) != MAGIC:
            raise ValueError("Unsupported backup format")
        size = handle.read(8)
        if len(size) != 8 or not 0 < (length := struct.unpack("!Q", size)[0]) <= MAX_MANIFEST:
            raise ValueError("Invalid backup manifest size")
        raw, signature = handle.read(length), handle.read(32)
        if not hmac.compare_digest(hmac.digest(self._key, raw, "sha256"), signature):
            raise ValueError("Backup authentication rejected")
        value = json_value(raw)
        if (
            set(value)
            != {
                "version",
                "schema",
                "instance_id",
                "created_at",
                "tables",
                "files",
                "deletion_checkpoint",
            }
            or type(value["version"]) is not int
            or value["version"] != 1
            or value["schema"] != REVISION
            or value["instance_id"] != self.store.instance_id
            or set(value["tables"]) != {t.name for t in TABLES}
            or type(value["files"]) is not dict
            or len(value["files"]) > MAX_FILES
            or datetime.fromisoformat(value["created_at"]).tzinfo is None
        ):
            raise ValueError("Backup manifest identity rejected")
        total = 0
        for name, entry in value["files"].items():
            safe_path(self.store.root, name)
            if (
                set(entry) != {"size", "sha256"}
                or type(entry["size"]) is not int
                or not 0 <= entry["size"] <= MAX_INPUT
                or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
            ):
                raise ValueError("Invalid backup material metadata")
            total += entry["size"]
        if total > self.lifecycle.MAX_BYTES:
            raise ValueError("Backup exceeds instance capacity")
        for table in TABLES:
            if type(value["tables"][table.name]) is not list:
                raise ValueError("Invalid backup table")
            for row in value["tables"][table.name]:
                if set(row) != set(table.c.keys()) or row["instance_id"] != self.store.instance_id:
                    raise ValueError("Invalid backup row scope")
                for column in table.c:
                    if row[column.name] is not None:
                        if isinstance(column.type, sa.DateTime):
                            row[column.name] = datetime.fromisoformat(row[column.name])
                            if row[column.name].tzinfo is None:
                                raise ValueError("Invalid backup timestamp")
                        elif isinstance(column.type, sa.UUID):
                            row[column.name] = UUID(row[column.name])
        for row in value["tables"][documents.name]:
            key = row["document_key"]
            if (
                not row["scope_id"]
                or not re.fullmatch(r"[a-f0-9]{32}/[A-Za-z0-9_.-]+", key)
                or key.split("/")[0] != row["scope_id"]
                or key.endswith("/..")
                or key.endswith("/.")
                or value["files"].get("web/.objects/" + row["material_ref"])
                != {"size": row["byte_count"], "sha256": row["sha256"]}
            ):
                raise ValueError("Backup document reference rejected")
        self._checkpoint(value)
        return value, signature.hex()

    def _checkpoint(self, value):
        history = self.journal.entries()
        checkpoint = value["deletion_checkpoint"]
        if (
            type(checkpoint) is not list
            or len(checkpoint) != 2
            or type(checkpoint[0]) is not int
            or not 0 <= checkpoint[0] <= len(history)
            or checkpoint[1] != (history[checkpoint[0] - 1]["mac"] if checkpoint[0] else "0" * 64)
        ):
            raise ValueError("Latest independent deletion journal required")

    def _marker(self, signature, resume):
        path = self.store.root / ".restore-in-progress"
        if path.exists() or path.is_symlink():
            if not resume:
                raise ValueError("Interrupted restore requires explicit resume")
            proof = json_value(private_file(path, secret=True).read_bytes())
            mac = proof.pop("mac")
            if (
                set(proof) != {"instance_id", "manifest_mac", "restore_id"}
                or proof["instance_id"] != self.store.instance_id
                or proof["manifest_mac"] != signature
                or not hmac.compare_digest(
                    mac, hmac.digest(self._key, encoded(proof), "sha256").hex()
                )
            ):
                raise ValueError("Restore ownership rejected")
            UUID(proof["restore_id"])
            return proof
        if resume:
            raise ValueError("No interrupted restore to resume")
        if any(self.store.root.iterdir()):
            # PostgresWebIntake creates an empty web/.objects. Anything else is
            # operator data; never overwrite or recursively remove it.
            allowed = {self.store.root / "web", self.intake.materials}
            if any(p not in allowed for p in self.store.root.rglob("*")):
                raise ValueError("Restore requires an empty material root")
        proof = {
            "instance_id": self.store.instance_id,
            "manifest_mac": signature,
            "restore_id": str(uuid4()),
        }
        signed = {**proof, "mac": hmac.digest(self._key, encoded(proof), "sha256").hex()}
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded(signed))
            handle.flush()
            os.fsync(handle.fileno())
        fsync_directory(self.store.root)
        return proof

    def _cleanup_stages(self, proof, value):
        prefix = ".restore-stage-" + proof["restore_id"] + "-"
        signed = {**proof, "mac": hmac.digest(self._key, encoded(proof), "sha256").hex()}
        for directory in self.store.root.parent.glob(prefix + "*"):
            if (
                directory.resolve() != directory.absolute()
                or directory.parent.resolve() != self.store.root.parent.resolve()
                or not re.fullmatch(r"[a-f0-9]{32}", directory.name[len(prefix) :])
                or not directory.is_dir()
            ):
                raise ValueError("Unrecognized restore staging ownership")
            if not any(directory.iterdir()):
                directory.rmdir()
                continue
            owner = directory / ".stage-owner"
            if not owner.is_file() or private_file(owner, secret=True).read_bytes() != encoded(
                signed
            ):
                raise ValueError("Unrecognized restore staging ownership")
            JobStore(directory)._safe_root()
            allowed_directories = {"web", "web/.objects"}
            for name in value["files"]:
                allowed_directories.update(
                    p.as_posix() for p in Path(name).parents if p.as_posix() != "."
                )
            for path in directory.rglob("*"):
                if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                    raise ValueError("Linked restore staging rejected")
                if not (path.is_dir() or path.is_file()):
                    raise ValueError("Unknown restore staging entry")
                if (
                    path.is_dir()
                    and path.relative_to(directory).as_posix() not in allowed_directories
                ):
                    raise ValueError("Unknown restore staging directory")
                if path.is_file() and path != owner:
                    name = path.relative_to(directory).as_posix()
                    safe_path(directory, name)
                    if name not in value["files"] or path.stat().st_nlink != 1:
                        raise ValueError("Unknown restore staging material")
            # Absolute target and every entry were validated above. The signed
            # marker proves this operation owns this particular temporary tree.
            shutil.rmtree(directory)

    def _check_destination(self, value):
        files = set(value["files"]) | {".restore-in-progress"}
        files.update("web/" + row["document_key"] for row in value["tables"][documents.name])
        directories = {"web", "web/.objects"}
        for name in files:
            directories.update(p.as_posix() for p in Path(name).parents if p.as_posix() != ".")
        for path in self.store.root.rglob("*"):
            self.intake._safe(path)
            name = path.relative_to(self.store.root).as_posix()
            if not ((path.is_dir() and name in directories) or (path.is_file() and name in files)):
                raise ValueError("Unknown restore destination data; preserve for inspection")

    def restore(self, source, *, resume=False):
        source = private_archive(source)
        previous = self.store._allow_restore
        self.store._allow_restore = True
        stage = None
        try:
            with source.open("rb") as handle:
                value, signature = self._read(handle)
                # Establish the offline gate under the same instance lock as
                # ordinary readers/writers, before publishing any file or row.
                with self.store._transaction() as conn:
                    count = conn.scalar(
                        sa.select(sa.func.count())
                        .select_from(scopes)
                        .where(scopes.c.instance_id == self.store.instance_id)
                    )
                    if count and not (self.store.root / ".restore-in-progress").exists():
                        raise ValueError("Restore requires an empty database instance")
                    proof = self._marker(signature, resume)
                    self._check_destination(value)
                    self._cleanup_stages(proof, value)
                stage = self.store.root.parent / (".restore-stage-" + proof["restore_id"])
                stage = stage.with_name(stage.name + "-" + uuid4().hex)
                stage.mkdir(mode=0o700)
                signed = {**proof, "mac": hmac.digest(self._key, encoded(proof), "sha256").hex()}
                fd = os.open(stage / ".stage-owner", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "wb") as owner:
                    owner.write(encoded(signed))
                    owner.flush()
                    os.fsync(owner.fileno())
                fsync_directory(stage)
                for name, expected in value["files"].items():
                    target = safe_path(stage, name)
                    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                    digest, remaining = hashlib.sha256(), expected["size"]
                    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(fd, "wb") as output:
                        while remaining:
                            block = handle.read(min(remaining, 1024 * 1024))
                            if not block:
                                raise ValueError("Truncated backup material")
                            digest.update(block)
                            remaining -= len(block)
                            output.write(block)
                        output.flush()
                        os.fsync(output.fileno())
                    if digest.hexdigest() != expected["sha256"]:
                        raise ValueError("Backup material integrity rejected")
                if handle.read(1):
                    raise ValueError("Unexpected backup trailing bytes")
            with self.store._transaction() as conn:
                self._checkpoint(value)
                done = conn.scalar(
                    sa.select(audit.c.event_id).where(
                        audit.c.instance_id == self.store.instance_id,
                        audit.c.event_id == UUID(proof["restore_id"]),
                        audit.c.action == "RESTORE_COMMITTED",
                    )
                )
                if not done:
                    for table in TABLES:
                        if conn.scalar(
                            sa.select(sa.func.count())
                            .select_from(table)
                            .where(table.c.instance_id == self.store.instance_id)
                        ):
                            raise ValueError("Unrecognized nonempty restore destination")
                    for name, expected in value["files"].items():
                        target = safe_path(self.store.root, name)
                        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        if target.exists():
                            if fingerprint(target) != expected:
                                raise ValueError("Restore destination material changed")
                        else:
                            # Same-volume atomic rename; the offline gate and
                            # instance lock exclude other authorized publishers.
                            staged = safe_path(stage, name)
                            os.rename(staged, target)
                        fsync_directory(target.parent)
                    for table in TABLES:
                        rows = value["tables"][table.name]
                        for offset in range(0, len(rows), 100):
                            conn.execute(table.insert(), rows[offset : offset + 100])
                    for row in value["tables"][jobs.name]:
                        self.store._load(row["job_id"], allow_tombstone=True)
                    execution = PostgresExecution(self.store)
                    for row in value["tables"][executions.name]:
                        record = self.store._load(row["job_id"], allow_tombstone=True)
                        if not record.tombstone and record.job.state in ACTIVE:
                            execution._retry(
                                conn, row, record, "WORKER_LOST", execution._now(conn), 0
                            )
                    self.lifecycle.replay()  # nested: revocations precede COMMIT
                    if value["tables"][scopes.name]:
                        conn.execute(
                            audit.insert().values(
                                instance_id=self.store.instance_id,
                                event_id=UUID(proof["restore_id"]),
                                scope_id=value["tables"][scopes.name][0]["scope_id"],
                                action="RESTORE_COMMITTED",
                                created_at=datetime.now(timezone.utc),
                            )
                        )
            # Reconstruct only logical zero-byte markers, never authority bytes.
            for row in value["tables"][documents.name]:
                marker = self.intake._safe(self.intake.root / row["document_key"])
                marker.parent.mkdir(mode=0o700, exist_ok=True)
                marker.touch(mode=0o600, exist_ok=True)
                fsync_directory(marker.parent)
            self.lifecycle.replay()
            result = self.lifecycle.collect()
            if result["pending"]:
                raise ValueError("Restore cleanup incomplete; resume required")
            shutil.rmtree(stage)
            stage = None
            (self.store.root / ".restore-in-progress").unlink()
            fsync_directory(self.store.root)
            return {"restored": True, "deletions": len(self.journal.entries())}
        finally:
            self.store._allow_restore = previous
            if stage is not None:
                # Only this invocation's freshly created staging directory.
                shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    store = intake = None
    try:
        from .postgres_store import PostgresJobStore

        if os.environ.get("PRIVACYTRACE_STORAGE") != "postgres":
            raise ValueError
        store = PostgresJobStore(
            os.environ["PRIVACYTRACE_DATABASE_URL"],
            os.environ["PRIVACYTRACE_INSTANCE_ID"],
            Path(os.environ["PRIVACYTRACE_STORE_ROOT"]),
            recovery=args.operation == "restore",
        )
        intake = PostgresWebIntake(store)
        key = private_file(os.environ["PRIVACYTRACE_MATERIAL_KEY_FILE"], secret=True).read_bytes()
        journal = DeletionJournal.for_store(store, key)
        runtime = RuntimeBackup(store, intake, journal, key)
        result = (
            runtime.backup(args.path)
            if args.operation == "backup"
            else runtime.restore(args.path, resume=args.resume)
        )
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print('{"error":"BACKUP_RECOVERY_REJECTED"}')
        return 1
    finally:
        if intake:
            intake.close()
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
