"""Reuse WebIntake semantics; atomically register immutable input and outbox only."""

import json
import os
from concurrent.futures import Future
from contextvars import ContextVar
from datetime import timedelta
from uuid import uuid4

import sqlalchemy as sa
from pydantic_core import to_json

from .deletion_journal import DeletionJournal, fsync_directory
from .material_lifecycle import MaterialLifecycle
from .postgres_execution import ACTIVE, PostgresExecution
from .postgres_intake import PostgresWebIntake
from .postgres_outbox import PostgresOutbox
from .postgres_schema import executions, jobs, runtime_inputs, uploads
from .runner_client import RunnerClient
from .web_intake import inspect_uploaded_package, write_private

UPLOAD_OWNER = ContextVar("privacytrace_upload_owner", default=None)


def ensure_control_plane():
    # Refuse even a stopped daemon's accessible socket: it may return later.
    # The control plane must be provisioned without this privileged capability.
    for name in ("/var/run/docker.sock", "/run/docker.sock"):
        if os.path.exists(name) and os.access(name, os.R_OK | os.W_OK):
            raise ValueError("Durable control plane must not have Docker socket access")
    if any(
        os.environ.get(name)
        for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH")
    ):
        raise ValueError("Docker endpoint configuration is forbidden on the control plane")


