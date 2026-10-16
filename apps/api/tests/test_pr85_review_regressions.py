"""Regression coverage for PR #85 review findings."""
import hashlib
import io
import logging
import uuid

from fastapi.testclient import TestClient

from privacytrace.main import create_app
from privacytrace.middleware import install_log_redaction
from privacytrace.models import AnalysisJob
from privacytrace.resources import taxonomy
from datetime import datetime, timezone


def draft_payload(name):
    return {"name": name, "sources": [{
        "id": "policy", "title": "Policy", "text": "We use location data.",
        "source_type": "OFFICIAL_WEB_POLICY",
    }]}


def test_remote_draft_credentials_persist_and_isolate(tmp_path):
    app = create_app(store_root=tmp_path, mode="remote")
    with TestClient(app) as client:
        first = client.post("/api/v1/web/drafts", json=draft_payload("A")).json()
        second = client.post("/api/v1/web/drafts", json=draft_payload("B")).json()
        identifier, token = first["id"], first["capability_token"]
        url = f"/api/v1/web/drafts/{identifier}"
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": f"Bearer {second['capability_token']}"}).status_code == 403
        authorized = {"Authorization": f"Bearer {token}"}
        assert client.get(url, headers=authorized).status_code == 200
        assert client.post(url + "/candidates", json={"revision": 1, "candidates": []}).status_code == 401
        assert client.post(url + "/candidates", headers={"Authorization": f"Bearer {second['capability_token']}"}, json={"revision": 1, "candidates": []}).status_code == 403
        saved = client.post(url + "/candidates", headers=authorized, json={"revision": 1, "candidates": []})
        assert saved.status_code == 200
        assert saved.json()["revision"] == 2
        assert client.get(url + "?token=" + token, headers=authorized).status_code == 400
        data = (tmp_path / "web" / identifier / "capability.json").read_text()
        assert token not in data
        assert hashlib.sha256(token.encode()).hexdigest() in data


def test_remote_draft_upload_authorization_and_job_inheritance(tmp_path, monkeypatch):
    app = create_app(store_root=tmp_path, mode="remote")
    # Stub scheduling to test authorization + persistence without running a real scan.
    class Finished:
        def done(self):
            return True
    monkeypatch.setattr(app.state.web_intake.executor, "submit", lambda *a, **k: Finished())
    with TestClient(app) as client:
        created = client.post("/api/v1/web/drafts", json=draft_payload("remote-upload")).json()
        identifier, token = created["id"], created["capability_token"]
        base = f"/api/v1/web/drafts/{identifier}"
        auth = {"Authorization": f"Bearer {token}"}
        assert client.post(base + "/apk", content=b"apk").status_code == 401
        uploaded = client.post(base + "/apk", headers=auth, content=b"apk")
        assert uploaded.status_code == 200
        revision = uploaded.json()["revision"]
        started = client.post(base + "/start", headers=auth, json={"revision": revision, "request_id": uuid.uuid4().hex})
        assert started.status_code == 200, started.text
        job_id = started.json()["id"]
        assert client.get(f"/api/v1/jobs/{job_id}", headers=auth).status_code == 200
        assert app.state.job_store.get_token_digest(job_id) == hashlib.sha256(token.encode()).hexdigest()
        assert client.get(f"/api/v1/jobs/{job_id}", headers={"Authorization": "Bearer " + "pt_cap_" + "a" * 43}).status_code == 403


def test_state_updates_preserve_capability_digest(tmp_path):
    from privacytrace.job_store import JobStore
    store = JobStore(tmp_path)
    job = AnalysisJob(id="token-job", sample_id="token-sample", input_mode="APK",
                      source_origin="REAL_SCAN", state="QUEUED", ruleset_version=taxonomy()["version"],
                      created_at=datetime.now(timezone.utc))
    store.create_if_absent(job, token_digest="a" * 64)
    for state in ("RUNNING", "FAILED"):
        job.state = state
        store.save_job(job)
        assert store.get_token_digest(job.id) == "a" * 64


def test_child_logger_reaches_new_handler_redacted():
    install_log_redaction()
    token = "pt_cap_" + "x" * 43
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s %(exc_text)s"))
    logger = logging.getLogger("third_party.pr85.secret")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("secret: %s", token)
        try:
            raise ValueError(token)
        except ValueError:
            logger.exception("bad %s", token)
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert token not in output
    assert "pt_cap_***" in output
