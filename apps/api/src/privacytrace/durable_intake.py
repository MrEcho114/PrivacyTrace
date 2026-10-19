"""Reuse WebIntake semantics; atomically register immutable input and outbox only."""

import json
import os
from concurrent.futures import Future

import sqlalchemy as sa
from pydantic_core import to_json

from .postgres_execution import PostgresExecution
from .postgres_intake import PostgresWebIntake
from .postgres_outbox import PostgresOutbox
from .postgres_schema import executions, runtime_inputs
from .runner_client import RunnerClient
from .web_intake import inspect_uploaded_package


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
        except Exception:
            self.executor.shutdown(wait=False)
            raise

    def start_service(self):
        # API restarts own no execution lease and must not fail other workers'
        # jobs or remove another API process's in-flight upload.
        return

    def close(self):
        self.executor.shutdown(wait=True)

    def _inspect_package(self, path, *, timeout=120):
        return inspect_uploaded_package(
            path, timeout=timeout, inspector=self.runner.inspect_metadata
        )

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

    def execute(self, lease):
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
            self._event(snapshot["draft"]["id"], lease.job_id, execution["state"])