class DurableWebIntake(PostgresWebIntake):
    MAX_ACTIVE_JOBS = 4

    def __init__(self, store, runner=None):
        super().__init__(store)
        try:
            self.runner = runner if runner is not None else RunnerClient.from_env(store)
            self._claim_runtime_mode()
            journal = (
                DeletionJournal.for_store(store, self.runner.materials._key)
                if hasattr(self.runner, "materials")
                else store.deletion_journal
            )
            self.lifecycle = MaterialLifecycle(store, self, journal)
            if journal is not None:
                store.deletion_journal = journal
                self.lifecycle.replay()
            store.cleanup_after_delete = self.lifecycle.collect
        except Exception:
            self.executor.shutdown(wait=False)
            raise

    def _claim_runtime_mode(self):
        # Durable APIs share this root. A permanent mode marker prevents a
        # mistakenly restarted legacy process from failing their active jobs or
        # sweeping uploads. Establish it only while the old exclusive service
        # owner is stopped, using its actual lock rather than a stale PID file.
        with self.store._transaction():
            fd = os.open(self._safe(self.root / "service.lock"), os.O_CREAT | os.O_RDWR, 0o600)
            try:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise ValueError(
                        "Stop the legacy intake owner before durable cutover"
                    ) from None
                path = self._safe(self.root / "durable-runtime.json")
                expected = {"version": 1, "instance_id": self.store.instance_id}
                if path.exists():
                    if path.stat().st_size > 512 or json.loads(path.read_bytes()) != expected:
                        raise ValueError("Durable runtime ownership marker rejected")
                else:
                    marker = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(marker, "wb") as handle:
                        handle.write(json.dumps(expected).encode())
                        handle.flush()
                        os.fsync(handle.fileno())
                    fsync_directory(self.root)
                unmanaged = self.store._local.connection.scalars(
                    sa.select(jobs.c.job_id).where(
                        jobs.c.instance_id == self.store.instance_id,
                        jobs.c.record["job"]["state"].as_string().in_(ACTIVE),
                        ~sa.exists(
                            sa.select(1).where(
                                executions.c.instance_id == jobs.c.instance_id,
                                executions.c.job_id == jobs.c.job_id,
                            )
                        ),
                    )
                ).all()
                for job_id in unmanaged:
                    record = self.store._load(job_id, allow_tombstone=True)
                    if record.tombstone:
                        continue
                    record.job.state = "FAILED"
                    record.job.error = json.dumps(
                        {
                            "code": "SERVICE_INTERRUPTED",
                            "message": "Legacy execution stopped; retry creates a new job",
                        }
                    )
                    self.store._write(record)
            finally:
                os.close(fd)

    def start_service(self):
        # API restarts own no execution lease and must not fail other workers'
        # jobs or remove another API process's in-flight upload.
        self.lifecycle.collect()

    def close(self):
        self.executor.shutdown(wait=True)

    def _inspect_package(self, path, *, timeout=120):
        return inspect_uploaded_package(
            path, timeout=timeout, inspector=self.runner.inspect_metadata
        )

    def delete_draft(self, draft_id):
        return self.lifecycle.delete_draft(draft_id)

    async def _upload_reserved(self, draft_id, request, expect_package_set=False):
        owner = uuid4()
        directory = self.directory(draft_id)
        marker = directory / (".upload-owner-" + owner.hex + ".json")
        with self.store._transaction() as conn:
            self.store.draft_digest(draft_id)
            now = PostgresExecution._now(conn)
            existing = (
                conn.execute(
                    sa.select(uploads).where(
                        uploads.c.instance_id == self.store.instance_id,
                        uploads.c.draft_id == draft_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing and existing["expires_at"] > now:
                raise ValueError("Draft already has an active upload")
            conn.execute(
                uploads.delete().where(
                    uploads.c.instance_id == self.store.instance_id, uploads.c.draft_id == draft_id
                )
            )
            reserved = conn.scalar(
                sa.select(sa.func.count())
                .select_from(uploads)
                .where(uploads.c.instance_id == self.store.instance_id, uploads.c.expires_at > now)
            )
            self.lifecycle.admit_upload((reserved + 1) * (2 * 150 * 1024 * 1024 + 8 * 1024 * 1024))
            write_private(
                marker,
                {"instance_id": self.store.instance_id, "draft_id": draft_id, "owner": owner.hex},
            )
            fsync_directory(directory)
            conn.execute(
                uploads.insert().values(
                    instance_id=self.store.instance_id,
                    draft_id=draft_id,
                    owner=owner,
                    expires_at=now + timedelta(seconds=900),
                )
            )
        context = UPLOAD_OWNER.set(owner)
        try:
            return await super()._upload_reserved(draft_id, request, expect_package_set)
        finally:
            UPLOAD_OWNER.reset(context)
            with self.store._transaction() as conn:
                conn.execute(
                    uploads.delete().where(
                        uploads.c.instance_id == self.store.instance_id,
                        uploads.c.draft_id == draft_id,
                        uploads.c.owner == owner,
                    )
                )
            if not any(
                (directory / (prefix + owner.hex)).exists()
                for prefix in ("upload.pending.", "packages.pending.")
            ):
                marker.unlink(missing_ok=True)

    def _upload_paths(self, directory):
        owner = UPLOAD_OWNER.get()
        if owner is None:
            raise ValueError("Missing upload reservation")
        return (
            self._safe(directory / ("upload.pending." + owner.hex)),
            self._safe(directory / ("packages.pending." + owner.hex)),
        )

    def _before_publish_upload(self, draft_id):
        owner = UPLOAD_OWNER.get()
        conn = self.store._local.connection
        row = (
            conn.execute(
                sa.select(uploads).where(
                    uploads.c.instance_id == self.store.instance_id, uploads.c.draft_id == draft_id
                )
            )
            .mappings()
            .one_or_none()
        )
        self.store.draft_digest(draft_id)
        if (
            owner is None
            or not row
            or row["owner"] != owner
            or row["expires_at"] <= PostgresExecution._now(conn)
        ):
            raise ValueError("Upload reservation expired or revoked")

    def _after_publish_upload(self, directory):
        owner = UPLOAD_OWNER.get()
        write_private(
            directory / ".published-upload-owner",
            {"instance_id": self.store.instance_id, "draft_id": directory.name, "owner": owner.hex},
        )
        if (directory / "packages").exists():
            fsync_directory(directory / "packages")
        fsync_directory(directory)

    def _may_remove_published(self, draft_id):
        owner = UPLOAD_OWNER.get()
        marker = self.directory(draft_id) / ".published-upload-owner"
        if owner is None or not marker.is_file() or marker.stat().st_size > 512:
            return False
        if json.loads(marker.read_bytes()) != {
            "instance_id": self.store.instance_id,
            "draft_id": draft_id,
            "owner": owner.hex,
        }:
            return False
        return super()._may_remove_published(draft_id)

    def _save(self, draft):
        with self.store._transaction():
            if UPLOAD_OWNER.get() is not None:
                self._before_publish_upload(draft["id"])
            result = super()._save(draft)
            if UPLOAD_OWNER.get() is not None:
                self._before_publish_upload(draft["id"])
            return result

    def start(self, draft_id, payload, *, retry_of=None):
        reservation, job = Future(), None
        try:
            with self.store._transaction() as conn:
                job, draft, captures = self._register_start(
                    draft_id, payload, reservation, retry_of=retry_of
                )
                if draft is None:
                    return job
                active = conn.scalar(
                    sa.select(sa.func.count())
                    .select_from(executions)
                    .where(
                        executions.c.instance_id == self.store.instance_id,
                        executions.c.state.in_(["READY", "RUNNING", "RETRY"]),
                    )
                )
                if active >= self.MAX_ACTIVE_JOBS:
                    raise ValueError("Durable task admission capacity reached")
                snapshot = json.loads(
                    to_json({"version": 1, "job_id": job.id, "draft": draft, "captures": captures})
                )
                document = self.directory(draft_id) / ("run-" + job.id + ".json")
                self._write_private(document, snapshot)
                conn.execute(
                    runtime_inputs.insert().values(
                        instance_id=self.store.instance_id,
                        job_id=job.id,
                        draft_id=draft_id,
                        document_key=self._key(document),
                    )
                )
                PostgresOutbox(self.store).enqueue(job.id)
            return job
        finally:
            reservation.cancel()
            if job is not None:
                self.futures.pop(job.id, None)

    def input_snapshot(self, job_id):
        with self.store._transaction() as conn:
            self.store._load(job_id)
            row = (
                conn.execute(
                    sa.select(runtime_inputs).where(
                        runtime_inputs.c.instance_id == self.store.instance_id,
                        runtime_inputs.c.job_id == job_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ValueError("Retained runtime input unavailable")
            document = self.directory(row["draft_id"]) / ("run-" + job_id + ".json")
            if self._key(document) != row["document_key"]:
                raise ValueError("Runtime input identity mismatch")
            snapshot = self._read(document)
            if (
                set(snapshot) != {"version", "job_id", "draft", "captures"}
                or snapshot["version"] != 1
                or snapshot["job_id"] != job_id
                or snapshot["draft"]["id"] != row["draft_id"]
            ):
                raise ValueError("Runtime input identity mismatch")
            return snapshot

    def execute(self, lease, *, on_fenced_stage=None):
        execution = PostgresExecution(self.store)
        execution.checkpoint(lease)
        snapshot = self.input_snapshot(lease.job_id)
        draft, captures = snapshot["draft"], snapshot["captures"]
        job = self.store.get(lease.job_id)
        job.error = None

        def event(stage):
            with execution.fenced_store(lease)._transaction() as conn:
                execution._guard(conn, lease)
                self._event(draft["id"], job.id, stage)
            # Never acknowledge a stage until its fenced DB transaction commits.
            if on_fenced_stage is not None:
                on_fenced_stage()

        return self._execute(
            draft,
            job,
            captures,
            job_store=execution.fenced_store(lease),
            scanner=self.runner.scanner(draft, lease),
            on_stage=event,
        )

    def terminal_event(self, lease):
        with self.store._transaction():
            execution = PostgresExecution(self.store).status(lease.job_id)
            if execution["fence"] != lease.fence or execution["state"] not in {
                "SUCCEEDED",
                "FAILED",
            }:
                return
            snapshot = self.input_snapshot(lease.job_id)
            draft_id = snapshot["draft"]["id"]
            current = self._get(draft_id)
            run = next(row for row in current["jobs"] if row["job_id"] == lease.job_id)
            if run["events"] and run["events"][-1]["state"] == execution["state"]:
                return
            self._event(draft_id, lease.job_id, execution["state"])
