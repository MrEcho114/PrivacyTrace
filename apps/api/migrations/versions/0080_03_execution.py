"""Execution attempts, expiring leases and monotonic fencing.

Revision ID: 0080_03
Revises: 0080_02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0080_03"
down_revision = "0080_02"
branch_labels = None
depends_on = None
S = "privacytrace"


def upgrade():
    op.create_table(
        "job_executions",
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
            ["instance_id", "job_id"], [f"{S}.jobs.instance_id", f"{S}.jobs.job_id"]
        ),
        sa.ForeignKeyConstraint(
            ["instance_id", "event_id"],
            [f"{S}.outbox_events.instance_id", f"{S}.outbox_events.event_id"],
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
        schema=S,
    )
    op.create_index(
        "execution_recovery", "job_executions", ["instance_id", "state", "leased_until"], schema=S
    )
    op.execute(f"ALTER TABLE {S}.job_executions ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {S}.job_executions FORCE ROW LEVEL SECURITY")
    predicate = "instance_id = current_setting('privacytrace.instance_id', true)"
    op.execute(
        f"CREATE POLICY instance_boundary ON {S}.job_executions "
        f"USING ({predicate}) WITH CHECK ({predicate})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON {S}.job_executions TO privacytrace_runtime")


def downgrade():
    op.drop_table("job_executions", schema=S)
