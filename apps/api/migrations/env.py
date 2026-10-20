"""Explicit operator-only migrations. The API never imports or runs this entry point."""

import os

import sqlalchemy as sa
from alembic import context

from privacytrace.postgres_schema import SCHEMA, metadata


def migrate(connection):
    owner = connection.execute(
        sa.text("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = :schema"),
        {"schema": SCHEMA},
    ).scalar_one_or_none()
    role = connection.execute(sa.text("SELECT current_user")).scalar_one()
    if owner is not None and owner != role:
        raise RuntimeError("Migrations require the dedicated schema owner role")
    if owner is None:
        connection.execute(sa.text(f"CREATE SCHEMA {SCHEMA}"))
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Run migrations against an explicit PostgreSQL database")
provided = context.config.attributes.get("connection")
if provided is not None:
    migrate(provided)
else:
    url = os.environ.get("PRIVACYTRACE_MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("PRIVACYTRACE_MIGRATION_DATABASE_URL is required")
    engine = sa.create_engine(url, hide_parameters=True, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
