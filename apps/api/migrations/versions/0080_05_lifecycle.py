"""Deletion replay checkpoints and cross-process upload reservations.

Revision ID: 0080_05
Revises: 0080_04
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0080_05"
down_revision = "0080_04"
branch_labels = None
depends_on = None
S = "privacytrace"


def upgrade():
    op.create_table(
        "deletion_intents",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(10), primary_key=True),
        sa.Column("scope_id", sa.String(100), primary_key=True),
        sa.Column("sequence", sa.BigInteger, nullable=False),
        sa.Column("mac", sa.String(64), nullable=False),
        sa.UniqueConstraint("instance_id", "sequence", name="deletion_sequence"),
        sa.CheckConstraint("kind IN ('JOB', 'DRAFT') AND sequence > 0", name="deletion_kind"),
        sa.CheckConstraint("mac ~ '^[a-f0-9]{64}$'", name="deletion_mac"),
        schema=S,
    )
    op.create_table(
        "upload_reservations",
        sa.Column("instance_id", sa.String(36), primary_key=True),
        sa.Column("draft_id", sa.String(32), primary_key=True),
        sa.Column("owner", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instance_id", "draft_id"],
            [f"{S}.analysis_scopes.instance_id", f"{S}.analysis_scopes.scope_id"],
        ),
        sa.CheckConstraint("draft_id ~ '^[a-f0-9]{32}$'", name="upload_draft"),
        schema=S,
    )
    predicate = "instance_id = current_setting('privacytrace.instance_id', true)"
    for table in ("deletion_intents", "upload_reservations"):
        op.execute(f"ALTER TABLE {S}.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {S}.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY instance_boundary ON {S}.{table} "
            f"USING ({predicate}) WITH CHECK ({predicate})"
        )
    op.execute(f"GRANT SELECT, INSERT ON {S}.deletion_intents TO privacytrace_runtime")
    op.execute(f"GRANT SELECT, INSERT, DELETE ON {S}.upload_reservations TO privacytrace_runtime")
    # Material pointers may be reclaimed; scope/audit/deletion history may not.
    op.execute(f"GRANT DELETE ON {S}.intake_documents TO privacytrace_runtime")


def downgrade():
    op.execute(f"REVOKE DELETE ON {S}.intake_documents FROM privacytrace_runtime")
    op.drop_table("upload_reservations", schema=S)
    op.drop_table("deletion_intents", schema=S)
