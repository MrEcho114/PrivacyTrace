"""Short PostgreSQL execution transactions; scans and network I/O stay outside.

Redis delivery is at least once. Only a current lease can mutate the original
pipeline's job/report. Internal recovery retains its job ID and finite budgets;
an explicit user retry continues to create a separate job via the existing API.
"""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from .postgres_outbox import MAX_ATTEMPTS as MAX_DELIVERIES
from .postgres_outbox import PostgresOutbox, _bounded, decode_message
from .postgres_schema import executions, outbox
from .postgres_store import PostgresOperationUnavailable

MAX_EXECUTIONS = 3
MAX_EXECUTION_SECONDS = 300
REDRIVE_SECONDS = 300
ACTIVE = frozenset(
    {"QUEUED", "INTAKE", "STATIC_ANALYSIS", "POLICY_PARSING", "EVALUATING", "REPORTING"}
)
RETRY_CODES = frozenset({"RUNNER_UNAVAILABLE", "WORKER_LOST"})


class LeaseLost(RuntimeError):
    """Escapes the pipeline's input-error handler; a stale worker must stop."""


@dataclass(frozen=True)
class ExecutionLease:
    instance_id: str
    job_id: str
    event_id: UUID
    owner: UUID
    fence: int
    attempt: int
    leased_until: datetime


