"""PostgreSQL implementation of #69's storage seam, sharing existing record semantics."""

import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import local
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from .job_store import JobStore
from .postgres_schema import REVISION, SCHEMA, audit, documents, executions, jobs, scopes
from .runtime_models import StoredJob


class PostgresJobStore(JobStore):
    """Validated job records in PostgreSQL; APK/policy materials stay on a private volume.

    The inherited save/review/cancel/report methods retain the JSON store's domain
    validation. Only persistence primitives change. One transaction lock per
    instance preserves the existing store's serialized mutation contract across
    processes; this is not a distributed scheduler or execution lease.
    """

    uses_postgres = True

    def __init__(self, url: str, instance_id: str, root: Path):
        self._local = local()
        try:
            self.instance_id = str(UUID(instance_id))
            parsed = sa.engine.make_url(url)
            if parsed.drivername not in {"postgresql", "postgresql+psycopg"}:
                raise ValueError("PostgreSQL with psycopg is required")
            self.engine = sa.create_engine(
                parsed.set(drivername="postgresql+psycopg"),
                pool_pre_ping=True,
                hide_parameters=True,
            )
        except (ValueError, SQLAlchemyError):
            raise ValueError("Invalid PostgreSQL storage configuration") from None
        try:
            self._check_runtime()
        except Exception:
            self.engine.dispose()
            raise
        # An explicit instance namespace cannot enumerate or import a local JSON root.
        self.root = Path(root).absolute() / "instances" / self.instance_id
        self._safe_root()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _check_runtime(self):
        try:
            with self.engine.connect() as conn:
                unsafe = conn.execute(
                    sa.text(
                        "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls "
                        "FROM pg_roles WHERE rolname = current_user"
                    )
                ).scalar_one()
                owner = conn.execute(
                    sa.text(
                        "SELECT pg_has_role(current_user, nspowner, 'MEMBER') "
                        "OR has_schema_privilege(current_user, oid, 'CREATE') "
                        "FROM pg_namespace WHERE nspname = :schema"
                    ),
                    {"schema": SCHEMA},
                ).scalar_one_or_none()
                if unsafe or owner is not False:
                    raise ValueError(
                        "Storage requires a migrated schema and a restricted runtime role"
                    )
                version = (
                    conn.execute(sa.text(f"SELECT version_num FROM {SCHEMA}.alembic_version"))
                    .scalars()
                    .all()
                )
                if version != [REVISION]:
                    raise ValueError(
                        "PostgreSQL schema version is not supported; run migrations separately"
                    )
        except SQLAlchemyError:
            raise ValueError("PostgreSQL storage unavailable or not migrated") from None

    @contextmanager
    def _transaction(self):
        active = getattr(self._local, "connection", None)
        if active is not None:
            yield active
            return
        try:
            with self.engine.begin() as conn:
                conn.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(sa.text("SET LOCAL statement_timeout = '15s'"))
                conn.execute(
                    sa.text("SELECT set_config('privacytrace.instance_id', :instance, true)"),
                    {"instance": self.instance_id},
                )
                conn.execute(
                    sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:instance, 80))"),
                    {"instance": self.instance_id},
                )
                self._local.connection = conn
                try:
                    yield conn
                finally:
                    self._local.connection = None
        except SQLAlchemyError:
            # Neither a DSN, SQL parameters, policy text nor capability goes into errors.
            raise ValueError("PostgreSQL storage rejected the operation") from None

    def _scope(self, scope_id):
        return (
            self._local.connection.execute(
                sa.select(scopes).where(
                    scopes.c.instance_id == self.instance_id,
                    scopes.c.scope_id == scope_id,
                )
            )
            .mappings()
            .one_or_none()
        )

    def _audit(self, scope_id, action):
        self._local.connection.execute(
            audit.insert().values(
                instance_id=self.instance_id,
                event_id=uuid4(),
                scope_id=scope_id,
                action=action,
                created_at=datetime.now(timezone.utc),
            )
        )

    def _load(self, job_id, allow_tombstone=False):
        self._path(job_id)  # Retain ID/path validation, without opening any JSON file.
        row = (
            self._local.connection.execute(
                sa.select(
                    jobs.c.record,
                    scopes.c.token_digest,
                    scopes.c.tombstone,
                )
                .select_from(
                    jobs.join(
                        scopes,
                        sa.and_(
                            jobs.c.instance_id == scopes.c.instance_id,
                            jobs.c.job_id == scopes.c.scope_id,
                        ),
                    )
                )
                .where(jobs.c.instance_id == self.instance_id, jobs.c.job_id == job_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None or (row["tombstone"] and not allow_tombstone):
            raise KeyError(job_id)
        record = StoredJob.model_validate(
            {
                **row["record"],
                "token_digest": row["token_digest"],
                "tombstone": row["tombstone"],
            }
        )
        if record.job.id != job_id:
            raise ValueError("Stored job identity mismatch")
        return record

    @staticmethod
    def _digest(digest):
        if digest is not None and not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid capability digest")

    def _write(self, record):
        record = StoredJob.model_validate(record.model_dump())
        self._path(record.job.id)
        self._digest(record.token_digest)
        previous = self._scope(record.job.id)
        if previous and (
            previous["kind"] != "JOB" or (previous["tombstone"] and not record.tombstone)
        ):
            raise ValueError("Scope is unavailable")
        if previous is None:
            count = self._local.connection.execute(
                sa.select(sa.func.count())
                .select_from(scopes)
                .where(
                    scopes.c.instance_id == self.instance_id,
                    scopes.c.kind == "JOB",
                    scopes.c.tombstone.is_(False),
                )
            ).scalar_one()
            if count >= self.MAX_RECORDS:
                raise ValueError("Job record limit reached")
        action = "JOB_WRITE"
        if record.tombstone:
            # Online deletion revokes credentials and removes report/policy/review content.
            record = StoredJob(job=record.job, tombstone=True)
            action = "JOB_DELETE"
        payload = record.model_dump(mode="json", exclude={"token_digest", "tombstone"})
        if len(record.model_dump_json().encode("utf-8")) > self.MAX_FILE_BYTES:
            raise ValueError("Job record exceeds storage size limit")
        statement = insert(scopes).values(
            instance_id=self.instance_id,
            scope_id=record.job.id,
            kind="JOB",
            token_digest=record.token_digest,
            tombstone=record.tombstone,
            created_at=record.job.created_at,
        )
        self._local.connection.execute(
            statement.on_conflict_do_update(
                index_elements=[scopes.c.instance_id, scopes.c.scope_id],
                set_={"token_digest": record.token_digest, "tombstone": record.tombstone},
            )
        )
        statement = insert(jobs).values(
            instance_id=self.instance_id,
            job_id=record.job.id,
            record=payload,
        )
        self._local.connection.execute(
            statement.on_conflict_do_update(
                index_elements=[jobs.c.instance_id, jobs.c.job_id],
                set_={"record": payload},
            )
        )
        self._audit(record.job.id, action)
        if record.tombstone or record.job.state == "CANCELLED":
            # Same transaction and instance lock as revocation: no late heartbeat
            # or report can retain a pre-cancellation execution token.
            self._local.connection.execute(
                executions.update()
                .where(
                    executions.c.instance_id == self.instance_id,
                    executions.c.job_id == record.job.id,
                    executions.c.state != "REVOKED",
                )
                .values(
                    state="REVOKED",
                    fence=executions.c.fence + 1,
                    owner=None,
                    leased_until=None,
                    started_at=None,
                    result_sha256=None,
                    last_error_code="JOB_UNAVAILABLE",
                )
            )

    def create_if_absent(self, job, token_digest=None):
        with self._transaction():
            if self._scope(job.id) is not None:
                raise ValueError("Job already exists; choose a new job ID")
            self._write(StoredJob(job=job, token_digest=token_digest))
            return job

    def list(self):
        with self._transaction() as conn:
            ids = (
                conn.execute(
                    sa.select(jobs.c.job_id).where(
                        jobs.c.instance_id == self.instance_id,
                    )
                )
                .scalars()
                .all()
            )
            records = [self._load(job_id, allow_tombstone=True) for job_id in ids]
            return sorted(
                (r.job for r in records if not r.tombstone),
                key=lambda job: job.created_at,
                reverse=True,
            )

    def is_tombstoned(self, job_id):
        self._path(job_id)
        with self._transaction():
            row = self._scope(job_id)
            return bool(row and row["tombstone"])

    def set_token_digest(self, job_id, token_digest):
        self._digest(token_digest)
        with self._transaction():
            record = self._load(job_id)
            record.token_digest = token_digest
            self._write(record)

    def document(self, key):
        with self._transaction() as conn:
            row = (
                conn.execute(
                    sa.select(documents).where(
                        documents.c.instance_id == self.instance_id,
                        documents.c.document_key == key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(key)
            return dict(row)

    def save_document(self, key, material_ref, digest, size, *, token_digest=None):
        """Index server-generated immutable material references, never arbitrary input paths."""
        if not re.fullmatch(r"(?:[a-f0-9]{32}/)?[A-Za-z0-9_.-]+", key):
            raise ValueError("Invalid intake document key")
        with self._transaction() as conn:
            scope_id = key.split("/")[0] if "/" in key else None
            if scope_id and self._scope(scope_id) is None:
                self._digest(token_digest)
                conn.execute(
                    scopes.insert().values(
                        instance_id=self.instance_id,
                        scope_id=scope_id,
                        kind="DRAFT",
                        token_digest=token_digest,
                        tombstone=False,
                        created_at=datetime.now(timezone.utc),
                    )
                )
            statement = insert(documents).values(
                instance_id=self.instance_id,
                document_key=key,
                scope_id=scope_id,
                material_ref=material_ref,
                sha256=digest,
                byte_count=size,
            )
            conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[documents.c.instance_id, documents.c.document_key],
                    set_={"material_ref": material_ref, "sha256": digest, "byte_count": size},
                )
            )
            if scope_id:
                self._audit(scope_id, "DRAFT_WRITE")

    def draft_digest(self, draft_id):
        with self._transaction():
            row = self._scope(draft_id)
            if row is None or row["kind"] != "DRAFT" or row["tombstone"]:
                raise KeyError(draft_id)
            return row["token_digest"]

    def draft_ids(self):
        with self._transaction() as conn:
            return (
                conn.execute(
                    sa.select(scopes.c.scope_id).where(
                        scopes.c.instance_id == self.instance_id,
                        scopes.c.kind == "DRAFT",
                        scopes.c.tombstone.is_(False),
                    )
                )
                .scalars()
                .all()
            )

    def document_bytes(self, draft_id):
        with self._transaction() as conn:
            return conn.execute(
                sa.select(
                    sa.func.coalesce(
                        sa.func.sum(documents.c.byte_count),
                        0,
                    )
                ).where(
                    documents.c.instance_id == self.instance_id,
                    documents.c.document_key.like(f"{draft_id}/revision-%"),
                )
            ).scalar_one()

    def close(self):
        self.engine.dispose()
