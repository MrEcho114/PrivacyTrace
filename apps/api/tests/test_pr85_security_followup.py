"""Security regressions for the second PR #85 review round."""

import hashlib
import io
import logging
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from privacytrace import pipeline, web_intake
from privacytrace.main import create_app
from privacytrace.middleware import install_log_redaction
from privacytrace.models import AnalysisJob
from privacytrace.resources import taxonomy


def payload(name="bounded"):
    return {
        "name": name,
        "sources": [{
            "id": "privacy",
            "title": "Privacy policy",
            "text": "We use location data.",
        }],
    }


def create_draft(client, name="bounded", headers=None):
    response = client.post("/api/v1/web/drafts", json=payload(name), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def bearer(draft):
    return {"Authorization": f"Bearer {draft['capability_token']}"}


def test_remote_draft_per_client_quota_and_idle_recovery(tmp_path):
    app = create_app(store_root=tmp_path, mode="remote")
    with TestClient(app) as client:
        first = create_draft(client, "first")
        create_draft(client, "second")
        create_draft(client, "third")
        # A spent draft budget is a capacity boundary, not an input rejection:
        # the caller gets 429 with a machine code so it can retry deliberately.
        refused = client.post("/api/v1/web/drafts", json=payload("fourth"))
        assert refused.status_code == 429, refused.text
        assert refused.json()["detail"] == "CLIENT_DRAFT_QUOTA_REACHED"

        # A different real client identity still has its own allocation.
        distinct = {"X-Forwarded-For": "203.0.113.42"}
        create_draft(client, "another-client", headers=distinct)

        # Lazy TTL cleanup happens on the next creation; no scheduler is required.
        app.state.web_intake.DRAFT_TTL_SECONDS = 60
        old = time.time() - 120
        path = tmp_path / "web" / first["id"] / "current.json"
        os.utime(path, (old, old))
        create_draft(client, "reclaimed")
        assert not path.exists()


def test_cleanup_does_not_delete_active_job_inputs(tmp_path):
    app = create_app(store_root=tmp_path, mode="remote")
    with TestClient(app) as client:
        draft = create_draft(client, "active")
        job = AnalysisJob(
            id=uuid4().hex,
            sample_id="active",
            input_mode="APK",
            source_origin="REAL_SCAN",
            state="STATIC_ANALYSIS",
            ruleset_version=taxonomy()["version"],
            created_at=datetime.now(timezone.utc),
        )
        app.state.job_store.create_if_absent(job)
        path = tmp_path / "web" / draft["id"] / "current.json"
        current = app.state.web_intake.get(draft["id"])
        current["jobs"] = [{
            "job_id": job.id,
            "request_id": uuid4().hex,
            "revision": 1,
            "events": [],
        }]
        web_intake.write_private(path, current)
        app.state.web_intake.DRAFT_TTL_SECONDS = 60
        old = time.time() - 120
        os.utime(path, (old, old))
        create_draft(client, "trigger-cleanup")
        assert path.exists()


def test_remote_oversize_stream_returns_413_and_cleans_pending(tmp_path, monkeypatch):
    # Small limit exercises the actual streaming guard without allocating 150 MiB.
    monkeypatch.setattr(web_intake, "MAX_INPUT", 12)
    app = create_app(store_root=tmp_path, mode="remote")
    with TestClient(app) as client:
        draft = create_draft(client)
        endpoint = f"/api/v1/web/drafts/{draft['id']}/apk"
        assert client.post(endpoint, content=b"x" * 24).status_code == 401
        assert client.post(
            endpoint,
            headers=bearer(draft),
            content=b"x" * 24,
        ).status_code == 413
        directory = tmp_path / "web" / draft["id"]
        assert not (directory / "upload.pending").exists()
        assert not (directory / "input.apk").exists()
        assert client.post(
            endpoint,
            headers=bearer(draft),
            content=b"small apk",
        ).status_code == 200


def test_nested_non_string_and_extra_fields_redacted_at_handler():
    install_log_redaction()
    install_log_redaction()  # Installation must be idempotent.
    token = "pt_cap_" + "x" * 43
    out = io.StringIO()
    handler = logging.StreamHandler(out)
    handler.setFormatter(logging.Formatter("%(message)s %(payload)s"))
    logger = logging.getLogger("third_party.pr85.structured")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        logger.info(
            {"nested": {"credentials": [token]}},
            extra={"payload": {"authorization": token}},
        )
        logger.info("payload: %s", {"nested": [{"credential": token}]},
                    extra={"payload": [token]})
        try:
            raise RuntimeError(token)
        except RuntimeError:
            logger.exception("trace", extra={"payload": (token,)})
    finally:
        logger.removeHandler(handler)
    logged = out.getvalue()
    assert token not in logged
    assert "pt_cap_***" in logged


def test_remote_real_worker_lifecycle_and_report_access(tmp_path, monkeypatch):
    """Keep HTTP, executor, pipeline.run, state changes and JobStore real.

    Only the isolated APK scanner is replaced by a deterministic bounded result.
    """
    def fake_scan(apk, **kwargs):
        raw = apk.read_bytes()
        return {
            "package_name": "org.privacytrace.test",
            "version_name": "1.0",
            "version_code": 1,
            "apk_sha256": hashlib.sha256(raw).hexdigest(),
            "permissions": [],
            "dex_entries": [],
            "evidence": [],
            "behaviors": [],
            "coverage": {
                "completeness": "COMPLETE",
                "limitations": [],
                "scanned_dex": [],
                "failed_dex": [],
            },
            "tools": {},
        }

    monkeypatch.setattr(pipeline, "scan_isolated", fake_scan)
    app = create_app(store_root=tmp_path, mode="remote")
    with TestClient(app) as client:
        draft = create_draft(client, "remote-lifecycle")
        other = create_draft(client, "unrelated")
        base = f"/api/v1/web/drafts/{draft['id']}"
        upload = client.post(base + "/apk", headers=bearer(draft), content=b"sample apk")
        assert upload.status_code == 200, upload.text
        start = client.post(
            base + "/start",
            headers=bearer(draft),
            json={"revision": upload.json()["revision"], "request_id": uuid4().hex},
        )
        assert start.status_code == 200, start.text
        job_id = start.json()["id"]
        app.state.web_intake.futures[job_id].result(timeout=10)
        endpoint = f"/api/v1/jobs/{job_id}/report"
        report = client.get(endpoint, headers=bearer(draft))
        assert report.status_code == 200, report.text
        assert report.json()["job"]["state"] == "SUCCEEDED"
        assert client.get(endpoint).status_code == 401
        assert client.get(endpoint, headers=bearer(other)).status_code == 403
        stored_digest = app.state.job_store.get_token_digest(job_id)
        assert stored_digest == hashlib.sha256(
            draft["capability_token"].encode()
        ).hexdigest()
        # Expiration reclaims draft inputs, not the published JobStore report.
        app.state.web_intake.DRAFT_TTL_SECONDS = 60
        current = tmp_path / "web" / draft["id"] / "current.json"
        old = time.time() - 120
        os.utime(current, (old, old))
        create_draft(client, "trigger-prune")
        assert not current.exists()
        assert client.get(endpoint, headers=bearer(draft)).status_code == 200
