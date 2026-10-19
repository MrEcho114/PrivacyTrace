"""Storage metadata only; public evidence/report models remain the source of truth."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "privacytrace"
REVISION = "0080_03"
metadata = sa.MetaData(schema=SCHEMA)

scopes = sa.Table(
    "analysis_scopes",
    metadata,
    sa.Column("instance_id", sa.String(36), primary_key=True),
    sa.Column("scope_id", sa.String(100), primary_key=True),
    sa.Column("kind", sa.String(10), nullable=False),
    sa.Column("token_digest", sa.String(64)),
    sa.Column("tombstone", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('JOB', 'DRAFT')", name="scope_kind"),
    sa.CheckConstraint(
        "token_digest IS NULL OR token_digest ~ '^[a-f0-9]{64}$'", name="digest_format"
    ),
    sa.CheckConstraint("NOT tombstone OR token_digest IS NULL", name="revoked_tombstone"),
)
jobs = sa.Table(
    "jobs",
    metadata,
    sa.Column("instance_id", sa.String(36), primary_key=True),
    sa.Column("job_id", sa.String(100), primary_key=True),
    sa.Column("record", JSONB, nullable=False),
    sa.ForeignKeyConstraint(
        ["instance_id", "job_id"],
        [f"{SCHEMA}.analysis_scopes.instance_id", f"{SCHEMA}.analysis_scopes.scope_id"],
    ),
)
documents = sa.Table(
    "intake_documents",
    metadata,
    sa.Column("instance_id", sa.String(36), primary_key=True),
    sa.Column("document_key", sa.String(200), primary_key=True),
    sa.Column("scope_id", sa.String(100)),
    sa.Column("material_ref", sa.String(32), nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("byte_count", sa.BigInteger, nullable=False),
    sa.ForeignKeyConstraint(
        ["instance_id", "scope_id"],
        [f"{SCHEMA}.analysis_scopes.instance_id", f"{SCHEMA}.analysis_scopes.scope_id"],
    ),
    sa.CheckConstraint("material_ref ~ '^[a-f0-9]{32}$'", name="material_reference"),
    sa.CheckConstraint("sha256 ~ '^[a-f0-9]{64}$'", name="material_digest"),
    sa.CheckConstraint("byte_count >= 0 AND byte_count <= 8388608", name="material_size"),
)
audit = sa.Table(
    "audit_events",
    metadata,
    sa.Column("instance_id", sa.String(36), primary_key=True),
    sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("scope_id", sa.String(100), nullable=False),
    sa.Column("action", sa.String(20), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(
        ["instance_id", "scope_id"],
        [f"{SCHEMA}.analysis_scopes.instance_id", f"{SCHEMA}.analysis_scopes.scope_id"],
    ),
)

outbox = sa.Table(
    "outbox_events",
    metadata,
    sa.Column("instance_id", sa.String(36), primary_key=True),
    sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
    sa.Column("job_id", sa.String(100), nullable=False),
    sa.Column("event_type", sa.String(40), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("state", sa.String(12), nullable=False),
    sa.Column("attempts", sa.Integer, nullable=False),
    sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("claim_token", UUID(as_uuid=True)),
    sa.Column("claimed_until", sa.DateTime(timezone=True)),
    sa.Column("delivered_at", sa.DateTime(timezone=True)),
    sa.Column("last_error_code", sa.String(24)),
    sa.ForeignKeyConstraint(
        ["instance_id", "job_id"], [f"{SCHEMA}.jobs.instance_id", f"{SCHEMA}.jobs.job_id"]
    ),
    sa.UniqueConstraint("instance_id", "job_id", "event_type", "version", name="outbox_once"),
    sa.CheckConstraint("event_type = 'privacytrace.job.ready' AND version = 1", name="outbox_kind"),
    sa.CheckConstraint(
        "state IN ('PENDING', 'CLAIMED', 'DELIVERED', 'DISCARDED', 'FAILED')",
        name="outbox_state",
    ),
    sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="outbox_attempts"),
    sa.CheckConstraint(
        "(state = 'CLAIMED' AND claim_token IS NOT NULL AND claimed_until IS NOT NULL) OR "
        "(state <> 'CLAIMED' AND claim_token IS NULL AND claimed_until IS NULL)",
        name="outbox_claim",
    ),
    sa.CheckConstraint(
        "(state = 'DELIVERED') = (delivered_at IS NOT NULL)", name="outbox_delivered"
    ),
    sa.CheckConstraint(
        "last_error_code IS NULL OR last_error_code IN "
        "('BROKER_UNAVAILABLE', 'DELIVERY_REJECTED', 'DELIVERY_TIMEOUT', 'JOB_UNAVAILABLE')",
        name="outbox_error",
    ),
)
sa.Index("outbox_pending", outbox.c.instance_id, outbox.c.state, outbox.c.available_at)
sa.Index("outbox_claimed", outbox.c.instance_id, outbox.c.state, outbox.c.claimed_until)

executions = sa.Table(
    "job_executions",
    metadata,
    sa.Column("instance_id", sa.String(36), primary_key=True),
    sa.Column("job_id", sa.String(100), primary_key=True),
    sa.Column("event_id", UUID(as_uuid=True), nullable=False),
    sa.Column("state", sa.String(12), nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("fence", sa.BigInteger, nullable=False),
    sa.Column("owner", UUID(as_uuid=True)),
    sa.Column("leased_until", sa.DateTime(timezone=True)),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("result_sha256", sa.String(64)),
    sa.Column("last_error_code", sa.String(24)),
    sa.ForeignKeyConstraint(
        ["instance_id", "job_id"], [f"{SCHEMA}.jobs.instance_id", f"{SCHEMA}.jobs.job_id"]
    ),
    sa.ForeignKeyConstraint(
        ["instance_id", "event_id"],
        [f"{SCHEMA}.outbox_events.instance_id", f"{SCHEMA}.outbox_events.event_id"],
    ),
    sa.CheckConstraint(
        "state IN ('READY', 'RUNNING', 'RETRY', 'SUCCEEDED', 'FAILED', 'REVOKED')",
        name="execution_state",
    ),
    sa.CheckConstraint("attempt BETWEEN 0 AND 3 AND fence >= 0", name="execution_attempt"),
    sa.CheckConstraint(
        "(state = 'RUNNING' AND attempt > 0 AND owner IS NOT NULL "
        "AND leased_until IS NOT NULL AND started_at IS NOT NULL) OR "
        "(state <> 'RUNNING' AND leased_until IS NULL AND started_at IS NULL "
        "AND (state = 'SUCCEEDED' OR owner IS NULL))",
        name="execution_lease",
    ),
    sa.CheckConstraint(
        "(state = 'SUCCEEDED' AND result_sha256 IS NOT NULL "
        "AND result_sha256 ~ '^[a-f0-9]{64}$') OR "
        "(state <> 'SUCCEEDED' AND result_sha256 IS NULL)",
        name="execution_result",
    ),
    sa.CheckConstraint(
        "last_error_code IS NULL OR last_error_code IN "
        "('LEASE_EXPIRED', 'RUNNER_UNAVAILABLE', 'WORKER_LOST', 'SCAN_FAILED', "
        "'DELIVERY_EXHAUSTED', 'BROKER_REDRIVE', 'JOB_UNAVAILABLE')",
        name="execution_error",
    ),
)
sa.Index(
    "execution_recovery", executions.c.instance_id, executions.c.state, executions.c.leased_until
)
