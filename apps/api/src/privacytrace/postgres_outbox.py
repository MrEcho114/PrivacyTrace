"""Internal PostgreSQL event ledger. No broker, APK input or execution side effects."""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from .postgres_schema import executions, jobs, outbox, scopes

EVENT_TYPE = "privacytrace.job.ready"
MAX_ATTEMPTS = 5
ERROR_CODES = frozenset({"BROKER_UNAVAILABLE", "DELIVERY_REJECTED", "DELIVERY_TIMEOUT"})
MESSAGE_KEYS = frozenset({"version", "event_type", "instance_id", "job_id", "event_id"})


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Invalid outbox identifier")
    return UUID(value)


def _bounded(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Outbox parameter outside permitted range")
    return value


def decode_message(value):
    """Validate exactly the fixed JSON envelope; never include input in errors."""
    try:
        if isinstance(value, (str, bytes)):
            if len(value) > 1024:
                raise ValueError

            def unique(pairs):
                result = {}
                for key, item in pairs:
                    if key in result:
                        raise ValueError
                    result[key] = item
                return result

            value = json.loads(value, object_pairs_hook=unique)
        if type(value) is not dict or set(value) != MESSAGE_KEYS:
            raise ValueError
        if type(value["version"]) is not int or value["version"] != 1:
            raise ValueError
        if type(value["event_type"]) is not str or value["event_type"] != EVENT_TYPE:
            raise ValueError
        _uuid(value["instance_id"])
        _uuid(value["event_id"])
        if type(value["job_id"]) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value["job_id"]
        ):
            raise ValueError
        return dict(value)
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError("Invalid outbox message") from None


@dataclass(frozen=True)
class OutboxEvent:
    instance_id: str
    event_id: UUID
    job_id: str
    event_type: str
    version: int
    state: str
    attempts: int
    available_at: datetime
    created_at: datetime
    claim_token: UUID | None
    claimed_until: datetime | None
    delivered_at: datetime | None
    last_error_code: str | None

    @property
    def message(self):
        return decode_message(
            {
                "version": self.version,
                "event_type": self.event_type,
                "instance_id": self.instance_id,
                "job_id": self.job_id,
                "event_id": str(self.event_id),
            }
        )


