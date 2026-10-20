"""Transactional outbox; delivery ownership is distinct from execution leases.

Revision ID: 0080_02
Revises: 0080_01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0080_02"
down_revision = "0080_01"
branch_labels = None
depends_on = None
S = "privacytrace"


def upgrade():
    op.create_table(
        "outbox_events",
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
            ["instance_id", "job_id"], [f"{S}.jobs.instance_id", f"{S}.jobs.job_id"]
        ),
        sa.UniqueConstraint("instance_id", "job_id", "event_type", "version", name="outbox_once"),
        sa.CheckConstraint(
            "event_type = 'privacytrace.job.ready' AND version = 1", name="outbox_kind"
        ),
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
        schema=S,
    )
    op.create_index(
        "outbox_pending", "outbox_events", ["instance_id", "state", "available_at"], schema=S
    )
    op.create_index(
        "outbox_claimed", "outbox_events", ["instance_id", "state", "claimed_until"], schema=S
    )
    op.execute(f"ALTER TABLE {S}.outbox_events ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {S}.outbox_events FORCE ROW LEVEL SECURITY")
    predicate = "instance_id = current_setting('privacytrace.instance_id', true)"
    op.execute(
        f"CREATE POLICY instance_boundary ON {S}.outbox_events "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {S}.outbox_events TO privacytrace_runtime")


def downgrade():
    # Explicitly destructive: never a retry/recovery path or an API startup action.
    op.drop_table("outbox_events", schema=S)
