"""Immutable job input manifests and expiring task-bound runner material references.

Revision ID: 0080_04
Revises: 0080_03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0080_04"
down_revision = "0080_03"
branch_labels = None
depends_on = None
S = "privacytrace"


def upgrade():
    op.create_table(
        "runtime_inputs",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(100), primary_key=True),
        sa.Column("draft_id", sa.String(32), nullable=False),
        sa.Column("document_key", sa.String(200), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id", "job_id"], [f"{S}.jobs.instance_id", f"{S}.jobs.job_id"]
        ),
        sa.ForeignKeyConstraint(
            ["instance_id", "draft_id"],
            [f"{S}.analysis_scopes.instance_id", f"{S}.analysis_scopes.scope_id"],
        ),
        sa.ForeignKeyConstraint(
            ["instance_id", "document_key"],
            [f"{S}.intake_documents.instance_id", f"{S}.intake_documents.document_key"],
        ),
        sa.CheckConstraint("draft_id ~ '^[a-f0-9]{32}$'", name="runtime_draft"),
        schema=S,
    )
    op.create_table(
        "runner_materials",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("material_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scope_id", sa.String(100), nullable=False),
        sa.Column("draft_id", sa.String(32), nullable=False),
        sa.Column("path_key", sa.String(300), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_count", sa.BigInteger, nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("owner", UUID(as_uuid=True)),
        sa.Column("fence", sa.BigInteger, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id", "scope_id"],
            [f"{S}.analysis_scopes.instance_id", f"{S}.analysis_scopes.scope_id"],
        ),
        sa.ForeignKeyConstraint(
            ["instance_id", "draft_id"],
            [f"{S}.analysis_scopes.instance_id", f"{S}.analysis_scopes.scope_id"],
        ),
        sa.CheckConstraint("draft_id ~ '^[a-f0-9]{32}$'", name="runner_material_draft"),
        sa.CheckConstraint("sha256 ~ '^[a-f0-9]{64}$'", name="runner_material_digest"),
        sa.CheckConstraint("byte_count BETWEEN 1 AND 157286400", name="runner_material_size"),
        sa.CheckConstraint(
            "(mode = 'inspect' AND owner IS NULL AND fence = 0) OR "
            "(mode = 'scan' AND owner IS NOT NULL AND fence > 0)",
            name="runner_material_mode",
        ),
        schema=S,
    )
    op.create_index(
        "runner_material_expiry", "runner_materials", ["instance_id", "expires_at"], schema=S
    )
    predicate = "instance_id = current_setting('privacytrace.instance_id', true)"
    for table in ("runtime_inputs", "runner_materials"):
        op.execute(f"ALTER TABLE {S}.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {S}.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY instance_boundary ON {S}.{table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(f"GRANT SELECT, INSERT, DELETE ON {S}.{table} TO privacytrace_runtime")


def downgrade():
    op.drop_table("runner_materials", schema=S)
    op.drop_table("runtime_inputs", schema=S)
