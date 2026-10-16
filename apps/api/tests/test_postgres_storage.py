"""Real PostgreSQL integration; no SQLite or database doubles satisfy these tests.

The explicitly supplied, disposable database name must end in _test. The two
URLs must use separately provisioned runtime and migration roles. Missing URLs
skip this module; supplied but broken URLs fail, never silently skip.
"""

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Event
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from test_capability_tokens import controlled_bundle, seed_job

from privacytrace.auth import generate_capability_token
from privacytrace.job_store import JobStore
from privacytrace.main import create_app
from privacytrace.postgres_schema import REVISION, SCHEMA, audit, documents, jobs, scopes
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.resources import ROOT
from privacytrace.runtime_models import ReviewRequest
from privacytrace.storage_seam import JobStorageProtocol


def migration(url, action="upgrade", target="head"):
    engine = sa.create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as conn:
            cfg = Config(str(ROOT / "apps/api/alembic.ini"))
            cfg.attributes["connection"] = conn
            if action == "check":
                command.check(cfg)
            else:
                getattr(command, action)(cfg, target)
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def postgres_urls():
    runtime = os.environ.get("PRIVACYTRACE_TEST_DATABASE_URL")
    migrator = os.environ.get("PRIVACYTRACE_TEST_MIGRATION_DATABASE_URL")
    if not runtime or not migrator:
        pytest.skip("Explicit disposable PostgreSQL runtime/migration URLs are required")
    rt, mg = sa.engine.make_url(runtime), sa.engine.make_url(migrator)
    assert rt.database and rt.database.endswith("_test"), "Use a disposable *_test database"
    assert (rt.host, rt.port, rt.database) == (mg.host, mg.port, mg.database)
    assert rt.username != mg.username, "Runtime and migration roles must differ"
    migration(migrator)
    return runtime, migrator


@pytest.fixture
def store(postgres_urls, tmp_path):
    value = PostgresJobStore(postgres_urls[0], str(uuid4()), tmp_path)
    yield value
    value.close()


@pytest.fixture
def postgres_app(postgres_urls, tmp_path, monkeypatch):
    instance = str(uuid4())
    monkeypatch.setenv("PRIVACYTRACE_STORAGE", "postgres")
    monkeypatch.setenv("PRIVACYTRACE_DATABASE_URL", postgres_urls[0])
    monkeypatch.setenv("PRIVACYTRACE_INSTANCE_ID", instance)

    def factory(instance_id=instance):
        monkeypatch.setenv("PRIVACYTRACE_INSTANCE_ID", instance_id)
        return create_app(tmp_path, mode="remote")

    return factory


def queued(job_id=None):
    job = controlled_bundle().job
    job.id = job_id or uuid4().hex
    job.state = "QUEUED"
    return job


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(params=["json", "postgres"])
def intake_app(request, tmp_path, monkeypatch):
    """Exercise shared intake fixes through both actual storage implementations."""
    if request.param == "postgres":
        return request.getfixturevalue("postgres_app")
    monkeypatch.setenv("PRIVACYTRACE_STORAGE", "json")
    return lambda: create_app(tmp_path, mode="remote")


def synthetic_scan(apk, **kwargs):
    # This is a scanner double, never evidence of an actual APK/container scan.
    return {
        "package_name": "org.privacytrace.fixture",
        "version_code": 1,
        "version_name": "1",
        "apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
        "permissions": [],
        "dex_entries": [],
        "evidence": [],
        "behaviors": [],
        "errors": [],
        "coverage": {
            "completeness": "COMPLETE", "limitations": [], "scanned_dex": [], "failed_dex": [],
        },
        "tools": {"scanner": "DETERMINISTIC_DOUBLE_NOT_A_SCAN"},
    }


def uploaded_draft(client):
    response = client.post(
        "/api/v1/web/drafts",
        json={
            "name": "stage1 regression fixture",
            "sources": [{"id": "host", "title": "fixture", "text": "Synthetic policy text."}],
        },
    )
    assert response.status_code == 200, response.text
    draft = response.json()
    path, headers = f"/api/v1/web/drafts/{draft['id']}", bearer(draft["token"])
    response = client.post(path + "/apk", headers=headers, content=b"synthetic registered APK")
    assert response.status_code == 200, response.text
    return response.json(), path, headers


