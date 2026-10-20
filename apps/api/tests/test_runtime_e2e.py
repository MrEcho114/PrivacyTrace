"""Real Windows control processes -> Redis/PG -> dedicated WSL scan VM.

Explicit opt-in, disposable PostgreSQL and a previously authorized task VM are
required. No eager Celery, scanner doubles or shared material mounts are used.
"""

import base64
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from apk_fixture_builder import apk_bytes
from runtime_vm_fixture import OwnedTestVM
from test_postgres_storage import postgres_urls as postgres_urls
from test_runtime_tls import serving
from test_runtime_tls import tls_materials as tls_materials

from privacytrace.material_gateway import create_gateway
from privacytrace.postgres_execution import PostgresExecution
from privacytrace.postgres_outbox import PostgresOutbox
from privacytrace.postgres_schema import audit
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.queue_runtime import BrokerConfig, CeleryPublisher
from privacytrace.runtime_materials import RuntimeMaterials
from privacytrace.runtime_tls import PrivateClient, RuntimeUnavailable


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class System:
    def __init__(self, root, store, vm, env, broker):
        self.root, self.store, self.vm, self.env, self.broker = root, store, vm, env, broker
        self.children = {}
        self.logs = []
        self.port = free_port()
        self.http = httpx.Client(
            base_url=f"http://127.0.0.1:{self.port}", trust_env=False, timeout=20
        )

    def start(self, kind):
        if kind == "api":
            args = [
                "-m",
                "uvicorn",
                "privacytrace.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--no-access-log",
                "--log-level",
                "warning",
            ]
        else:
            args = [
                "-m",
                "privacytrace.runtime_worker" if kind == "worker" else "privacytrace.queue_runtime",
            ]
            if kind == "dispatch_once":
                args.append("--once")
        log = (self.root / (kind + ".log")).open("ab")
        self.logs.append(log)
        environment = dict(self.env)
        if kind == "api":
            environment.pop("PRIVACYTRACE_BROKER_URL", None)
        elif kind.startswith("dispatch"):
            environment = {
                k: v
                for k, v in environment.items()
                if not k.startswith("PRIVACYTRACE_CONTROL_TLS")
                and k != "PRIVACYTRACE_MATERIAL_KEY_FILE"
            }
        child = subprocess.Popen(
            [sys.executable, "-B", *args],
            env=environment,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.children[kind] = child
        return child

    def stop(self, kind, *, hard=False):
        process = self.children.get(kind)
        if process is not None and process.poll() is None:
            (process.kill if hard else process.terminate)()
            process.wait(timeout=20)

    def ready_api(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            assert self.children["api"].poll() is None, (
                "API failed; inspect private test process log"
            )
            try:
                if self.http.get("/api/v1/health").status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        pytest.fail("API did not become ready")

    def create(self, name="runtime-apk"):
        created = self.http.post(
            "/api/v1/web/drafts",
            json={
                "name": name,
                "sources": [
                    {
                        "id": "host",
                        "title": "Private runtime policy canary",
                        "text": "We do not collect contacts.",
                    }
                ],
            },
        ).json()
        assert "token" in created, "Draft creation failed"
        headers = {"Authorization": "Bearer " + created["token"]}
        draft_path = "/api/v1/web/drafts/" + created["id"]
        upload = self.http.post(draft_path + "/apk", content=apk_bytes(), headers=headers)
        assert upload.status_code == 200, "Actual APK upload was rejected"
        started = self.http.post(
            draft_path + "/start",
            json={"revision": upload.json()["revision"], "request_id": uuid4().hex},
            headers=headers,
        )
        assert started.status_code == 200, "Durable task registration was rejected"
        return started.json()["id"], headers, created

    def wait_job(self, job_id, expected="SUCCEEDED", timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.store.get(job_id)
            if job.state == expected:
                return job
            if job.state in {"FAILED", "CANCELLED"} and job.state != expected:
                pytest.fail("Real runtime job terminated: " + str(job.error))
            time.sleep(0.1)
        pytest.fail("Real runtime job did not reach expected state")

    def wait_execution(self, job_id, expected, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = PostgresExecution(self.store).status(job_id)
            if row["state"] == expected:
                return row
            time.sleep(0.05)
        pytest.fail("Execution did not reach controlled process fault point")

    def restart_runner(self):
        log = (self.root / "vm-runner.log").open("ab")
        self.logs.append(log)
        self.vm.start_runner(log)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if self.remote.json("/v1/health")["status"] == "ready":
                    return
            except (RuntimeUnavailable, PermissionError):
                pass
            time.sleep(0.1)
        pytest.fail("Actual runner did not restart")

    def close(self):
        for kind in list(self.children):
            self.stop(kind)
        self.http.close()
        for log in self.logs:
            log.close()


@contextmanager
def running_system(postgres_urls, tls_materials, tmp_path):
    if os.environ.get("PRIVACYTRACE_E2E_WSL_TESTS") != "1":
        pytest.skip("Opt-in real Windows API/worker and dedicated WSL Runner E2E")
    assert os.name == "nt", "This explicit harness uses Windows control + dedicated WSL VM"
    import ctypes

    import redis

    assert not ctypes.windll.shell32.IsUserAnAdmin(), (
        "Control processes must run without administrator privileges"
    )
    for name in (
        "PRIVACYTRACE_E2E_WSL_DISTRO",
        "PRIVACYTRACE_E2E_WSL_MARKER",
        "PRIVACYTRACE_E2E_LINUX_REPO",
    ):
        assert os.environ.get(name), "Authorized test VM configuration required"
    instance = str(uuid4())
    store = PostgresJobStore(postgres_urls[0], instance, tmp_path / "materials")
    key = tmp_path / "material.key"
    key.write_bytes(secrets.token_bytes(32))
    key.chmod(0o600)
    materials = RuntimeMaterials(store, key)
    tls = tls_materials
    password, admin_password = secrets.token_hex(24), secrets.token_hex(24)
    vm = OwnedTestVM(
        instance,
        tls["other"],
        tls["client_fingerprint"],
        password,
        admin_password,
        os.environ["PRIVACYTRACE_E2E_LINUX_REPO"],
    )
    gateway = create_gateway(
        store, ("127.0.0.1", 0), tls["server"], [tls["other_fingerprint"]], materials
    )
    system = None
    try:
        with serving(gateway):
            vm.configure("https://127.0.0.1:" + str(gateway.server_port))
            vm.call("redis_start")
            broker = BrokerConfig(
                f"redis://app_{instance.replace('-', '')}:{password}"
                f"@127.0.0.1:{vm.state['redis_port']}/15",
                instance,
            )
            client = redis.Redis.from_url(broker.url, socket_connect_timeout=1, socket_timeout=1)
            deadline = time.monotonic() + 15
            while True:
                try:
                    if client.ping():
                        break
                except redis.exceptions.RedisError:
                    pass
                assert time.monotonic() < deadline, "Actual VM Redis unavailable"
                time.sleep(0.1)
            environment = {
                name: os.environ[name]
                for name in (
                    "PATH",
                    "SystemRoot",
                    "WINDIR",
                    "TEMP",
                    "TMP",
                    "USERPROFILE",
                    "LOCALAPPDATA",
                    "APPDATA",
                )
                if name in os.environ
            }
            environment.update(
                PRIVACYTRACE_STORAGE="postgres",
                PRIVACYTRACE_MODE="remote",
                PRIVACYTRACE_EXECUTION="durable",
                PRIVACYTRACE_DATABASE_URL=postgres_urls[0],
                PRIVACYTRACE_INSTANCE_ID=instance,
                PRIVACYTRACE_STORE_ROOT=str(tmp_path / "materials"),
                PRIVACYTRACE_ALLOWED_HOSTS="127.0.0.1",
                PRIVACYTRACE_BROKER_URL=broker.url,
                PRIVACYTRACE_MATERIAL_KEY_FILE=str(key),
                PRIVACYTRACE_RUNNER_URL="https://127.0.0.1:" + str(vm.state["runner_port"]),
                PRIVACYTRACE_RUNNER_IMAGE_ID=vm.state["image_id"],
                PRIVACYTRACE_CONTROL_TLS_CA=str(tls["client"].ca),
                PRIVACYTRACE_CONTROL_TLS_CERT=str(tls["client"].cert),
                PRIVACYTRACE_CONTROL_TLS_KEY=str(tls["client"].key),
                PRIVACYTRACE_LEASE_SECONDS="5",
                PYTHONUTF8="1",
                PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"),
            )
            system = System(tmp_path, store, vm, environment, broker)
            with (tmp_path / "vm-runner.log").open("ab") as log:
                vm.start_runner(log)
                remote = PrivateClient(
                    environment["PRIVACYTRACE_RUNNER_URL"], tls["client"], timeout=2
                )
                system.remote = remote
                deadline = time.monotonic() + 20
                while True:
                    assert vm.process.poll() is None, "Actual VM runner failed to boot"
                    try:
                        if remote.json("/v1/health")["status"] == "ready":
                            break
                    except (RuntimeUnavailable, PermissionError):
                        pass
                    assert time.monotonic() < deadline, "Actual VM runner unavailable"
                    time.sleep(0.1)
                assert vm.call("runner_check")["database_credentials"] is False
                system.start("api")
                system.ready_api()
                try:
                    yield system, client
                finally:
                    system.close()
            client.close()
    finally:
        if system:
            system.close()
        vm.close()
        store.close()


@pytest.fixture
def system(postgres_urls, tls_materials, tmp_path):
    with running_system(postgres_urls, tls_materials, tmp_path) as value:
        yield value


def test_actual_single_apk_api_restart_queue_worker_runner_and_report(system):
    value, broker = system
    assert value.http.post("/api/v1/jobs", json={}).status_code == 409
    job_id, headers, draft = value.create()
    assert value.store.get(job_id).state == "QUEUED"
    value.stop("api", hard=True)
    value.start("api")
    value.ready_api()
    assert value.store.get(job_id).state == "QUEUED"
    dispatch = value.start("dispatch_once")
    assert dispatch.wait(timeout=20) == 0, "Actual dispatcher failed"
    raw = broker.lrange(value.broker.key_prefix + value.broker.queue, 0, -1)
    assert len(raw) == 1
    envelope = json.loads(base64.b64decode(json.loads(raw[0])["body"]))
    assert set(envelope[0][0]) == {"version", "event_type", "instance_id", "job_id", "event_id"}
    assert draft["token"].encode() not in raw[0] and b"collect contacts" not in raw[0]
    value.start("worker")
    value.wait_job(job_id)
    report = value.http.get(f"/api/v1/jobs/{job_id}/report", headers=headers)
    assert report.status_code == 200
    result = report.json()
    assert result["job"]["source_origin"] == "REAL_SCAN"
    assert result["policy_documents"][0]["review_status"] == "UNREVIEWED"
    proof = json.loads(result["tools"]["runner_receipt"])
    assert proof["cleanup_verified"] and proof["input_removed"]
    assert proof["image_id"] == value.vm.state["image_id"]
    assert value.http.get(f"/api/v1/jobs/{job_id}/report").status_code == 401
    for name in ("api", "worker", "dispatch_once", "vm-runner"):
        text = (value.root / (name + ".log")).read_text(encoding="utf-8", errors="replace")
        assert draft["token"] not in text and "collect contacts" not in text
    (value.root / "e2e-receipt.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")


def assert_one_result(value, job_id):
    import sqlalchemy as sa

    with value.store._transaction() as conn:
        assert (
            conn.scalar(
                sa.select(sa.func.count())
                .select_from(audit)
                .where(audit.c.scope_id == job_id, audit.c.action == "EXECUTION_COMMITTED")
            )
            == 1
        )


def test_actual_worker_and_runner_restart_expired_lease_and_duplicate_delivery(system):
    value, broker = system
    job_id, headers, _ = value.create()
    assert value.start("dispatch_once").wait(timeout=20) == 0
    value.vm.call("runner_pause")
    try:
        value.start("worker")
        first = value.wait_execution(job_id, "RUNNING")
        value.stop("worker", hard=True)
        # Kill the stopped trusted process, closing the old RPC. Old execution
        # authority still expires according to PG, not this process command.
        value.vm.stop_runner(hard=True)
    finally:
        value.restart_runner()
    time.sleep(5.2)  # Actual five-second test lease, no database clock rewrite.
    assert PostgresExecution(value.store).recover()["retried"] == 1
    value.start("dispatch")
    value.start("worker")
    value.wait_job(job_id)
    row = PostgresExecution(value.store).status(job_id)
    assert row["attempt"] == 2 and row["fence"] > first["fence"] and row["owner"] != first["owner"]
    event = PostgresOutbox(value.store).get(str(row["event_id"]))
    publisher = CeleryPublisher(value.broker)
    try:
        for _ in range(3):
            publisher.publish(event.message)
    finally:
        publisher.close()
    deadline = time.monotonic() + 10
    while broker.llen(value.broker.key_prefix + value.broker.queue) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert broker.llen(value.broker.key_prefix + value.broker.queue) == 0
    assert_one_result(value, job_id)
    assert PostgresExecution(value.store).status(job_id)["attempt"] == 2
    assert value.http.get(f"/api/v1/jobs/{job_id}/report", headers=headers).status_code == 200


def test_actual_broker_outage_aof_restart_two_jobs_and_scope_matrix(system):
    value, _ = system
    first, headers1, draft1 = value.create("first private scope")
    second, headers2, draft2 = value.create("second private scope")
    # Check authorization before touching bodies, scanner or terminal state.
    for method, url, body in (
        ("GET", f"/api/v1/web/drafts/{draft1['id']}", None),
        ("POST", f"/api/v1/web/drafts/{draft1['id']}/apk", b"foreign bytes"),
        ("POST", f"/api/v1/web/drafts/{draft1['id']}/start", b"{}"),
        ("DELETE", f"/api/v1/web/drafts/{draft1['id']}", None),
        ("GET", f"/api/v1/jobs/{first}/report", None),
        ("POST", f"/api/v1/jobs/{first}/reviews", b"{}"),
        ("POST", f"/api/v1/jobs/{first}/cancel", None),
        ("DELETE", f"/api/v1/jobs/{first}", None),
    ):
        assert value.http.request(method, url, content=body, headers=headers2).status_code == 403
    assert value.http.get(f"/api/v1/web/drafts/{draft2['id']}", headers=headers2).status_code == 200
    value.vm.call("redis_stop", hard=True)
    assert value.start("dispatch_once").wait(timeout=20) == 0
    assert value.store.get(first).state == value.store.get(second).state == "QUEUED"
    value.vm.call("redis_start")
    value.start("dispatch")
    # Wait for durable delivery, then restart the actual AOF broker before the
    # consumer runs. Both independently registered tasks must survive.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        rows = [PostgresExecution(value.store).status(j) for j in (first, second)]
        delivered = [PostgresOutbox(value.store).get(str(r["event_id"])) for r in rows]
        if all(e.state == "DELIVERED" for e in delivered):
            break
        time.sleep(0.1)
    assert all(e.state == "DELIVERED" for e in delivered)
    value.stop("dispatch")
    value.vm.call("redis_stop", hard=True)
    value.vm.call("redis_start")
    value.start("worker")
    value.wait_job(first)
    value.wait_job(second)
    for job, headers in ((first, headers1), (second, headers2)):
        assert value.http.get(f"/api/v1/jobs/{job}/report", headers=headers).status_code == 200
        assert_one_result(value, job)
    assert value.http.get(f"/api/v1/jobs/{second}/report", headers=headers1).status_code == 403


def test_actual_cancel_delete_redelivery_and_explicit_retry_use_new_identity(system):
    value, _ = system
    first, headers1, _ = value.create("cancelled before runner acceptance")
    second, headers2, draft2 = value.create("deleted before runner acceptance")
    assert value.start("dispatch_once").wait(timeout=20) == 0
    # The actual trusted Runner is stopped while the first Celery task owns a
    # real lease. Resume only after both independent authorizations are revoked.
    value.vm.call("runner_pause")
    try:
        value.start("worker")
        deadline = time.monotonic() + 20
        active = None
        while time.monotonic() < deadline:
            rows = {j: PostgresExecution(value.store).status(j) for j in (first, second)}
            active = next((j for j, r in rows.items() if r["state"] == "RUNNING"), None)
            if active:
                break
            time.sleep(0.05)
        assert active, "Worker did not acquire real execution authority"
        assert value.http.post(f"/api/v1/jobs/{first}/cancel", headers=headers1).status_code == 200
        assert (
            value.http.delete(f"/api/v1/web/drafts/{draft2['id']}", headers=headers2).status_code
            == 200
        )
        assert value.store.get(first).state == "CANCELLED" and value.store.is_tombstoned(second)
        publisher = CeleryPublisher(value.broker)
        try:
            for job in (first, second):
                row = PostgresExecution(value.store).status(job)
                publisher.publish(PostgresOutbox(value.store).get(str(row["event_id"])).message)
        finally:
            publisher.close()
    finally:
        value.vm.call("runner_continue")
    # User retry is a new authorization-scoped task. The cancelled identity and
    # deleted draft remain terminal even while duplicate messages are consumed.
    retried = value.http.post(f"/api/v1/jobs/{first}/retry", headers=headers1)
    assert retried.status_code == 200
    new_id = retried.json()["id"]
    assert new_id != first and retried.json()["retry_of"] == first
    value.start("dispatch")
    value.wait_job(new_id)
    assert value.store.get(first).state == "CANCELLED"
    assert value.store.is_tombstoned(second)
    assert value.http.get(f"/api/v1/jobs/{second}/report", headers=headers2).status_code == 404
    assert value.http.get(f"/api/v1/jobs/{new_id}/report", headers=headers1).status_code == 200
    assert_one_result(value, new_id)
    assert not (value.store.root / "web" / draft2["id"]).exists()


def test_actual_two_independent_instances_scan_concurrently_and_reject_cross_scope(
    postgres_urls, tls_materials, tmp_path
):
    with (
        running_system(postgres_urls, tls_materials, tmp_path / "one") as (one, _),
        running_system(postgres_urls, tls_materials, tmp_path / "two") as (two, _),
    ):
        first, headers1, draft = one.create("independent instance one")
        second, headers2, _ = two.create("independent instance two")
        assert one.store.instance_id != two.store.instance_id
        assert one.broker.key_prefix != two.broker.key_prefix
        for value in (one, two):
            assert value.start("dispatch_once").wait(timeout=20) == 0
            value.start("worker")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(one.wait_job, first), pool.submit(two.wait_job, second)
            a.result(timeout=60)
            b.result(timeout=60)
        assert one.http.get(f"/api/v1/jobs/{first}/report", headers=headers1).status_code == 200
        assert two.http.get(f"/api/v1/jobs/{second}/report", headers=headers2).status_code == 200
        assert one.http.get(f"/api/v1/jobs/{second}/report", headers=headers2).status_code == 404
        assert two.http.get(f"/api/v1/jobs/{first}/report", headers=headers1).status_code == 404
        assert one.http.post(f"/api/v1/jobs/{first}/cancel", headers=headers2).status_code == 403
        assert two.http.delete(f"/api/v1/jobs/{second}", headers=headers1).status_code == 403
        # A valid first-instance transfer permit and trusted control certificate
        # still cannot make the second dedicated Runner fetch its material.
        materials = RuntimeMaterials(one.store, one.env["PRIVACYTRACE_MATERIAL_KEY_FILE"])
        file = materials.register(
            one.store.root / "web" / draft["id"] / "input.apk", draft_id=draft["id"]
        )
        request = {
            "version": 1,
            "operation": "inspect",
            "request_id": str(uuid4()),
            "instance_id": one.store.instance_id,
            "scope_id": draft["id"],
            "owner": None,
            "fence": 0,
            "package_set": False,
            "files": [file],
        }
        with pytest.raises(PermissionError):
            two.remote.json("/v1/run", data=request)
        assert_one_result(one, first)
        assert_one_result(two, second)
