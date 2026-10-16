"""HTTP and concurrent lifecycle regressions for the final PR85 review."""

import asyncio
import io
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from privacytrace import middleware, web_intake
from privacytrace.config import ServerConfig
from privacytrace.main import create_app
from privacytrace.middleware import RateLimiter, install_log_redaction
from privacytrace.policy_llm_extractor import MockLLMClient
from privacytrace.web_models import ModelSettings


def draft_payload():
    return {"name": "active", "sources": [
        {"id": "policy", "title": "Policy", "url": "https://example.com/privacy",
         "text": "We use location."},
    ]}


@pytest.mark.parametrize("operation", ["fetch", "extract"])
@pytest.mark.parametrize("fails", [False, True])
def test_cleanup_preserves_long_operations(tmp_path, monkeypatch, operation, fails):
    entered, release = threading.Event(), threading.Event()

    def external_call(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        if fails:
            raise ValueError("external failure")
        return {"status": "manual", "text": "We use location."} if operation == "fetch" else "[]"

    monkeypatch.setattr(web_intake, "fetch_policy", external_call)
    monkeypatch.setattr(web_intake, "UrllibLLMClient", lambda **kw: MockLLMClient(external_call))
    app = create_app(tmp_path, mode="remote")
    with TestClient(app) as client, ThreadPoolExecutor() as executor:
        service = app.state.web_intake
        service.configure(ModelSettings(enabled=True, api_base="http://127.0.0.1/v1", model="test"))
        draft = client.post("/api/v1/web/drafts", json=draft_payload()).json()
        path = tmp_path / "web" / draft["id"] / "current.json"
        endpoint = f"/api/v1/web/drafts/{draft['id']}/sources/policy/{operation}"
        future = executor.submit(client.post, endpoint, json={"revision": 1},
                                 headers={"Authorization": f"Bearer {draft['token']}"})
        try:
            assert entered.wait(5)
            # Even an operation running beyond the TTL must retain its inputs.
            old = time.time() - service.DRAFT_TTL_SECONDS - 60
            os.utime(path, (old, old))
            response = client.post("/api/v1/web/drafts", json=draft_payload())
            assert response.status_code == 200
            assert path.exists()
        finally:
            release.set()
        expected = 409 if fails and operation == "fetch" else 200
        assert future.result(timeout=10).status_code == expected
        # A completed or failed operation counts as recent activity.
        assert path.stat().st_mtime > old
        # Once idle, both successful and failed drafts can be reclaimed.
        os.utime(path, (old, old))
        assert client.post("/api/v1/web/drafts", json=draft_payload()).status_code == 200
        assert not path.exists()


def test_authorized_read_refreshes_idle_ttl(tmp_path):
    app = create_app(tmp_path, mode="remote")
    with TestClient(app) as client:
        draft = client.post("/api/v1/web/drafts", json=draft_payload()).json()
        path = tmp_path / "web" / draft["id"] / "current.json"
        old = time.time() - app.state.web_intake.DRAFT_TTL_SECONDS - 60
        os.utime(path, (old, old))
        url = f"/api/v1/web/drafts/{draft['id']}"
        response = client.get(url, headers={"Authorization": f"Bearer {draft['token']}"})
        assert response.status_code == 200
        client.post("/api/v1/web/drafts", json=draft_payload())
        assert path.exists()


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "GET"])
@pytest.mark.parametrize("declared", [False, True])
def test_all_remote_bodies_bounded_before_parsing(tmp_path, method, declared):
    app = create_app(tmp_path, config=ServerConfig(mode="remote", max_json_body_bytes=16))
    consumed = []

    async def run():
        async def chunks():
            for _ in range(10):
                consumed.append(1)
                yield b"x" * 12

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                     base_url="http://testserver") as client:
            headers = {"Content-Length": "120"} if declared else {}
            return await client.request(method, "/api/v1/consistency/evaluate",
                                        content=chunks(), headers=headers)

    response = asyncio.run(run())
    assert response.status_code == 413
    assert len(consumed) == (0 if declared else 2)


@pytest.mark.parametrize("method, path, expected", [
    ("POST", "/api/v1/web/settings", 403),
    ("POST", "/api/v1/web/settings/", 403),
    ("POST", "/api/v1/web/drafts/" + "a" * 32 + "/candidates", 401),
    ("POST", "/api/v1/jobs/unknown/reviews", 401),
    ("GET", "/api/v1/jobs", 403),
])
def test_rejection_precedes_body_consumption(tmp_path, method, path, expected):
    app = create_app(tmp_path, mode="remote")
    consumed = []

    async def run():
        async def chunks():
            consumed.append(True)
            yield b"not valid json"

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                     base_url="http://testserver") as client:
            return await client.request(method, path, content=chunks())

    assert asyncio.run(run()).status_code == expected
    assert not consumed


def test_custom_repr_never_reaches_handler_unredacted():
    install_log_redaction()
    token = "pt_cap_" + "r" * 43

    class Sensitive:
        def __str__(self):
            return "innocent"

        def __repr__(self):
            return token

    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(message)s %(payload)r"))
    logger = logging.getLogger("third_party.final_pr85")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        logger.info("%r", Sensitive(), extra={"payload": {"object": Sensitive()}})
    finally:
        logger.removeHandler(handler)
    assert token not in output.getvalue()


def test_limiter_client_table_is_bounded_and_expires(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(middleware.time, "monotonic", lambda: clock[0])
    limiter = RateLimiter(2)
    limiter.max_clients = 2
    assert limiter.is_allowed("client-a")
    assert limiter.is_allowed("client-b")
    assert not limiter.is_allowed("client-c")
    assert limiter.is_allowed("client-a")
    assert not limiter.is_allowed("client-a")
    assert len(limiter.history) == 2
    clock[0] = 61.0
    assert limiter.is_allowed("client-c")
    assert list(limiter.history) == ["client-c"]


def test_invalid_transport_and_rate_limit_reject_before_reading_body(tmp_path):
    app = create_app(tmp_path, config=ServerConfig(mode="remote", rate_limit_per_minute=1))
    consumed = []

    async def run():
        async def chunks():
            consumed.append(True)
            yield b"not json"

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                     base_url="http://testserver") as client:
            invalid = await client.post("/api/v1/consistency/evaluate", content=chunks(),
                                        headers={"Host": "untrusted.example"})
            assert invalid.status_code == 400
            assert (await client.get("/api/v1/health")).status_code == 200
            limited = await client.post("/api/v1/consistency/evaluate", content=chunks())
            assert limited.status_code == 429

    asyncio.run(run())
    assert not consumed


@pytest.mark.parametrize("body", [b"not json", b"[]", b"null", b'"text"',
                                  b'{"input_mode":"invalid"}', b'{"sample_id":[]}'])
def test_invalid_job_creation_never_allocates_storage(tmp_path, body):
    with TestClient(create_app(tmp_path, mode="remote"), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/jobs", content=body)
        assert response.status_code == 422
        assert not list(tmp_path.glob("*.json"))


def test_job_storage_quota_reports_conflict_and_keeps_tombstones(tmp_path):
    app = create_app(tmp_path, mode="remote")
    app.state.job_store.MAX_RECORDS = 1
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post("/api/v1/jobs", json={}).json()
        url = f"/api/v1/jobs/{created['id']}"
        auth = {"Authorization": f"Bearer {created['token']}"}
        assert client.delete(url, headers=auth).status_code == 200
        assert client.get(url, headers=auth).status_code == 404
        response = client.post("/api/v1/jobs", json={})
        assert response.status_code == 409
        assert app.state.job_store.is_tombstoned(created["id"])
