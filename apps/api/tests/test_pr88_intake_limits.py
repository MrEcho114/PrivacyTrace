"""Bounded HTTP intake regressions; APKs and metadata doubles are synthetic."""

import asyncio
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from queue import Queue
from types import SimpleNamespace
from uuid import uuid4

import anyio
import pytest
from apk_fixture_builder import apk, package_set_archive
from fastapi.testclient import TestClient
from test_web_intake import HEADERS, new_draft

from privacytrace import apk_worker, pipeline, web_intake
from privacytrace.main import create_app
from privacytrace.package_set import validate_package_set
from privacytrace.resources import taxonomy
from privacytrace.web_intake import InspectionBusy, UploadTimedOut


def scan_fixture_set(path, *, inventory=False, **kwargs):
    package_set = validate_package_set(path)
    return apk_worker.scan_package_set(
        path / package_set.base.file_name,
        [(s.split_name, path / s.file_name) for s in package_set.splits],
        taxonomy(), inventory=inventory,
    )


def test_discovery_and_upload_share_admission_without_blocking_readers(tmp_path, monkeypatch):
    entered, release = Queue(), threading.Event()

    def metadata(path, *, timeout):
        entered.put(path)
        assert release.wait(5)
        return {"policy_urls": []}

    app = create_app(tmp_path)
    service = app.state.web_intake
    monkeypatch.setattr(service, "INSPECTION_WAIT_SECONDS", 0.02)
    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as workers:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        assert client.post(route + "/apk", headers=HEADERS, content=b"fixture").status_code == 200
        other = new_draft(client)
        try:
            first = workers.submit(client.post, route + "/sources/discover", headers=HEADERS)
            entered.get(timeout=2)
            second = workers.submit(client.post, route + "/sources/discover", headers=HEADERS)
            entered.get(timeout=2)
            for endpoint in (route + "/sources/discover",
                             f"/api/v1/web/drafts/{other['id']}/apk"):
                response = client.post(endpoint, headers=HEADERS, content=b"fixture")
                assert response.status_code == 503
                assert response.json()["detail"] == "INSPECTION_CAPACITY_BUSY"
                assert response.headers["Retry-After"] == "15"
            assert entered.empty()
            assert client.get(route).status_code == 200
        finally:
            release.set()
        assert first.result(timeout=3).status_code == 200
        assert second.result(timeout=3).status_code == 200
        # A later upload proves rejection and completion both release admission.
        response = client.post(
            f"/api/v1/web/drafts/{other['id']}/apk", headers=HEADERS, content=b"fixture"
        )
        assert response.status_code == 200
        assert not service.active_drafts


@pytest.mark.usefixtures("synthetic_package_metadata")
@pytest.mark.parametrize("with_split", [False, True])
def test_discovery_deadline_is_shared_across_splits_and_does_not_commit_partial_results(
    tmp_path, monkeypatch, with_split
):
    base = apk(tmp_path / "base.apk")
    split = apk(tmp_path / "split.apk", split=True, split_name="feature")
    files = {base.name: base.read_bytes()}
    if with_split:
        files[split.name] = split.read_bytes()
    archive = package_set_archive(tmp_path / "set.zip", files)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        assert client.post(
            route + "/package-set", headers=HEADERS, content=archive.read_bytes()
        ).status_code == 200
        before = client.get(route).json()
        calls = []

        def metadata(path, *, timeout):
            calls.append(timeout)
            threading.Event().wait(0.03)
            return {"policy_urls": ["https://example.com/partial"]}

        monkeypatch.setattr(app.state.web_intake, "INSPECTION_BUDGET_SECONDS", 0.01)
        monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)
        response = client.post(route + "/sources/discover", headers=HEADERS)
        assert response.status_code == 503
        assert calls == [1]
        assert client.get(route).json() == before
        assert not app.state.web_intake.active_drafts


