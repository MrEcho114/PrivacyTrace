"""Storage metadata only; public evidence/report models remain the source of truth."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "privacytrace"
REVISION = "0080_01"
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