class PostgresOutbox:
    """Reuse the store's transaction/RLS and per-instance serialization contract.

    A caller's outer transaction owns commit. Dispatchers must claim in a short
    standalone transaction, publish AFTER commit, then acknowledge separately.
    Never hold a transaction open across network I/O. Claims fence delivery only;
    consumers still require an execution lease and must recheck cancellation.
    """

    def __init__(self, store):
        self.store = store

    def _standalone(self):
        # Returning a claim from a caller-owned, uncommitted transaction could
        # publish an event whose Job is subsequently rolled back. Settlement
        # also needs its own commit before a dispatcher can rely on the result.
        if getattr(self.store._local, "connection", None) is not None:
            raise ValueError("Outbox delivery requires a standalone transaction")

    def _where(self, event_id):
        return sa.and_(
            outbox.c.instance_id == self.store.instance_id, outbox.c.event_id == _uuid(event_id)
        )

    def _live(self):
        return sa.exists(
            sa.select(1)
            .select_from(
                jobs.join(
                    scopes,
                    sa.and_(
                        jobs.c.instance_id == scopes.c.instance_id,
                        jobs.c.job_id == scopes.c.scope_id,
                    ),
                )
            )
            .where(
                jobs.c.instance_id == outbox.c.instance_id,
                jobs.c.job_id == outbox.c.job_id,
                scopes.c.kind == "JOB",
                scopes.c.tombstone.is_(False),
                jobs.c.record["job"]["state"].as_string().not_in(["FAILED", "CANCELLED"]),
            )
        )

    @staticmethod
    def _event(row):
        return OutboxEvent(**dict(row))

    def register(self, job, token_digest=None):
        """Explicit atomic registration; existing JSON/HTTP execution is untouched."""
        if job.state != "QUEUED":
            raise ValueError("Only queued jobs can be registered for delivery")
        with self.store._transaction():
            self.store.create_if_absent(job, token_digest)
            return self.enqueue(job.id)

    def enqueue(self, job_id):
        """Idempotent event insertion, including when nested in job registration."""
        with self.store._transaction() as conn:
            record = self.store._load(job_id)
            if record.job.state != "QUEUED":
                raise ValueError("Job is unavailable for delivery")
            now = conn.scalar(sa.select(sa.func.clock_timestamp()))
            conn.execute(
                insert(outbox)
                .values(
                    instance_id=self.store.instance_id,
                    event_id=uuid4(),
                    job_id=job_id,
                    event_type=EVENT_TYPE,
                    version=1,
                    state="PENDING",
                    attempts=0,
                    available_at=now,
                    created_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        outbox.c.instance_id,
                        outbox.c.job_id,
                        outbox.c.event_type,
                        outbox.c.version,
                    ]
                )
            )
            event = self._event(
                conn.execute(
                    sa.select(outbox).where(
                        outbox.c.instance_id == self.store.instance_id,
                        outbox.c.job_id == job_id,
                        outbox.c.event_type == EVENT_TYPE,
                        outbox.c.version == 1,
                    )
                )
                .mappings()
                .one()
            )
            conn.execute(
                insert(executions)
                .values(
                    instance_id=self.store.instance_id,
                    job_id=job_id,
                    event_id=event.event_id,
                    state="READY",
                    attempt=0,
                    fence=0,
                    available_at=now,
                )
                .on_conflict_do_nothing()
            )
            return event

    def get(self, event_id):
        with self.store._transaction() as conn:
            row = (
                conn.execute(sa.select(outbox).where(self._where(event_id)))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError("Outbox event unavailable")
            return self._event(row)

    def _discard_unavailable(self, conn):
        conn.execute(
            outbox.update()
            .where(
                outbox.c.instance_id == self.store.instance_id,
                outbox.c.state.in_(["PENDING", "CLAIMED", "FAILED"]),
                ~self._live(),
            )
            .values(
                state="DISCARDED",
                claim_token=None,
                claimed_until=None,
                last_error_code="JOB_UNAVAILABLE",
            )
        )

    def claim(self, *, limit=10, visibility_seconds=30):
        _bounded(limit, 1, 100)
        _bounded(visibility_seconds, 1, 300)
        self._standalone()
        with self.store._transaction() as conn:
            now = conn.scalar(sa.select(sa.func.clock_timestamp()))
            self._discard_unavailable(conn)
            expired = sa.and_(outbox.c.state == "CLAIMED", outbox.c.claimed_until <= now)
            conn.execute(
                outbox.update()
                .where(
                    outbox.c.instance_id == self.store.instance_id,
                    expired,
                    outbox.c.attempts >= MAX_ATTEMPTS,
                )
                .values(
                    state="FAILED",
                    claim_token=None,
                    claimed_until=None,
                    last_error_code="DELIVERY_TIMEOUT",
                )
            )
            rows = (
                conn.execute(
                    sa.select(outbox)
                    .where(
                        outbox.c.instance_id == self.store.instance_id,
                        self._live(),
                        sa.exists(
                            sa.select(1).where(
                                jobs.c.instance_id == outbox.c.instance_id,
                                jobs.c.job_id == outbox.c.job_id,
                                jobs.c.record["job"]["state"].as_string() != "SUCCEEDED",
                            )
                        ),
                        outbox.c.attempts < MAX_ATTEMPTS,
                        sa.or_(
                            sa.and_(outbox.c.state == "PENDING", outbox.c.available_at <= now),
                            expired,
                        ),
                    )
                    .order_by(outbox.c.available_at, outbox.c.event_id)
                    .limit(limit)
                    .with_for_update(skip_locked=True, of=outbox)
                )
                .mappings()
                .all()
            )
            result = []
            for row in rows:
                updated = (
                    conn.execute(
                        outbox.update()
                        .where(self._where(str(row["event_id"])))
                        .values(
                            state="CLAIMED",
                            claim_token=uuid4(),
                            claimed_until=now + timedelta(seconds=visibility_seconds),
                            attempts=outbox.c.attempts + 1,
                        )
                        .returning(outbox)
                    )
                    .mappings()
                    .one()
                )
                result.append(self._event(updated))
            return result

    def _owned(self, event_id, token, now):
        return sa.and_(
            self._where(event_id),
            outbox.c.state == "CLAIMED",
            outbox.c.claim_token == _uuid(token),
            outbox.c.claimed_until > now,
        )

    def acknowledge(self, event_id, token):
        self._standalone()
        with self.store._transaction() as conn:
            now = conn.scalar(sa.select(sa.func.clock_timestamp()))
            self._discard_unavailable(conn)
            return bool(
                conn.execute(
                    outbox.update()
                    .where(
                        self._owned(event_id, token, now),
                        self._live(),
                    )
                    .values(
                        state="DELIVERED",
                        delivered_at=now,
                        claim_token=None,
                        claimed_until=None,
                        last_error_code=None,
                    )
                ).rowcount
            )

    def fail(self, event_id, token, *, code, retry_delay_seconds=0):
        if type(code) is not str or code not in ERROR_CODES:
            raise ValueError("Invalid delivery failure code")
        _bounded(retry_delay_seconds, 0, 3600)
        self._standalone()
        with self.store._transaction() as conn:
            now = conn.scalar(sa.select(sa.func.clock_timestamp()))
            self._discard_unavailable(conn)
            return bool(
                conn.execute(
                    outbox.update()
                    .where(
                        self._owned(event_id, token, now),
                        self._live(),
                    )
                    .values(
                        state=sa.case(
                            (outbox.c.attempts >= MAX_ATTEMPTS, "FAILED"), else_="PENDING"
                        ),
                        available_at=now + timedelta(seconds=retry_delay_seconds),
                        claim_token=None,
                        claimed_until=None,
                        last_error_code=code,
                    )
                ).rowcount
            )