@pytest.mark.parametrize("worker_truncated", [False, True])
def test_discovery_exposes_worker_and_draft_truncation(tmp_path, monkeypatch, worker_truncated):
    note = "Discovered policy URLs truncated at 8; additional candidate URLs omitted."
    urls = [f"https://example.com/{i}" for i in range(8)]
    metadata = {
        "policy_urls": urls, "coverage": {"limitations": [note] if worker_truncated else []}
    }
    monkeypatch.setattr(web_intake, "inspect_package_isolated", lambda *a, **kw: metadata)
    with TestClient(create_app(tmp_path)) as client:
        draft = new_draft(client)  # Existing sources consume two of the eight slots.
        route = f"/api/v1/web/drafts/{draft['id']}"
        assert client.post(route + "/apk", headers=HEADERS, content=b"fixture").status_code == 200
        response = client.post(route + "/sources/discover", headers=HEADERS)
        assert response.status_code == 200
        result = response.json()
        assert len(result["sources"]) == 8
        assert any("Draft source limit" in item for item in result["limitations"])
        assert (note in result["limitations"]) is worker_truncated
        found = [s for s in result["sources"] if s["provenance"] == "MANIFEST_METADATA"]
        assert all(s["status"] == "url_only" and not s["text"] for s in found)


def test_slow_stream_times_out_cleans_staging_and_allows_retry(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    service = app.state.web_intake
    draft = service.create(web_intake.DraftInput(name="fixture", sources=[
        {"id": "s1", "title": "Fixture"}
    ]))
    upload_timeout = service.UPLOAD_TIMEOUT_SECONDS
    monkeypatch.setattr(service, "UPLOAD_TIMEOUT_SECONDS", 0.01)

    class SlowStream:
        async def stream(self):
            yield b"first chunk"
            await asyncio.sleep(1)
            yield b"too late"

    class CompleteStream:
        async def stream(self):
            yield b"complete"

    async def run():
        with pytest.raises(UploadTimedOut):
            await service.upload(draft["id"], SlowStream())
        directory = service.directory(draft["id"])
        assert not list(directory.glob("*pending*"))
        assert not service.get(draft["id"])["uploaded"]
        assert not service.active_drafts
        monkeypatch.setattr(service, "UPLOAD_TIMEOUT_SECONDS", upload_timeout)
        assert (await service.upload(draft["id"], CompleteStream()))["uploaded"]

    try:
        asyncio.run(run())
    finally:
        service.close()


@pytest.mark.parametrize("endpoint", ["apk", "package-set"])
def test_upload_timeout_has_distinct_http_status(tmp_path, monkeypatch, endpoint):
    app = create_app(tmp_path)

    async def timed_out(*args, **kwargs):
        raise UploadTimedOut("UPLOAD_TIMEOUT")

    monkeypatch.setattr(app.state.web_intake, "upload", timed_out)
    with TestClient(app) as client:
        draft = new_draft(client)
        response = client.post(
            f"/api/v1/web/drafts/{draft['id']}/{endpoint}", headers=HEADERS, content=b"fixture"
        )
        assert response.status_code == 408
        assert response.json()["detail"] == "UPLOAD_TIMEOUT"


@pytest.mark.usefixtures("synthetic_package_metadata")
@pytest.mark.parametrize("length", [200, 201, 255])
def test_long_split_name_survives_upload_scan_and_report(tmp_path, monkeypatch, length):
    split_name = "x" * length
    base = apk(tmp_path / "base.apk")
    split = apk(tmp_path / "split.apk", split=True, split_name=split_name)
    archive = package_set_archive(
        tmp_path / "set.zip", {base.name: base.read_bytes(), split.name: split.read_bytes()}
    )
    # Only controlled fixture bytes are parsed in this HTTP contract test.
    monkeypatch.setattr(pipeline, "scan_isolated", scan_fixture_set)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        upload = client.post(route + "/package-set", headers=HEADERS, content=archive.read_bytes())
        assert upload.status_code == 200, upload.text
        directory = app.state.web_intake.directory(draft["id"])
        assert os.path.samefile(directory / "input.apk", directory / "packages" / "base.apk")
        job = client.post(route + "/start", headers=HEADERS, json={
            "revision": upload.json()["revision"], "request_id": uuid4().hex,
        }).json()
        app.state.web_intake.futures[job["id"]].result(timeout=10)
        assert app.state.job_store.get(job["id"]).state == "SUCCEEDED"
        report = app.state.job_store.report(job["id"])
        assert any(item.package_split == split_name for item in report.evidence)
        assert split_name in report.sample.package_set.split_names


def test_inventory_keeps_identical_call_sites_from_each_package(tmp_path):
    packages = tmp_path / "packages"
    packages.mkdir()
    apk(packages / "base.apk", kind="android_id")
    apk(packages / "split.apk", split=True, split_name="feature", kind="android_id")
    result = scan_fixture_set(packages, inventory=True)
    calls = json.loads(result["tools"]["unmapped_android_invokes"])
    assert len(calls) == 2
    assert {item["dex"] for item in calls} == {"base:classes.dex", "split:feature:classes.dex"}
    assert len({(item["caller"], item["offset_bytes"]) for item in calls}) == 1


@pytest.mark.usefixtures("synthetic_package_metadata")
def test_failed_base_link_preserves_preexisting_input(tmp_path):
    sample = apk(tmp_path / "base.apk")
    with TestClient(create_app(tmp_path / "jobs")) as client:
        draft = new_draft(client)
        service = client.app.state.web_intake
        directory = service.directory(draft["id"])
        existing = directory / "input.apk"
        existing.write_bytes(b"existing material")
        response = client.post(
            f"/api/v1/web/drafts/{draft['id']}/package-set",
            headers=HEADERS, content=sample.read_bytes(),
        )
        assert response.status_code == 409
        assert existing.read_bytes() == b"existing material"
        assert not (directory / "packages").exists()
        assert not list(directory.glob("*pending*"))
        assert not service.get(draft["id"])["uploaded"]


@pytest.mark.parametrize("cancel_kind", ["anyio", "asyncio", "asyncio-repeated"])
def test_cancelled_discovery_holds_admission_until_worker_finishes(
    tmp_path, monkeypatch, cancel_kind
):
    entered, release = Queue(), threading.Event()
    app = create_app(tmp_path)
    service = app.state.web_intake
    draft = service.create(web_intake.DraftInput(name="fixture", sources=[
        {"id": "s1", "title": "Fixture"}
    ]))
    (service.directory(draft["id"]) / "input.apk").write_bytes(b"fixture")
    monkeypatch.setattr(service, "INSPECTION_WAIT_SECONDS", 0.02)

    def metadata(path, *, timeout):
        entered.put(path)
        assert release.wait(5)
        return {"policy_urls": []}

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)

    async def run():
        scopes = []
        completed = []

        async def discover():
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                await service.discover_sources(draft["id"])
                completed.append(scope)

        tasks = [asyncio.create_task(discover()) for _ in range(2)]
        try:
            for _ in tasks:
                await anyio.to_thread.run_sync(lambda: entered.get(timeout=2))
            for _ in range(2 if cancel_kind == "asyncio-repeated" else 1):
                if cancel_kind == "anyio":
                    scopes[0].cancel()
                else:
                    tasks[0].cancel()
                with pytest.raises(InspectionBusy):
                    await service.discover_sources(draft["id"])
                assert not tasks[0].done()
                assert entered.empty()
        finally:
            release.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
        if cancel_kind != "anyio":
            assert isinstance(results[0], asyncio.CancelledError)
        else:
            assert results[0] is None
        assert scopes[0] not in completed
        assert scopes[1] in completed
        assert results[1] is None
        await service.discover_sources(draft["id"])
        assert not service.active_drafts

    try:
        asyncio.run(run())
    finally:
        release.set()
        service.close()


