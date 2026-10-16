"""Initial PostgreSQL persistence. No queue, lease executor or legacy data import.

Revision ID: 0080_01
Revises: None
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0080_01"
down_revision = None
branch_labels = None
depends_on = None
S = "privacytrace"


def upgrade():
    op.create_table(
        "analysis_scopes",
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
        schema=S,
    )
    op.create_table(
        "jobs",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(100), primary_key=True),
        sa.Column("record", JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id", "job_id"],
            [f"{S}.analysis_scopes.instance_id", f"{S}.analysis_scopes.scope_id"],
        ),
        schema=S,
    )
    op.create_table(
        "intake_documents",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("document_key", sa.String(200), primary_key=True),
        sa.Column("scope_id", sa.String(100)),
        sa.Column("material_ref", sa.String(32), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_count", sa.BigInteger, nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id", "scope_id"],
            [f"{S}.analysis_scopes.instance_id", f"{S}.analysis_scopes.scope_id"],
        ),
        sa.CheckConstraint("material_ref ~ '^[a-f0-9]{32}$'", name="material_reference"),
        sa.CheckConstraint("sha256 ~ '^[a-f0-9]{64}$'", name="material_digest"),
        sa.CheckConstraint("byte_count >= 0 AND byte_count <= 8388608", name="material_size"),
        schema=S,
    )
    op.create_table(
        "audit_events",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scope_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id", "scope_id"],
            [f"{S}.analysis_scopes.instance_id", f"{S}.analysis_scopes.scope_id"],
        ),
        schema=S,
    )
    op.execute(f"REVOKE ALL ON SCHEMA {S} FROM PUBLIC")
    op.execute(f"GRANT USAGE ON SCHEMA {S} TO privacytrace_runtime")
    for table in ("analysis_scopes", "jobs", "intake_documents", "audit_events"):
        op.execute(f"ALTER TABLE {S}.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {S}.{table} FORCE ROW LEVEL SECURITY")
        predicate = "instance_id = current_setting('privacytrace.instance_id', true)"
        op.execute(
            f"CREATE POLICY instance_boundary ON {S}.{table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        rights = "SELECT, INSERT" if table == "audit_events" else "SELECT, INSERT, UPDATE"
        op.execute(f"GRANT {rights} ON {S}.{table} TO privacytrace_runtime")
    op.execute(f"GRANT SELECT ON {S}.alembic_version TO privacytrace_runtime")


def downgrade():
    # Explicit destructive operator action, never called during API startup.
    for table in ("audit_events", "intake_documents", "jobs", "analysis_scopes"):
        op.drop_table(table, schema=S)
