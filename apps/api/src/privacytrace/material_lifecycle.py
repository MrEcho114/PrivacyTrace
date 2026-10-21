"""Scope revocation, independent deletion replay and committed-reference garbage collection."""

import argparse
import json
import os
import re
import shutil
import stat
import time
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from .capacity import CapacityRefused
from .deletion_journal import fsync_directory
from .postgres_schema import deletions, documents, runner_materials, runtime_inputs, scopes, uploads


class MaterialLifecycle:
    MAX_BYTES = 4 * 1024 * 1024 * 1024
    MIN_FREE = 16 * 1024 * 1024

    def __init__(self, store, intake, journal=None):
        self.store, self.intake, self.journal = store, intake, journal

    def _tombstone(self, kind, scope_id, at):
        conn = self.store._local.connection
        previous = self.store._scope(scope_id)
        if previous and previous["kind"] != kind:
            raise ValueError("Deletion scope identity mismatch")
        conn.execute(
            insert(scopes)
            .values(
                instance_id=self.store.instance_id,
                scope_id=scope_id,
                kind=kind,
                token_digest=None,
                tombstone=True,
                created_at=at,
            )
            .on_conflict_do_update(
                index_elements=[scopes.c.instance_id, scopes.c.scope_id],
                set_={"token_digest": None, "tombstone": True},
            )
        )

    def _apply(self, intent):
        kind, scope_id = intent["kind"], intent["scope_id"]
        conn = self.store._local.connection
        if kind == "JOB":
            try:
                record = self.store._load(scope_id, allow_tombstone=True)
            except KeyError:
                self._tombstone(kind, scope_id, datetime.fromisoformat(intent["at"]))
            else:
                if not record.tombstone:
                    self.store.delete(scope_id)
        else:
            known = self.store._scope(scope_id)
            if known and known["kind"] != "DRAFT":
                raise ValueError("Deletion scope identity mismatch")
            linked = set(
                conn.scalars(
                    sa.select(runtime_inputs.c.job_id).where(
                        runtime_inputs.c.instance_id == self.store.instance_id,
                        runtime_inputs.c.draft_id == scope_id,
                    )
                )
            )
            # Old single-host PG jobs predate runtime_inputs. Their committed,
            # digest-checked draft still identifies their same capability scope.
            if known and not known["tombstone"]:
                try:
                    draft = self.intake._get(scope_id)
                except (KeyError, ValueError, OSError):
                    draft = None
                if draft:
                    for run in draft["jobs"]:
                        scope = self.store._scope(run["job_id"])
                        if (
                            scope
                            and scope["kind"] == "JOB"
                            and scope["token_digest"] == known["token_digest"]
                        ):
                            linked.add(run["job_id"])
            for job_id in sorted(linked):
                self.store.delete(job_id)
            self._tombstone(kind, scope_id, datetime.fromisoformat(intent["at"]))
        self.store._record_deletion(intent)

    def delete_draft(self, draft_id):
        self.intake.directory(draft_id)
        if self.journal is None:
            raise ValueError("Durable deletion journal required")
        with self.store._transaction():
            scope = self.store._scope(draft_id)
            if not scope or scope["kind"] != "DRAFT" or scope["tombstone"]:
                raise KeyError(draft_id)
            self._apply(self.journal.append("DRAFT", draft_id))
        result = self.collect()
        return {"deleted": True, "cleanup_pending": result["pending"] > 0}

    def replay(self):
        if self.journal is None:
            raise ValueError("Independent deletion journal required for recovery")
        with self.store._transaction() as conn:
            intents = self.journal.entries()
            indexed = {(entry["kind"], entry["scope_id"]): entry for entry in intents}
            saved = (
                conn.execute(
                    sa.select(deletions, scopes.c.kind.label("scope_kind"), scopes.c.tombstone)
                    .outerjoin(
                        scopes,
                        sa.and_(
                            deletions.c.instance_id == scopes.c.instance_id,
                            deletions.c.scope_id == scopes.c.scope_id,
                        ),
                    )
                    .where(deletions.c.instance_id == self.store.instance_id)
                )
                .mappings()
                .all()
            )
            applied = set()
            for row in saved:
                entry = indexed.get((row["kind"], row["scope_id"]))
                if not entry or row["sequence"] != entry["sequence"] or row["mac"] != entry["mac"]:
                    raise ValueError("Deletion journal is missing committed history")
                if not row["tombstone"] or row["scope_kind"] != row["kind"]:
                    raise ValueError("Deletion checkpoint has an inconsistent scope")
                applied.add((row["kind"], row["scope_id"]))
            for intent in intents:
                # Also reapply scopes after a backup rollback. No journal growth:
                # append() returns the existing intent for an already deleted ID.
                if (intent["kind"], intent["scope_id"]) not in applied:
                    self._apply(intent)
        return len(intents)

    def usage(self):
        total = 0
        for directory, directories, files in os.walk(self.intake.root, followlinks=False):
            parent = self.intake._safe(
                self.intake.root / os.path.relpath(directory, self.intake.root)
            )
            for name in directories:
                self.intake._safe(parent / name)
            for name in files:
                path = self.intake._safe(parent / name)
                info = path.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("Unexpected private material entry")
                total += info.st_size
                if total > self.MAX_BYTES:
                    raise CapacityRefused(
                        "MATERIAL_BUDGET_REACHED", "Private material capacity reached"
                    )
        return total

    def admit_upload(self, incoming):
        # The byte budget and the free space on the material volume are distinct
        # boundaries: an operator can raise the first, only the disk can fix the
        # second, and a refusal must say which one was hit.
        if self.usage() + incoming > self.MAX_BYTES:
            raise CapacityRefused(
                "MATERIAL_BUDGET_REACHED", "Private material capacity reached"
            )
        if shutil.disk_usage(self.intake.root).free < incoming + self.MIN_FREE:
            raise CapacityRefused(
                "MATERIAL_DISK_SPACE_REACHED", "Private material disk space exhausted"
            )

    def collect(self):
        result = {"objects": 0, "directories": 0, "temporary": 0, "pending": 0}
        # Phase one commits pointer removal before any file is unlinked. A real
        # COMMIT rejection cannot leave an existing pointer without its bytes.
        with self.store._transaction() as conn:
            dead = set(
                conn.scalars(
                    sa.select(scopes.c.scope_id).where(
                        scopes.c.instance_id == self.store.instance_id, scopes.c.tombstone.is_(True)
                    )
                )
            )
            rows = (
                conn.execute(
                    sa.select(runtime_inputs).where(
                        runtime_inputs.c.instance_id == self.store.instance_id
                    )
                )
                .mappings()
                .all()
            )
            keys = [
                row["document_key"]
                for row in rows
                if row["job_id"] in dead or row["draft_id"] in dead
            ]
            conn.execute(
                runtime_inputs.delete().where(
                    runtime_inputs.c.instance_id == self.store.instance_id,
                    sa.or_(runtime_inputs.c.job_id.in_(dead), runtime_inputs.c.draft_id.in_(dead)),
                )
            )
            conn.execute(
                documents.delete().where(
                    documents.c.instance_id == self.store.instance_id,
                    sa.or_(documents.c.scope_id.in_(dead), documents.c.document_key.in_(keys)),
                )
            )
            now = conn.scalar(sa.select(sa.func.clock_timestamp()))
            conn.execute(
                runner_materials.delete().where(
                    runner_materials.c.instance_id == self.store.instance_id,
                    sa.or_(
                        runner_materials.c.scope_id.in_(dead),
                        runner_materials.c.draft_id.in_(dead),
                        runner_materials.c.expires_at <= now,
                    ),
                )
            )
            conn.execute(
                uploads.delete().where(
                    uploads.c.instance_id == self.store.instance_id,
                    sa.or_(uploads.c.draft_id.in_(dead), uploads.c.expires_at <= now),
                )
            )
        # Phase two rechecks references while all honest pointer writers share
        # the same PG instance lock. It performs no DB mutations to roll back.
        with self.store._transaction() as conn:
            references = set(
                conn.scalars(
                    sa.select(documents.c.material_ref).where(
                        documents.c.instance_id == self.store.instance_id
                    )
                )
            )
            active_uploads = {
                row.draft_id: row.owner
                for row in conn.execute(
                    sa.select(uploads.c.draft_id, uploads.c.owner).where(
                        uploads.c.instance_id == self.store.instance_id
                    )
                )
            }
            known = {
                row.scope_id: row.tombstone
                for row in conn.execute(
                    sa.select(scopes.c.scope_id, scopes.c.tombstone).where(
                        scopes.c.instance_id == self.store.instance_id, scopes.c.kind == "DRAFT"
                    )
                )
            }
            for path in self.intake.materials.iterdir():
                self.intake._safe(path)
                if (
                    not re.fullmatch(r"[a-f0-9]{32}", path.name)
                    or not path.is_file()
                    or path.stat().st_nlink != 1
                ):
                    raise ValueError("Unexpected immutable material entry")
                if path.name not in references:
                    try:
                        path.unlink()
                        result["objects"] += 1
                    except OSError:
                        result["pending"] += 1
            for directory in self.intake.root.iterdir():
                self.intake._safe(directory)
                if not directory.is_dir() or not re.fullmatch(r"[a-f0-9]{32}", directory.name):
                    continue
                if known.get(directory.name, True):
                    try:
                        shutil.rmtree(directory)
                        result["directories"] += 1
                    except OSError:
                        result["pending"] += 1
                    continue
                owner = active_uploads.get(directory.name)
                published = directory / ".published-upload-owner"
                if owner is None and published.exists():
                    self.intake._safe(published)
                    if published.stat().st_size > 512:
                        raise ValueError("Unknown published upload marker")
                    proof = json.loads(published.read_bytes())
                    if (
                        set(proof) != {"instance_id", "draft_id", "owner"}
                        or proof["instance_id"] != self.store.instance_id
                        or proof["draft_id"] != directory.name
                        or not re.fullmatch(r"[a-f0-9]{32}", proof["owner"])
                    ):
                        raise ValueError("Unknown published upload marker")
                    draft = self.intake._get(directory.name)
                    if not draft["uploaded"] and not draft["jobs"]:
                        for path in (directory / "input.apk", directory / "packages"):
                            self.intake._safe(path)
                            if path.exists():
                                try:
                                    shutil.rmtree(path) if path.is_dir() else path.unlink()
                                    result["temporary"] += 1
                                except OSError:
                                    result["pending"] += 1
                for marker in directory.glob(".upload-owner-*.json"):
                    self.intake._safe(marker)
                    suffix = marker.name[len(".upload-owner-") : -len(".json")]
                    if not re.fullmatch(r"[a-f0-9]{32}", suffix):
                        raise ValueError("Unknown upload ownership marker")
                    if owner is not None and suffix == owner.hex:
                        continue
                    if marker.stat().st_size > 512 or json.loads(marker.read_bytes()) != {
                        "instance_id": self.store.instance_id,
                        "draft_id": directory.name,
                        "owner": suffix,
                    }:
                        raise ValueError("Unknown upload ownership marker")
                    for path in (
                        directory / ("upload.pending." + suffix),
                        directory / ("packages.pending." + suffix),
                    ):
                        self.intake._safe(path)
                        try:
                            if path.exists():
                                shutil.rmtree(path) if path.is_dir() else path.unlink()
                                result["temporary"] += 1
                        except OSError:
                            result["pending"] += 1
                    if not any(
                        (directory / (prefix + suffix)).exists()
                        for prefix in ("upload.pending.", "packages.pending.")
                    ):
                        marker.unlink()
            fsync_directory(self.intake.materials)
            fsync_directory(self.intake.root)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    from pathlib import Path

    from .postgres_intake import PostgresWebIntake
    from .storage_factory import create_store

    store = intake = None
    try:
        store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
        if not getattr(store, "uses_postgres", False):
            raise ValueError
        intake = PostgresWebIntake(store)
        while True:
            print(json.dumps(MaterialLifecycle(store, intake).collect()), flush=True)
            if args.once:
                return 0
            time.sleep(30)
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, KeyError):
        print('{"error":"MATERIAL_CLEANUP_UNAVAILABLE"}')
        return 1
    finally:
        if intake:
            intake.close()
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