@pytest.mark.parametrize("worker_fails", [False, True])
def test_anyio_cancel_is_delivered_after_discovery_worker_finishes(
    tmp_path, monkeypatch, worker_fails
):
    entered, release = threading.Event(), threading.Event()
    service = create_app(tmp_path).state.web_intake
    draft = service.create(web_intake.DraftInput(name="fixture", sources=[
        {"id": "s1", "title": "Fixture"}
    ]))
    (service.directory(draft["id"]) / "input.apk").write_bytes(b"synthetic fixture")

    def metadata(path, **kwargs):
        entered.set()
        assert release.wait(5)
        if worker_fails:
            raise ValueError("Synthetic discovery failure")
        return {"policy_urls": []}

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)

    async def run():
        scopes, completed = [], []

        async def discover():
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                try:
                    await service.discover_sources(draft["id"])
                except ValueError:
                    completed.append("worker error caught instead of cancellation")
                completed.append("caller completed instead of cancellation")
            return scope.cancelled_caught

        task = asyncio.create_task(discover())
        try:
            assert await anyio.to_thread.run_sync(lambda: entered.wait(2))
            scopes[0].cancel()
        finally:
            release.set()
            cancelled = await task
        assert cancelled
        assert not completed
        assert not service.active_drafts

    try:
        asyncio.run(run())
    finally:
        release.set()
        service.close()


