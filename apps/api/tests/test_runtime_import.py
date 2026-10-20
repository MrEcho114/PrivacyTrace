"""Explicit JSON import against real PostgreSQL, with fresh authorization scopes."""

import hashlib
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from starlette.requests import Request
from test_capability_tokens import seed_job
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import queued
from test_postgres_storage import store as store

from privacytrace.auth import SecuritySeam, generate_capability_token, hash_token
from privacytrace.config import ServerConfig
from privacytrace.job_store import JobStore
from privacytrace.postgres_schema import outbox
from privacytrace.runtime_import import import_records


def test_import_preserves_original_bytes_provenance_and_issues_new_scope(store, tmp_path):
    source = JobStore(tmp_path / "local-json")
    old_token, digest = generate_capability_token()
    report = seed_job(source, digest)
    path = source._path(report.job.id)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    mapping_path = tmp_path / "private-import-mapping.json"
    assert import_records(source, store, [report.job.id], mapping_path)["imported"] == 1
    mapping = json.loads(mapping_path.read_bytes())["jobs"][0]
    assert mapping["job_id"] != report.job.id and mapping["token"] != old_token
    assert store.get_token_digest(mapping["job_id"]) == hash_token(mapping["token"])
    imported = store.report(mapping["job_id"])
    assert imported.job.source_origin == report.job.source_origin
    assert (
        imported.evidence == report.evidence
        and imported.policy_documents == report.policy_documents
    )
    assert imported.policy_claims == report.policy_claims and imported.reviews == report.reviews
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    assert source.report(report.job.id).job.id == report.job.id
    seam = SecuritySeam(ServerConfig(mode="remote"), store)

    def request(token):
        return Request(
            {
                "type": "http",
                "query_string": b"",
                "headers": [(b"authorization", ("Bearer " + token).encode())],
            }
        )

    with pytest.raises(HTTPException) as denied:
        seam.authorize_job_access(request(old_token), mapping["job_id"])
    assert denied.value.status_code == 403
    seam.authorize_job_access(request(mapping["token"]), mapping["job_id"])
    with store._transaction() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(outbox)) == 0


def test_explicit_import_refuses_tombstone_active_job_and_existing_mapping(store, tmp_path):
    source = JobStore(tmp_path / "local-json")
    active = queued()
    source.create_if_absent(active)
    mapping = tmp_path / "mapping.json"
    with pytest.raises(ValueError, match="Active"):
        import_records(source, store, [active.id], mapping)
    assert not mapping.exists() and store.list() == []
    source.delete(active.id)
    with pytest.raises(KeyError):
        import_records(source, store, [active.id], mapping)
    report = seed_job(source)
    mapping.write_bytes(b"previous operator credential mapping")
    with pytest.raises(FileExistsError):
        import_records(source, store, [report.job.id], mapping)
    assert mapping.read_bytes() == b"previous operator credential mapping"
    assert store.list() == []


def test_retry_cannot_overwrite_an_existing_postgres_scope(store):
    job = queued()
    job.state = "FAILED"
    store.create_if_absent(job, "a" * 64)
    existing = queued()
    store.create_if_absent(existing, "b" * 64)
    retry = queued(existing.id)
    retry.retry_of = job.id
    with pytest.raises(ValueError, match="identifier"):
        store.create_retry(retry, "a" * 64)
    assert store.get_token_digest(existing.id) == "b" * 64
    assert store.get(existing.id).retry_of is None
    retry.id = uuid4().hex
    store.create_retry(retry, "a" * 64)
    assert store.get(retry.id).retry_of == job.id