def start_draft(client, draft, path, headers, request_id=None):
    response = client.post(
        path + "/start", headers=headers,
        json={"revision": draft["revision"], "request_id": request_id or uuid4().hex},
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["id"]
    return job_id, client.app.state.web_intake.futures[job_id]


def test_real_server_migrations_and_schema_drift(postgres_urls):
    migration(postgres_urls[1], "check")
    engine = sa.create_engine(postgres_urls[0], hide_parameters=True)
    try:
        with engine.connect() as conn:
            assert "PostgreSQL" in conn.execute(sa.text("SELECT version()")).scalar_one()
            assert (
                conn.execute(
                    sa.text(f"SELECT version_num FROM {SCHEMA}.alembic_version")
                ).scalar_one()
                == REVISION
            )
    finally:
        engine.dispose()


def test_report_review_and_credentials_survive_independent_process(store, postgres_urls):
    assert isinstance(store, JobStorageProtocol)
    token, digest = generate_capability_token()
    report = seed_job(store, digest)
    reviewed = store.review(
        report.job.id,
        ReviewRequest(
            actor="fixture",
            reason="persistence check",
            note="synthetic review event",
        ),
    )
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, os
from pathlib import Path
from privacytrace.postgres_store import PostgresJobStore
s = PostgresJobStore(os.environ['PRIVACYTRACE_TEST_DATABASE_URL'],
                    os.environ['PT_TEST_INSTANCE'], Path(os.environ['PT_TEST_ROOT']))
r = s.report(os.environ['PT_TEST_JOB'])
print(json.dumps({'report': r.model_dump(mode='json'),
                  'digest': s.get_token_digest(r.job.id)}))
s.close()
""",
        ],
        env={
            **os.environ,
            "PT_TEST_INSTANCE": store.instance_id,
            "PT_TEST_ROOT": str(store.root.parent.parent),
            "PT_TEST_JOB": report.job.id,
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    restored = json.loads(child.stdout)
    assert restored["report"] == reviewed.model_dump(mode="json")
    assert restored["digest"] == digest
    assert token not in child.stdout
    assert restored["report"]["delivery_mode"] == "PERSISTED_REPLAY"
    assert restored["report"]["job"]["source_origin"] == "CONTROLLED"


def test_transaction_rollback_leaves_no_job_or_audit(store):
    job = queued()
    with pytest.raises(RuntimeError, match="interrupt"):
        with store._transaction():
            store.create_if_absent(job)
            raise RuntimeError("interrupt before commit")
    with pytest.raises(KeyError):
        store.get(job.id)
    with store._transaction() as conn:
        assert (
            conn.execute(
                sa.select(audit.c.event_id).where(
                    audit.c.scope_id == job.id,
                )
            ).first()
            is None
        )


def test_two_connections_cannot_claim_same_job_or_replace_credential(store, postgres_urls):
    other = PostgresJobStore(postgres_urls[0], store.instance_id, store.root.parent.parent)
    barrier = Barrier(2)
    job = queued()
    credentials = [generate_capability_token()[1] for _ in range(2)]

    def create(candidate, digest):
        barrier.wait(timeout=10)
        try:
            candidate.create_if_absent(job, digest)
            return digest
        except ValueError:
            return None

    try:
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(create, s, d) for s, d in zip((store, other), credentials)]
            winners = [f.result(timeout=15) for f in futures]
        assert sum(w is not None for w in winners) == 1
        assert store.get_token_digest(job.id) == next(w for w in winners if w)
        assert len(store.list()) == 1
    finally:
        other.close()


def test_delete_racing_report_cannot_resurrect_and_purges_content(store, postgres_urls):
    bundle = controlled_bundle()
    token, digest = generate_capability_token()
    job = bundle.job.model_copy(update={"state": "QUEUED"})
    store.create_if_absent(job, digest)
    other = PostgresJobStore(postgres_urls[0], store.instance_id, store.root.parent.parent)
    barrier = Barrier(2)

    def publish():
        barrier.wait(timeout=10)
        try:
            seed_job(other)
        except ValueError:
            pass  # A tombstone won the race.

    def delete():
        barrier.wait(timeout=10)
        store.delete(job.id)

    try:
        with ThreadPoolExecutor(2) as pool:
            a, b = pool.submit(publish), pool.submit(delete)
            a.result(timeout=15)
            b.result(timeout=15)
        assert store.is_tombstoned(job.id)
        with pytest.raises(KeyError):
            other.report(job.id)
        with pytest.raises(KeyError):
            other.set_token_digest(job.id, digest)
        with pytest.raises(ValueError):
            other.create_if_absent(job, digest)
        other.save_job(bundle.job)
        assert store.is_tombstoned(job.id)
        with store._transaction() as conn:
            payload = conn.execute(sa.select(jobs.c.record)).scalar_one()
            assert payload["bundle"] is None and payload["reviews"] == []
            assert conn.execute(sa.select(scopes.c.token_digest)).scalar_one() is None
            assert token not in json.dumps(payload)
    finally:
        other.close()


def test_cancel_rejects_late_report_and_preserves_digest(store):
    job = controlled_bundle().job.model_copy(update={"state": "QUEUED"})
    digest = generate_capability_token()[1]
    store.create_if_absent(job, digest)
    store.cancel(job.id)
    with pytest.raises(ValueError, match="Cancelled"):
        seed_job(store)
    store.save_job(job.model_copy(update={"state": "SUCCEEDED"}))
    assert store.get(job.id).state == "CANCELLED"
    assert store.get_token_digest(job.id) == digest


def test_instances_have_distinct_db_rows_and_enforced_rls(store, postgres_urls, tmp_path):
    other = PostgresJobStore(postgres_urls[0], str(uuid4()), tmp_path)
    job = queued("same-visible-id")
    a, b = generate_capability_token()[1], generate_capability_token()[1]
    try:
        store.create_if_absent(job, a)
        other.create_if_absent(job, b)
        assert store.get_token_digest(job.id) == a
        assert other.get_token_digest(job.id) == b
        store.cancel(job.id)
        assert other.get(job.id).state == "QUEUED"
        with store._transaction() as conn:
            assert (
                conn.execute(
                    sa.select(jobs.c.job_id).where(
                        jobs.c.instance_id == other.instance_id,
                    )
                ).first()
                is None
            )
        with pytest.raises(ValueError, match="PostgreSQL storage rejected"):
            with store._transaction() as conn:
                conn.execute(
                    scopes.insert().values(
                        instance_id=other.instance_id,
                        scope_id="injected",
                        kind="JOB",
                        created_at=job.created_at,
                        tombstone=False,
                    )
                )
    finally:
        other.close()


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE privacytrace.forbidden (id integer)",
        "ALTER TABLE privacytrace.jobs ADD COLUMN forbidden integer",
        "DELETE FROM privacytrace.analysis_scopes",
        "UPDATE privacytrace.audit_events SET action = 'FORGED'",
        "UPDATE privacytrace.alembic_version SET version_num = 'forged'",
    ],
)
def test_runtime_cannot_migrate_remove_tombstones_or_rewrite_audit(store, statement):
    with pytest.raises(ValueError, match="PostgreSQL storage rejected"):
        with store._transaction() as conn:
            conn.execute(sa.text(statement))


def test_runtime_without_instance_context_sees_no_records(store):
    store.create_if_absent(queued())
    with store.engine.connect() as conn:
        assert conn.execute(sa.select(jobs.c.job_id)).first() is None


def test_schema_owner_is_rejected_for_runtime(postgres_urls, tmp_path):
    with pytest.raises(ValueError, match="restricted runtime role"):
        PostgresJobStore(postgres_urls[1], str(uuid4()), tmp_path)


@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("GET", "", None),
        ("GET", "/report", None),
        ("POST", "/cancel", None),
        ("DELETE", "", None),
        ("POST", "/reviews", {"actor": "fixture", "reason": "test"}),
    ],
)
def test_http_cross_job_credentials_rejected(postgres_app, method, suffix, payload):
    with TestClient(postgres_app()) as client:
        a = client.post("/api/v1/jobs").json()
        b = client.post("/api/v1/jobs").json()
        response = client.request(
            method, f"/api/v1/jobs/{b['id']}{suffix}", json=payload, headers=bearer(a["token"])
        )
        assert response.status_code == 403
        assert client.get(f"/api/v1/jobs/{b['id']}", headers=bearer(b["token"])).status_code == 200
        assert a["token"] not in response.text and b["token"] not in response.text


def test_http_restart_revocation_and_cross_instance(postgres_app):
    with TestClient(postgres_app()) as client:
        created = client.post("/api/v1/jobs").json()
    path = f"/api/v1/jobs/{created['id']}"
    with TestClient(postgres_app(str(uuid4()))) as other:
        assert other.get(path, headers=bearer(created["token"])).status_code == 404
    with TestClient(postgres_app()) as restarted:
        assert restarted.get(path).status_code == 401
        assert restarted.get(path, headers=bearer(created["token"])).status_code == 200
        assert restarted.delete(path, headers=bearer(created["token"])).status_code == 200
    with TestClient(postgres_app()) as final:
        assert final.get(path, headers=bearer(created["token"])).status_code == 404


def test_draft_materials_candidates_and_digest_persist_without_plaintext_db(postgres_app):
    text = "我们不会读取联系人。"
    with TestClient(postgres_app()) as client:
        draft = client.post(
            "/api/v1/web/drafts",
            json={
                "name": "synthetic policy persistence",
                "sources": [{"id": "host", "title": "fixture", "text": text}],
            },
        ).json()
        headers = bearer(draft["token"])
        path = f"/api/v1/web/drafts/{draft['id']}"
        changed = client.post(
            path + "/candidates",
            headers=headers,
            json={
                "revision": 1,
                "candidates": [
                    {
                        "id": "quote",
                        "source_id": "host",
                        "excerpt": text,
                        "data_type": "CONTACTS",
                        "polarity": "NEGATIVE",
                        "subject": "HOST_APP",
                        "checked": False,
                    }
                ],
            },
        )
        assert changed.status_code == 200, changed.text
        uploaded = client.post(path + "/apk", headers=headers, content=b"synthetic-upload-bytes")
        assert uploaded.status_code == 200, uploaded.text
    with TestClient(postgres_app()) as restarted:
        restored = restarted.get(path, headers=headers)
        assert restored.status_code == 200, restored.text
        assert restored.json()["revision"] == 3
        assert restored.json()["uploaded"] is True
        assert (
            restored.json()["apk_sha256"] == hashlib.sha256(b"synthetic-upload-bytes").hexdigest()
        )
        assert restored.json()["sources"][0]["text"] == text
        assert restored.json()["candidates"][0]["checked"] is False
        store = restarted.app.state.job_store
        with store._transaction() as conn:
            manifest = [dict(row) for row in conn.execute(sa.select(documents)).mappings()]
            scope = [dict(row) for row in conn.execute(sa.select(scopes)).mappings()]
            dumped = json.dumps([manifest, scope], default=str, ensure_ascii=False)
            assert text not in dumped and draft["token"] not in dumped
            assert store.draft_digest(draft["id"])


@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("GET", "", None),
        ("POST", "/apk", None),
        ("POST", "/sources/host/fetch", {"revision": 1}),
        ("POST", "/sources/host/extract", {"revision": 1}),
        ("POST", "/candidates", {"revision": 1, "candidates": []}),
        ("POST", "/start", {"revision": 1, "request_id": "a" * 32}),
    ],
)
def test_cross_draft_and_instance_access_rejected(postgres_app, method, suffix, payload):
    with TestClient(postgres_app()) as client:
        source = [{"id": "host", "title": "fixture", "text": "fixture only"}]
        a = client.post("/api/v1/web/drafts", json={"name": "a", "sources": source}).json()
        b = client.post("/api/v1/web/drafts", json={"name": "b", "sources": source}).json()
        path = f"/api/v1/web/drafts/{b['id']}"
        assert (
            client.request(
                method, path + suffix, json=payload, headers=bearer(a["token"])
            ).status_code
            == 403
        )
    with TestClient(postgres_app(str(uuid4()))) as other:
        assert other.get(path, headers=bearer(b["token"])).status_code == 404


def test_corrupted_material_rejected_and_uncommitted_pointer_cannot_replace_draft(postgres_app):
    with TestClient(postgres_app()) as client:
        draft = client.post(
            "/api/v1/web/drafts",
            json={
                "name": "committed",
                "sources": [{"id": "host", "title": "fixture"}],
            },
        ).json()
        store, intake = client.app.state.job_store, client.app.state.web_intake
        path = intake.directory(draft["id"]) / "current.json"
        with pytest.raises(RuntimeError):
            with store._transaction():
                intake._write_private(path, {**intake._get(draft["id"]), "name": "uncommitted"})
                raise RuntimeError("abort")
        assert intake.get(draft["id"])["name"] == "committed"
        reference = store.document(f"{draft['id']}/current.json")["material_ref"]
        (intake.materials / reference).write_bytes(b"tampered")
        response = client.get(f"/api/v1/web/drafts/{draft['id']}", headers=bearer(draft["token"]))
        assert response.status_code == 409
        assert "tampered" not in response.text


def test_rolled_back_revision_can_be_retried_and_orphan_directory_ignored(postgres_app):
    app = postgres_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/web/drafts",
            json={
                "name": "committed",
                "sources": [{"id": "host", "title": "fixture"}],
            },
        )
        assert response.status_code == 200, response.text
        draft = response.json()
        intake, store = app.state.web_intake, app.state.job_store
        value = intake.get(draft["id"])
        value.update(revision=2, name="retried")
        with pytest.raises(RuntimeError):
            with store._transaction():
                intake._save(value)
                raise RuntimeError("crash before committing revision")
        assert intake.get(draft["id"])["revision"] == 1
        with store._transaction():
            intake._save(value)
        assert intake.get(draft["id"])["name"] == "retried"
        # A filesystem entry alone is neither an authorized draft nor a recovery input.
        orphan = intake.root / uuid4().hex
        orphan.mkdir()
        (orphan / "current.json").write_text('{"private": "uncommitted"}')
    with TestClient(postgres_app()) as restarted:
        result = restarted.get(f"/api/v1/web/drafts/{draft['id']}", headers=bearer(draft["token"]))
        assert result.status_code == 200
        assert result.json()["name"] == "retried"


def test_real_tcp_http_api_crash_and_restart_preserve_authorization(postgres_urls, tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        "PRIVACYTRACE_STORAGE": "postgres",
        "PRIVACYTRACE_MODE": "remote",
        "PRIVACYTRACE_DATABASE_URL": postgres_urls[0],
        "PRIVACYTRACE_INSTANCE_ID": str(uuid4()),
        "PRIVACYTRACE_STORE_ROOT": str(tmp_path),
        "PRIVACYTRACE_ALLOWED_HOSTS": "127.0.0.1",
        "PYTHONUTF8": "1",
    }

    @contextmanager
    def server():
        with (tmp_path / "http-server.log").open("ab") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "privacytrace.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--no-access-log",
                ],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                    deadline = time.monotonic() + 15
                    while True:
                        assert process.poll() is None, "HTTP process failed; inspect test log"
                        try:
                            if client.get("/api/v1/health").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        assert time.monotonic() < deadline, "HTTP startup timed out"
                        time.sleep(0.05)
                    yield client
            finally:
                process.terminate()
                process.wait(timeout=10)

    with server() as client:
        created = client.post("/api/v1/jobs").json()
        path = f"/api/v1/jobs/{created['id']}"
        assert client.get(path, headers=bearer(created["token"])).status_code == 200
    with server() as restarted:
        assert restarted.get(path).status_code == 401
        assert restarted.get(path, headers=bearer(created["token"])).status_code == 200
        assert restarted.delete(path, headers=bearer(created["token"])).status_code == 200
        assert restarted.get(path, headers=bearer(created["token"])).status_code == 404
    assert created["token"] not in (tmp_path / "http-server.log").read_text(encoding="utf-8")


def test_local_json_and_old_capability_are_never_imported(postgres_app, tmp_path):
    local = JobStore(tmp_path)
    token, digest = generate_capability_token()
    report = seed_job(local, digest)
    path = tmp_path / f"{report.job.id}.json"
    original = path.read_bytes()
    with TestClient(postgres_app()) as remote:
        assert remote.get(f"/api/v1/jobs/{report.job.id}", headers=bearer(token)).status_code == 404
        assert remote.app.state.job_store.list() == []
    assert path.read_bytes() == original
    assert local.report(report.job.id).sample == report.sample


def test_existing_http_pipeline_publishes_to_postgres_not_a_shadow_json_store(
    postgres_app,
    monkeypatch,
):
    from privacytrace import pipeline

    def deterministic_scanner(apk, **kwargs):
        # Only the parser/runner is doubled; HTTP, intake, pipeline and PostgreSQL are real.
        return {
            "package_name": "org.privacytrace.fixture",
            "version_code": 1,
            "version_name": "1",
            "apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
            "permissions": [],
            "dex_entries": [],
            "evidence": [],
            "behaviors": [],
            "errors": [],
            "coverage": {
                "completeness": "COMPLETE",
                "limitations": [],
                "scanned_dex": [],
                "failed_dex": [],
            },
            "tools": {"scanner": "DETERMINISTIC_DOUBLE_NOT_A_SCAN"},
        }

    monkeypatch.setattr(pipeline, "scan_isolated", deterministic_scanner)
    with TestClient(postgres_app()) as client:
        draft = client.post(
            "/api/v1/web/drafts",
            json={
                "name": "synthetic storage integration",
                "sources": [{"id": "host", "title": "fixture", "text": "合成政策材料。"}],
            },
        ).json()
        headers = bearer(draft["token"])
        path = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(
            path + "/apk", headers=headers, content=b"synthetic APK bytes"
        ).json()
        started = client.post(
            path + "/start",
            headers=headers,
            json={
                "revision": uploaded["revision"],
                "request_id": uuid4().hex,
            },
        )
        assert started.status_code == 200, started.text
        job_id = started.json()["id"]
        client.app.state.web_intake.futures[job_id].result(timeout=15)
        response = client.get(f"/api/v1/jobs/{job_id}/report", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["job"]["state"] == "SUCCEEDED"
        assert response.json()["tools"]["scanner"] == "DETERMINISTIC_DOUBLE_NOT_A_SCAN"
        assert not (client.app.state.job_store.root / f"{job_id}.json").exists()
    with TestClient(postgres_app()) as restarted:
        response = restarted.get(f"/api/v1/jobs/{job_id}/report", headers=headers)
        assert response.status_code == 200
        assert response.json()["delivery_mode"] == "PERSISTED_REPLAY"


def test_migration_repeat_preserves_data_and_runtime_cannot_run_it(store, postgres_urls):
    job = queued()
    store.create_if_absent(job)
    migration(postgres_urls[1])
    assert store.get(job.id) == job
    with pytest.raises(RuntimeError, match="dedicated schema owner"):
        migration(postgres_urls[0])


def test_failed_registration_commit_never_launches_worker(postgres_app, monkeypatch):
    from privacytrace.web_models import StartInput

    app = postgres_app()
    with TestClient(app) as client:
        draft = client.post(
            "/api/v1/web/drafts",
            json={
                "name": "commit failure fixture",
                "sources": [{"id": "host", "title": "fixture", "text": "合成材料"}],
            },
        ).json()
        path = f"/api/v1/web/drafts/{draft['id']}"
        uploaded = client.post(
            path + "/apk", headers=bearer(draft["token"]), content=b"synthetic bytes"
        ).json()
        store, intake = app.state.job_store, app.state.web_intake
        original = store._transaction
        submissions = []

        def submit(*args, **kwargs):
            from concurrent.futures import Future

            submissions.append(True)
            future = Future()
            future.set_result(None)
            return future

        @contextmanager
        def fail_before_commit():
            outer = getattr(store._local, "connection", None) is None
            with original() as conn:
                yield conn
                if outer and conn.execute(sa.select(jobs.c.job_id)).first() is not None:
                    raise ValueError("injected registration commit failure")

        with monkeypatch.context() as patch:
            patch.setattr(store, "_transaction", fail_before_commit)
            patch.setattr(intake.executor, "submit", submit)
            with pytest.raises(ValueError, match="injected registration"):
                intake.start(
                    draft["id"],
                    StartInput(
                        revision=uploaded["revision"],
                        request_id=uuid4().hex,
                    ),
                )
        assert submissions == [], "Workers must not start for rolled-back registrations"
        assert store.list() == []
        assert intake.get(draft["id"])["jobs"] == []
        assert all(f.done() for f in intake.futures.values())


@pytest.mark.parametrize("operation", ["restart", "retry"])
def test_deleted_draft_job_does_not_block_recovery_or_retry(intake_app, monkeypatch, operation):
    from privacytrace import pipeline

    monkeypatch.setattr(pipeline, "scan_isolated", synthetic_scan)
    request_id = uuid4().hex
    with TestClient(intake_app()) as client:
        draft, path, headers = uploaded_draft(client)
        deleted_id, future = start_draft(client, draft, path, headers, request_id)
        future.result(timeout=15)
        job_path = f"/api/v1/jobs/{deleted_id}"
        assert client.delete(job_path, headers=headers).status_code == 200
        if operation == "retry":
            # Replaying the deleted submission never allocates a replacement credential/job.
            assert client.post(path + "/start", headers=headers, json={
                "revision": draft["revision"], "request_id": request_id,
            }).status_code == 404
            new_id, future = start_draft(client, draft, path, headers)
            future.result(timeout=15)
            assert new_id != deleted_id
            assert client.app.state.job_store.is_tombstoned(deleted_id)
    if operation == "restart":
        with TestClient(intake_app()) as restarted:
            assert restarted.get("/api/v1/health").status_code == 200
            assert restarted.get(path, headers=headers).status_code == 200
            assert restarted.get(job_path, headers=headers).status_code == 404
            new_id, future = start_draft(restarted, draft, path, headers)
            future.result(timeout=15)
            assert new_id != deleted_id


def test_deleted_inflight_job_finishes_without_resurrection(intake_app, monkeypatch):
    from privacytrace import pipeline

    entered, release = Event(), Event()

    def blocked_scan(apk, **kwargs):
        entered.set()
        assert release.wait(timeout=10), "Review fixture did not release scanner"
        return synthetic_scan(apk, **kwargs)

    monkeypatch.setattr(pipeline, "scan_isolated", blocked_scan)
    with TestClient(intake_app()) as client:
        draft, path, headers = uploaded_draft(client)
        job_id, future = start_draft(client, draft, path, headers)
        try:
            assert entered.wait(timeout=10)
            assert client.delete(f"/api/v1/jobs/{job_id}", headers=headers).status_code == 200
        finally:
            release.set()
        future.result(timeout=15)
        assert client.app.state.job_store.is_tombstoned(job_id)
        assert client.get(f"/api/v1/jobs/{job_id}/report", headers=headers).status_code == 404


def test_upload_commit_failure_releases_owned_pending_file(
    postgres_app, postgres_urls, monkeypatch,
):
    """A deferred FK is rejected by PostgreSQL COMMIT itself, not a fake transaction."""
    probe = f"{SCHEMA}.commit_probe_{uuid4().hex}"
    migrator = sa.create_engine(postgres_urls[1], hide_parameters=True)
    role = migrator.dialect.identifier_preparer.quote(
        sa.engine.make_url(postgres_urls[0]).username
    )
    with migrator.begin() as conn:
        conn.execute(sa.text(
            f"CREATE TABLE {probe} (instance_id varchar(36), scope_id varchar(100), "
            f"FOREIGN KEY (instance_id, scope_id) REFERENCES {SCHEMA}.analysis_scopes "
            "DEFERRABLE INITIALLY DEFERRED)"
        ))
        conn.execute(sa.text(f"GRANT INSERT ON {probe} TO {role}"))
    opened, states = [], []
    try:
        with TestClient(postgres_app()) as client:
            response = client.post("/api/v1/web/drafts", json={
                "name": "commit failure", "sources": [{"id": "host", "title": "fixture"}],
            })
            assert response.status_code == 200, response.text
            draft = response.json()
            intake, store = client.app.state.web_intake, client.app.state.job_store
            pending = intake.directory(draft["id"]) / "upload.pending"
            original_open, armed = os.open, True

            def track_open(path, *args, **kwargs):
                fd = original_open(path, *args, **kwargs)
                if path == pending:
                    opened.append(fd)
                return fd

            def defer_invalid_reference(conn):
                nonlocal armed
                if armed and opened:
                    armed = False
                    conn.execute(sa.text(f"INSERT INTO {probe} VALUES (:instance, :scope)"), {
                        "instance": store.instance_id, "scope": "nonexistent-review-scope",
                    })

            def record_commit_error(context):
                states.append(getattr(context.original_exception, "sqlstate", None))

            sa.event.listen(store.engine, "commit", defer_invalid_reference)
            sa.event.listen(store.engine, "handle_error", record_commit_error)
            try:
                with monkeypatch.context() as patch:
                    patch.setattr(os, "open", track_open)
                    response = client.post(
                        f"/api/v1/web/drafts/{draft['id']}/apk",
                        headers=bearer(draft["token"]), content=b"first upload",
                    )
                assert response.status_code == 409
                assert states == ["23503"], "The server must reject the deferred FK at COMMIT"
                assert not pending.exists(), "Failed COMMIT must release this upload reservation"
                for fd in opened:
                    with pytest.raises(OSError):
                        os.fstat(fd)
                response = client.post(
                    f"/api/v1/web/drafts/{draft['id']}/apk",
                    headers=bearer(draft["token"]), content=b"retried upload",
                )
                assert response.status_code == 200, response.text
                assert response.json()["apk_sha256"] == hashlib.sha256(
                    b"retried upload"
                ).hexdigest()
            finally:
                sa.event.remove(store.engine, "commit", defer_invalid_reference)
                sa.event.remove(store.engine, "handle_error", record_commit_error)
                for fd in opened:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                pending.unlink(missing_ok=True)
    finally:
        with migrator.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE {probe}"))
        migrator.dispose()


@pytest.mark.parametrize("tamper_at", ["before_start", "during_scan"])
def test_registered_apk_digest_mismatch_never_publishes(intake_app, monkeypatch, tamper_at):
    from privacytrace import pipeline

    def changed_input_scan(apk, **kwargs):
        if tamper_at == "during_scan":
            apk.write_bytes(b"different synthetic APK after registration")
        return synthetic_scan(apk, **kwargs)

    monkeypatch.setattr(pipeline, "scan_isolated", changed_input_scan)
    with TestClient(intake_app()) as client:
        draft, path, headers = uploaded_draft(client)
        if tamper_at == "before_start":
            apk = client.app.state.web_intake.directory(draft["id"]) / "input.apk"
            apk.write_bytes(b"different synthetic APK before start")
        job_id, future = start_draft(client, draft, path, headers)
        future.result(timeout=15)
        response = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["state"] == "FAILED"
        assert json.loads(response.json()["error"])["code"] == "INPUT_DIGEST_MISMATCH"
        assert client.get(f"/api/v1/jobs/{job_id}/report", headers=headers).status_code == 409
        assert client.get(path, headers=headers).json()["apk_sha256"] == draft["apk_sha256"]


def test_rejected_upload_does_not_remove_another_reservation(intake_app):
    with TestClient(intake_app()) as client:
        response = client.post("/api/v1/web/drafts", json={
            "name": "existing upload", "sources": [{"id": "host", "title": "fixture"}],
        })
        assert response.status_code == 200, response.text
        draft = response.json()
        pending = client.app.state.web_intake.directory(draft["id"]) / "upload.pending"
        pending.write_bytes(b"another upload owns these bytes")
        response = client.post(
            f"/api/v1/web/drafts/{draft['id']}/apk",
            headers=bearer(draft["token"]), content=b"rejected duplicate upload",
        )
        assert response.status_code == 409
        assert pending.read_bytes() == b"another upload owns these bytes"


def test_unknown_job_reference_is_not_silently_treated_as_deleted(intake_app):
    with TestClient(intake_app()) as client:
        draft, path, headers = uploaded_draft(client)
        intake = client.app.state.web_intake
        with intake.data_store._transaction():
            stored = intake._get(draft["id"])
            stored["jobs"].append({
                "job_id": uuid4().hex, "request_id": uuid4().hex,
                "revision": draft["revision"], "events": [],
            })
            intake._write_private(intake.directory(draft["id"]) / "current.json", stored)
        response = client.post(path + "/start", headers=headers, json={
            "revision": draft["revision"], "request_id": uuid4().hex,
        })
        assert response.status_code == 404
        assert client.app.state.job_store.list() == []


def test_explicit_downgrade_and_fresh_upgrade(postgres_urls, tmp_path):
    # This module opts into a disposable *_test database; no production DSN is accepted.
    migration(postgres_urls[1], "downgrade", "base")
    try:
        with pytest.raises(ValueError, match="schema version"):
            PostgresJobStore(postgres_urls[0], str(uuid4()), tmp_path)
    finally:
        migration(postgres_urls[1])
    migration(postgres_urls[1], "check")