class PostgresExecution:
    def __init__(self, store):
        self.store = store
        self.events = PostgresOutbox(store)

    def _where(self, job_id):
        return sa.and_(
            executions.c.instance_id == self.store.instance_id, executions.c.job_id == job_id
        )

    def _row(self, conn, job_id):
        return (
            conn.execute(sa.select(executions).where(self._where(job_id))).mappings().one_or_none()
        )

    def status(self, job_id):
        self.store._path(job_id)
        with self.store._transaction() as conn:
            row = self._row(conn, job_id)
            if row is None:
                raise KeyError("Execution unavailable")
            return dict(row)

    @staticmethod
    def _now(conn):
        return conn.scalar(sa.select(sa.func.clock_timestamp()))

    def _guard(self, conn, lease):
        if not isinstance(lease, ExecutionLease) or lease.instance_id != self.store.instance_id:
            raise LeaseLost("Execution lease unavailable")
        row = self._row(conn, lease.job_id)
        now = self._now(conn)
        try:
            record = self.store._load(lease.job_id)
        except KeyError:
            raise LeaseLost("Execution lease unavailable") from None
        if (
            row is None
            or row["state"] != "RUNNING"
            or row["owner"] != lease.owner
            or row["fence"] != lease.fence
            or row["attempt"] != lease.attempt
            or row["event_id"] != lease.event_id
            or row["leased_until"] <= now
            or row["started_at"] + timedelta(seconds=MAX_EXECUTION_SECONDS) <= now
            or record.job.state not in ACTIVE
            or record.bundle is not None
        ):
            raise LeaseLost("Execution lease unavailable")
        return row, record, now

    def checkpoint(self, lease):
        with self.store._transaction() as conn:
            self._guard(conn, lease)

    def acquire(self, message, *, lease_seconds=60):
        _bounded(lease_seconds, 5, 300)
        self.events._standalone()
        message = decode_message(message)
        if message["instance_id"] != self.store.instance_id:
            raise ValueError("Execution instance does not match the event")
        with self.store._transaction() as conn:
            try:
                event = self.events.get(message["event_id"])
                record = self.store._load(message["job_id"])
            except KeyError:
                return None
            if (
                event.message != message
                or event.attempts < 1
                or event.state == "DISCARDED"
                or record.job.state not in ACTIVE
                or record.bundle is not None
            ):
                return None
            now = self._now(conn)
            self._initialize(conn, event, now)
            row = self._row(conn, event.job_id)
            if (
                row["state"] not in {"READY", "RETRY"}
                or row["available_at"] > now
                or row["attempt"] >= MAX_EXECUTIONS
                or row["event_id"] != event.event_id
            ):
                return None
            owner = uuid4()
            until = now + timedelta(seconds=lease_seconds)
            conn.execute(
                executions.update()
                .where(self._where(event.job_id))
                .values(
                    state="RUNNING",
                    attempt=row["attempt"] + 1,
                    fence=row["fence"] + 1,
                    owner=owner,
                    started_at=now,
                    leased_until=until,
                    last_error_code=None,
                )
            )
            self.store._audit(event.job_id, "EXECUTION_ACQUIRED")
            return ExecutionLease(
                self.store.instance_id,
                event.job_id,
                event.event_id,
                owner,
                row["fence"] + 1,
                row["attempt"] + 1,
                until,
            )

    def heartbeat(self, lease, *, lease_seconds=60):
        _bounded(lease_seconds, 5, 300)
        self.events._standalone()
        with self.store._transaction() as conn:
            row, _, now = self._guard(conn, lease)
            until = min(
                now + timedelta(seconds=lease_seconds),
                row["started_at"] + timedelta(seconds=MAX_EXECUTION_SECONDS),
            )
            conn.execute(
                executions.update().where(self._where(lease.job_id)).values(leased_until=until)
            )
            return ExecutionLease(
                lease.instance_id,
                lease.job_id,
                lease.event_id,
                lease.owner,
                lease.fence,
                lease.attempt,
                until,
            )

    def fenced_store(self, lease):
        if not isinstance(lease, ExecutionLease) or lease.instance_id != self.store.instance_id:
            raise LeaseLost("Execution lease unavailable")
        return FencedJobStore(self, lease)

    def _initialize(self, conn, event, now):
        # Handles pre-0080_03 events without an unsafe all-instance RLS bypass.
        conn.execute(
            insert(executions)
            .values(
                instance_id=self.store.instance_id,
                job_id=event.job_id,
                event_id=event.event_id,
                state="READY",
                attempt=0,
                fence=0,
                available_at=now,
            )
            .on_conflict_do_nothing()
        )

    def _terminal_failure(self, conn, row, record, code):
        record.job.state = "FAILED"
        record.job.error = json.dumps({"code": code, "message": "Runtime execution failed"})
        self.store._write(record)
        conn.execute(
            executions.update()
            .where(self._where(row["job_id"]))
            .values(
                state="FAILED",
                fence=row["fence"] + 1,
                owner=None,
                leased_until=None,
                started_at=None,
                last_error_code=code,
            )
        )
        self.store._audit(row["job_id"], "EXECUTION_FAILED")

    def _retry(self, conn, row, record, code, now, delay):
        event = self.events.get(str(row["event_id"]))
        if row["attempt"] >= MAX_EXECUTIONS or event.attempts >= MAX_DELIVERIES:
            reason = code if row["attempt"] >= MAX_EXECUTIONS else "DELIVERY_EXHAUSTED"
            self._terminal_failure(conn, row, record, reason)
            return False
        due = now + timedelta(seconds=delay)
        # Invalidate the old owner before rearming its same event. Attempts and
        # publication budgets never reset, including after broker loss.
        conn.execute(
            executions.update()
            .where(self._where(row["job_id"]))
            .values(
                state="RETRY",
                fence=row["fence"] + 1,
                owner=None,
                leased_until=None,
                started_at=None,
                available_at=due,
                last_error_code=code,
            )
        )
        conn.execute(
            outbox.update()
            .where(
                outbox.c.instance_id == self.store.instance_id,
                outbox.c.event_id == row["event_id"],
            )
            .values(
                state="PENDING",
                available_at=due,
                claim_token=None,
                claimed_until=None,
                delivered_at=None,
                last_error_code=None,
            )
        )
        record.job.state = "QUEUED"
        record.job.error = json.dumps(
            {
                "code": "INTERNAL_RETRY",
                "reason": code,
                "attempt": row["attempt"],
                "message": "Runtime recovery queued",
            }
        )
        self.store._write(record)
        self.store._audit(row["job_id"], "EXECUTION_RETRY")
        return True

    def retry(self, lease, *, code, delay_seconds=2):
        if type(code) is not str or code not in RETRY_CODES:
            raise ValueError("Invalid runtime retry code")
        _bounded(delay_seconds, 0, 60)
        self.events._standalone()
        with self.store._transaction() as conn:
            row, record, now = self._guard(conn, lease)
            return self._retry(conn, row, record, code, now, delay_seconds)

    def recover(self, *, limit=100):
        _bounded(limit, 1, 100)
        self.events._standalone()
        result = {"retried": 0, "failed": 0}
        with self.store._transaction() as conn:
            now = self._now(conn)
            # Scope-local lazy migration for existing committed outbox rows.
            missing = (
                conn.execute(
                    sa.select(outbox)
                    .where(
                        outbox.c.instance_id == self.store.instance_id,
                        self.events._live(),
                        ~sa.exists(
                            sa.select(1).where(
                                executions.c.instance_id == outbox.c.instance_id,
                                executions.c.job_id == outbox.c.job_id,
                            )
                        ),
                    )
                    .limit(limit)
                )
                .mappings()
                .all()
            )
            for row in missing:
                if self.store._load(row["job_id"]).job.state in ACTIVE:
                    self._initialize(conn, self.events._event(row), now)
            rows = (
                conn.execute(
                    sa.select(executions)
                    .join(
                        outbox,
                        sa.and_(
                            executions.c.instance_id == outbox.c.instance_id,
                            executions.c.event_id == outbox.c.event_id,
                        ),
                    )
                    .where(
                        executions.c.instance_id == self.store.instance_id,
                        sa.or_(
                            sa.and_(
                                executions.c.state == "RUNNING", executions.c.leased_until <= now
                            ),
                            sa.and_(
                                executions.c.state.in_(["READY", "RETRY"]),
                                executions.c.available_at <= now,
                                sa.or_(
                                    sa.and_(
                                        outbox.c.state == "FAILED",
                                        outbox.c.attempts >= MAX_DELIVERIES,
                                    ),
                                    sa.and_(
                                        outbox.c.state == "DELIVERED",
                                        outbox.c.delivered_at
                                        <= now - timedelta(seconds=REDRIVE_SECONDS),
                                    ),
                                ),
                            ),
                        ),
                    )
                    .order_by(executions.c.available_at, executions.c.job_id)
                    .limit(limit)
                )
                .mappings()
                .all()
            )
            for row in rows:
                record = self.store._load(row["job_id"], allow_tombstone=True)
                if record.tombstone or record.job.state not in ACTIVE:
                    continue  # Cancellation/deletion already revoke in _write.
                event = self.events.get(str(row["event_id"]))
                expired = row["state"] == "RUNNING"
                abandoned = (
                    event.state == "DELIVERED"
                    and event.delivered_at + timedelta(seconds=REDRIVE_SECONDS) <= now
                )
                exhausted = event.state == "FAILED" and event.attempts >= MAX_DELIVERIES
                if not (expired or abandoned or exhausted):
                    continue
                if exhausted and not expired:
                    self._terminal_failure(conn, row, record, "DELIVERY_EXHAUSTED")
                    result["failed"] += 1
                else:
                    retry = self._retry(
                        conn, row, record, "LEASE_EXPIRED" if expired else "BROKER_REDRIVE", now, 2
                    )
                    result["retried" if retry else "failed"] += 1
        return result


