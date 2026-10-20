"""Database migration bootstrap entrypoint.

Executes `alembic upgrade head` using dedicated migrator credentials (privacytrace_migrator)
before runtime containers boot. Verifies schema revision 0080_05, RLS enforcement,
and least-privilege role boundaries.

This entrypoint never leaks connection credentials in exceptions or process outputs.
"""

import argparse
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "apps/api/alembic.ini"
SCHEMA = "privacytrace"
EXPECTED_REVISION = "0080_05"

EXPECTED_TABLES = {
    "analysis_scopes",
    "jobs",
    "intake_documents",
    "audit_events",
    "outbox_events",
    "job_executions",
    "runtime_inputs",
    "runner_materials",
    "deletion_intents",
    "upload_reservations",
}


def resolve_migration_url(secret_file=None):
    """Resolve the migration database URL from a secret file or environment."""
    url = None
    if secret_file:
        path = Path(secret_file)
        if not path.is_file():
            raise ValueError("Migration database URL secret file not found")
        url = path.read_text(encoding="utf-8").strip()
    elif os.environ.get("PRIVACYTRACE_MIGRATION_DATABASE_URL_FILE"):
        path = Path(os.environ["PRIVACYTRACE_MIGRATION_DATABASE_URL_FILE"])
        if not path.is_file():
            raise ValueError("Migration database URL secret file not found")
        url = path.read_text(encoding="utf-8").strip()
    elif os.environ.get("PRIVACYTRACE_MIGRATION_DATABASE_URL"):
        url = os.environ["PRIVACYTRACE_MIGRATION_DATABASE_URL"].strip()

    if not url:
        raise ValueError(
            "Migration database URL required via PRIVACYTRACE_MIGRATION_DATABASE_URL_FILE "
            "or PRIVACYTRACE_MIGRATION_DATABASE_URL"
        )
    return url


def validate_migrator_role(connection):
    """Assert role boundaries: must not be runtime user, must not be superuser or bypassrls."""
    role = connection.execute(sa.text("SELECT current_user")).scalar_one()
    if role != "privacytrace_migrator":
        raise ValueError(
            "Migration bootstrap requires dedicated privacytrace_migrator "
            "credentials, not runtime credentials"
        )

    flags = connection.execute(
        sa.text(
            "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).fetchone()
    if not flags or any(flags):
        raise ValueError("Migration role must not possess superuser or bypassrls privileges")
    return role


def run_bootstrap(migration_url):
    """Execute Alembic migrations and verify schema state post-migration."""
    from privacytrace.durable_intake import ensure_control_plane

    # Enforce control plane container boundaries: no Docker socket or endpoints
    ensure_control_plane()

    engine = sa.create_engine(migration_url, hide_parameters=True, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as conn:
            # 1. Validate role boundaries
            role = validate_migrator_role(conn)

            # 2. Configure and run Alembic migrations
            cfg = Config(str(ALEMBIC_INI))
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            conn.commit()

            # 3. Verify target revision
            rev = conn.execute(
                sa.text(f"SELECT version_num FROM {SCHEMA}.alembic_version")
            ).scalar_one_or_none()
            if rev != EXPECTED_REVISION:
                raise RuntimeError(
                    f"Migration completed with revision {rev!r}, expected {EXPECTED_REVISION!r}"
                )

            # 4. Verify all 10 expected tables exist
            tables = set(
                conn.execute(
                    sa.text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"),
                    {"schema": SCHEMA},
                )
                .scalars()
                .all()
            )
            missing = EXPECTED_TABLES - tables
            if missing:
                raise RuntimeError("Migration schema missing required tables")

            # 5. Verify *business* RLS, not the Alembic metadata version table.
            # Unknown tables must be forced-RLS too, so a later forward
            # migration cannot add an unprotected table that slips past us.
            rows = conn.execute(
                sa.text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = :schema AND c.relkind = 'r'"
                ),
                {"schema": SCHEMA},
            ).fetchall()
            actual = {name for name, _, _ in rows}
            if not EXPECTED_TABLES.issubset(actual):
                raise RuntimeError("Migration schema missing required tables")
            if any(
                not enabled or not forced
                for name, enabled, forced in rows
                if name != "alembic_version"
            ):
                raise RuntimeError("Business table requires enabled and forced ROW LEVEL SECURITY")
            if not conn.execute(
                sa.text(
                    "SELECT has_table_privilege("
                    "'privacytrace_runtime', 'privacytrace.alembic_version', 'SELECT')"
                )
            ).scalar_one():
                raise RuntimeError("Runtime role needs migration revision read privilege")

            return {
                "bootstrap": "success",
                "schema": SCHEMA,
                "revision": rev,
                "tables_count": len(tables),
                "role": role,
            }
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="PrivacyTrace Database Migration Bootstrap")
    parser.add_argument(
        "--secret-file", type=Path, help="Path to migration database URL secret file"
    )
    args = parser.parse_args()

    try:
        url = resolve_migration_url(args.secret_file)
        summary = run_bootstrap(url)
        print(
            f"Database bootstrap successful: schema {summary['schema']} "
            f"at revision {summary['revision']}"
        )
    except Exception as exc:
        # Never echo secret DSNs or database passwords in exit messages
        msg = type(exc).__name__
        if str(exc) and "postgres" not in str(exc).lower() and "@" not in str(exc):
            msg += f": {exc}"
        sys.exit(f"Database migration bootstrap failed: {msg}")


if __name__ == "__main__":
    main()