@pytest.mark.usefixtures("synthetic_package_metadata")
@pytest.mark.parametrize("with_split", [False, True])
@pytest.mark.parametrize("expire_at", ["last_inspection", "publication"])
def test_expired_upload_does_not_publish_and_can_be_retried(
    tmp_path, monkeypatch, with_split, expire_at
):
    base = apk(tmp_path / "base.apk")
    files = {base.name: base.read_bytes()}
    if with_split:
        split = apk(tmp_path / "split.apk", split=True, split_name="feature")
        files[split.name] = split.read_bytes()
    archive = package_set_archive(tmp_path / "set.zip", files)
    app = create_app(tmp_path / "jobs")
    service = app.state.web_intake
    clock = [0]
    monkeypatch.setattr(web_intake, "time", SimpleNamespace(
        monotonic=lambda: clock[0], time=web_intake.time.time,
    ))
    inspect_fixture = web_intake.inspect_package_isolated
    link = os.link
    calls = []
    expired = False

    def metadata(path, **kwargs):
        nonlocal expired
        result = inspect_fixture(path, **kwargs)
        calls.append(path.name)
        if expire_at == "last_inspection" and len(calls) == len(files) and not expired:
            clock[0] += service.INSPECTION_BUDGET_SECONDS + 1
            expired = True
        return result

    def publish_link(*args, **kwargs):
        nonlocal expired
        link(*args, **kwargs)
        if expire_at == "publication" and not expired:
            clock[0] += service.INSPECTION_BUDGET_SECONDS + 1
            expired = True

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)
    monkeypatch.setattr(os, "link", publish_link)
    with TestClient(app) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(
            route + "/package-set", headers=HEADERS, content=archive.read_bytes(),
        )
        assert expired
        assert len(calls) == len(files)
        assert response.status_code == 503
        assert response.json()["detail"] == "ISOLATED_INSPECTION_UNAVAILABLE"
        assert client.get(route).json() == draft
        directory = service.directory(draft["id"])
        assert not (directory / "packages").exists()
        assert not (directory / "input.apk").exists()
        assert not list(directory.glob("*pending*"))
        assert not service.active_drafts
        response = client.post(
            route + "/package-set", headers=HEADERS, content=archive.read_bytes(),
        )
        assert response.status_code == 200
        assert response.json()["uploaded"]