class FencedJobStore:
    """Only the pipeline operations; never delegate unfenced mutators."""

    uses_postgres = True

    def __init__(self, execution, lease):
        self.execution, self.lease = execution, lease
        self.root = execution.store.root

    def _identity(self, job_id):
        if (
            self.lease.instance_id != self.execution.store.instance_id
            or job_id != self.lease.job_id
        ):
            raise LeaseLost("Execution lease unavailable")

    @contextmanager
    def _transaction(self):
        try:
            with self.execution.store._transaction() as conn:
                yield conn
        except PostgresOperationUnavailable:
            raise LeaseLost("Execution transaction unavailable") from None

    def get_job(self, job_id):
        self._identity(job_id)
        with self._transaction() as conn:
            _, record, _ = self.execution._guard(conn, self.lease)
            return record.job

    def is_tombstoned(self, job_id):
        self._identity(job_id)
        return self.execution.store.is_tombstoned(job_id)

    def save_job(self, job):
        self._identity(job.id)
        if job.state == "SUCCEEDED":
            raise ValueError("Successful execution requires an atomic report")
        with self._transaction() as conn:
            self.execution._guard(conn, self.lease)
            result = self.execution.store.save_job(job)
            if result.state == "FAILED":
                conn.execute(
                    executions.update()
                    .where(self.execution._where(job.id))
                    .values(
                        state="FAILED",
                        owner=None,
                        leased_until=None,
                        started_at=None,
                        last_error_code="SCAN_FAILED",
                    )
                )
                self.execution.store._audit(job.id, "EXECUTION_FAILED")
            return result

    def save(self, bundle, metadata, coverage, tools):
        self._identity(bundle.job.id)
        if bundle.job.state != "SUCCEEDED":
            raise ValueError("Execution report requires a successful job")
        payload = {
            "bundle": bundle.model_dump(mode="json"),
            "metadata": metadata,
            "coverage": coverage,
            "tools": tools,
        }
        digest = hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
            ).encode()
        ).hexdigest()
        store = self.execution.store
        with self._transaction() as conn:
            row = self.execution._row(conn, bundle.job.id)
            if (
                row
                and row["state"] == "SUCCEEDED"
                and row["owner"] == self.lease.owner
                and row["fence"] == self.lease.fence
                and row["event_id"] == self.lease.event_id
                and row["attempt"] == self.lease.attempt
                and row["result_sha256"] == digest
            ):
                record = store._load(bundle.job.id)
                if record.bundle is not None:
                    return store.report(bundle.job.id)
            self.execution._guard(conn, self.lease)
            report = store.save(bundle, metadata, coverage, tools)
            conn.execute(
                executions.update()
                .where(self.execution._where(bundle.job.id))
                .values(
                    state="SUCCEEDED",
                    leased_until=None,
                    started_at=None,
                    result_sha256=digest,
                    last_error_code=None,
                )
            )
            store._audit(bundle.job.id, "EXECUTION_COMMITTED")
            return report