@pytest.mark.usefixtures("synthetic_package_metadata")
@pytest.mark.parametrize("worker_fails", [False, True])
def test_native_upload_cancel_drains_worker_before_cleanup(tmp_path, monkeypatch, worker_fails):
    base = apk(tmp_path / "base.apk")
    entered, release = Queue(), threading.Event()
    app = create_app(tmp_path / "jobs")
    service = app.state.web_intake
    monkeypatch.setattr(service, "INSPECTION_WAIT_SECONDS", 0.02)
    drafts = [service.create(web_intake.DraftInput(name="fixture", sources=[
        {"id": "s1", "title": "Fixture"}
    ])) for _ in range(3)]
    directory = service.directory(drafts[0]["id"])
    inspect_fixture = web_intake.inspect_package_isolated

    def metadata(path, **kwargs):
        entered.put(path)
        assert release.wait(5)
        if worker_fails and path.is_relative_to(directory):
            raise web_intake.ScanError("TIMEOUT", "Synthetic inspection failure")
        return inspect_fixture(path, **kwargs)

    monkeypatch.setattr(web_intake, "inspect_package_isolated", metadata)

    class Body:
        async def stream(self):
            yield base.read_bytes()

    async def run():
        tasks = [asyncio.create_task(service.upload(
            draft["id"], Body(), expect_package_set=True,
        )) for draft in drafts[:2]]
        try:
            for _ in tasks:
                await anyio.to_thread.run_sync(lambda: entered.get(timeout=2))
            for _ in range(2):
                tasks[0].cancel()
                with pytest.raises(InspectionBusy):
                    await service.discover_sources(drafts[2]["id"])
                assert not tasks[0].done()
                assert (directory / "upload.pending").exists()
                assert len(list(directory.glob("packages.pending*"))) == 1
                assert service.active_drafts[drafts[0]["id"]] == 1
                assert entered.empty()
        finally:
            release.set()
            results = await asyncio.gather(*tasks, return_exceptions=True)
        assert isinstance(results[0], asyncio.CancelledError)
        assert results[1]["uploaded"]
        assert service.get(drafts[0]["id"])["uploaded"] is not worker_fails
        assert (directory / "packages").exists() is not worker_fails
        assert (directory / "input.apk").exists() is not worker_fails
        assert not list(directory.glob("*pending*"))
        assert not service.active_drafts
        assert (await service.upload(
            drafts[2]["id"], Body(), expect_package_set=True,
        ))["uploaded"]

    try:
        asyncio.run(run())
    finally:
        release.set()
        service.close()


@pytest.mark.parametrize("disk_phase", ["write", "fsync"])
def test_native_cancel_waits_for_upload_disk_io(tmp_path, monkeypatch, disk_phase):
    entered, release = threading.Event(), threading.Event()
    service = create_app(tmp_path).state.web_intake
    draft = service.create(web_intake.DraftInput(name="fixture", sources=[
        {"id": "s1", "title": "Fixture"}
    ]))
    request_context = ContextVar("intake_test_context", default=None)
    contexts, handles = [], []
    fdopen, fsync = os.fdopen, os.fsync

    def wait_for_disk():
        contexts.append(request_context.get())
        entered.set()
        assert release.wait(5)

    class UploadFile:
        def __init__(self, handle):
            self.handle = handle
            handles.append(handle)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def write(self, data):
            if disk_phase == "write":
                wait_for_disk()
            return self.handle.write(data)

        def __getattr__(self, name):
            return getattr(self.handle, name)

    def sync(fd):
        wait_for_disk()
        fsync(fd)

    monkeypatch.setattr(os, "fdopen", lambda *a, **kw: UploadFile(fdopen(*a, **kw)))
    if disk_phase == "fsync":
        monkeypatch.setattr(os, "fsync", sync)

    class Body:
        async def stream(self):
            yield b"synthetic upload"

    async def run():
        request_context.set("request context must reach disk worker")
        task = asyncio.create_task(service.upload(draft["id"], Body()))
        directory = service.directory(draft["id"])
        try:
            assert await anyio.to_thread.run_sync(lambda: entered.wait(2))
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            assert not handles[0].closed
            assert (directory / "upload.pending").exists()
        finally:
            release.set()
            result, = await asyncio.gather(task, return_exceptions=True)
        assert isinstance(result, asyncio.CancelledError)
        assert contexts == ["request context must reach disk worker"]
        assert handles[0].closed
        assert not list(directory.glob("*pending*"))
        assert not service.active_drafts
        assert not service.get(draft["id"])["uploaded"]
        assert (await service.upload(draft["id"], Body()))["uploaded"]

    try:
        asyncio.run(run())
    finally:
        release.set()
        service.close()
