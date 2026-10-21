"""Real private mTLS reproduction of the caller's remaining Runner budget.

The peer deliberately stalls; synthetic material references avoid APK analysis.
These transport checks do not replace F01-F04/F07 Android acceptance.
"""

import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_runtime_tls import serving
from test_runtime_tls import tls_materials as tls_materials

from privacytrace.runner_client import RunnerClient
from privacytrace.runtime_tls import (
    PrivateClient,
    PrivateHandler,
    PrivateServer,
    RuntimeUnavailable,
)
from privacytrace.scan_workspace import ScanError


class StalledRunner(PrivateHandler):
    def do_POST(self):
        request = self.body()
        self.server.received.append(request)
        time.sleep(0.6)
        self.reply(
            200,
            {
                "version": 1,
                "request_id": request["request_id"],
                "result": None,
                "receipt": None,
                "error": "TIMEOUT",
            },
        )


def client_at(server, tls, tmp_path, *, registration_delay=0):
    draft = {"id": "draft1", "apk_sha256": "a" * 64}
    path = tmp_path / "web" / draft["id"] / "input.apk"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic reference only")

    def register(*args, **kwargs):
        time.sleep(registration_delay)
        return {"name": "base.apk", "size": 24, "sha256": "a" * 64, "ticket": "x.y"}

    remote = PrivateClient("https://127.0.0.1:" + str(server.server_port), tls["client"], timeout=2)
    store = SimpleNamespace(root=tmp_path, instance_id=str(uuid4()))
    lease = SimpleNamespace(job_id="job1", fence=1, owner=uuid4())
    client = RunnerClient(store, remote, "sha256:" + "b" * 64, SimpleNamespace(register=register))
    return client, draft, path, lease


@pytest.mark.parametrize("operation", ["inspect", "scan"])
def test_runner_respects_callers_remaining_budget(tls_materials, tmp_path, operation):
    tls = tls_materials
    server = PrivateServer(
        ("127.0.0.1", 0), StalledRunner, tls["server"], [tls["client_fingerprint"]]
    )
    server.received = []
    with serving(server):
        client, draft, path, lease = client_at(server, tls, tmp_path)
        started = time.monotonic()
        if operation == "inspect":
            with pytest.raises(ScanError) as error:
                client.inspect_metadata(path, timeout=0.15)
            assert error.value.code == "ISOLATION_UNAVAILABLE"
        else:
            with pytest.raises(RuntimeUnavailable):
                client.scanner(draft, lease)(path, timeout=0.15)
        assert time.monotonic() - started < 0.5
        assert len(server.received) == 1


@pytest.mark.parametrize("operation", ["inspect", "scan"])
def test_material_registration_consumes_budget_before_http(tls_materials, tmp_path, operation):
    tls = tls_materials
    server = PrivateServer(
        ("127.0.0.1", 0), StalledRunner, tls["server"], [tls["client_fingerprint"]]
    )
    server.received = []
    with serving(server):
        client, draft, path, lease = client_at(server, tls, tmp_path, registration_delay=0.2)
        if operation == "inspect":
            with pytest.raises(ScanError) as error:
                client.inspect_metadata(path, timeout=0.1)
            assert error.value.code == "ISOLATION_UNAVAILABLE"
        else:
            with pytest.raises(RuntimeUnavailable):
                client.scanner(draft, lease)(path, timeout=0.1)
        assert server.received == [], "Expired work must not start a Runner operation"


class SplitBudgetPeer(PrivateHandler):
    def do_GET(self):
        assert self.authorized()
        time.sleep(0.3)
        raw = json.dumps({"version": 1, "status": "ready"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        time.sleep(0.3)
        self.wfile.write(raw)


def test_private_json_does_not_restart_budget_after_headers(tls_materials):
    tls = tls_materials
    server = PrivateServer(
        ("127.0.0.1", 0), SplitBudgetPeer, tls["server"], [tls["client_fingerprint"]]
    )
    with serving(server):
        client = PrivateClient(
            "https://127.0.0.1:" + str(server.server_port), tls["client"], timeout=2
        )
        started = time.monotonic()
        with pytest.raises(RuntimeUnavailable):
            client.json("/v1/health", timeout=0.45)
        assert time.monotonic() - started < 0.58


@pytest.mark.parametrize("timeout", [0, -1, True, None, "1", float("inf"), float("nan")])
def test_invalid_budget_does_not_register_material_or_send_http(tmp_path, timeout):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid budget reached material registration or network")

    client = RunnerClient(
        SimpleNamespace(root=tmp_path),
        SimpleNamespace(timeout=2, json=forbidden),
        "sha256:" + "b" * 64,
        SimpleNamespace(register=forbidden),
    )
    with pytest.raises(ValueError, match="deadline"):
        client.inspect_metadata(tmp_path / "unused", timeout=timeout)
    with pytest.raises(ValueError, match="deadline"):
        client.scanner({}, None)(tmp_path / "unused", timeout=timeout)


def test_long_scan_budget_still_respects_transport_cap(tls_materials, tmp_path):
    tls = tls_materials
    server = PrivateServer(
        ("127.0.0.1", 0), StalledRunner, tls["server"], [tls["client_fingerprint"]]
    )
    server.received = []
    with serving(server):
        client, draft, path, lease = client_at(server, tls, tmp_path)
        client.remote.timeout = 0.15
        with pytest.raises(RuntimeUnavailable):
            client.scanner(draft, lease)(path, timeout=120)
        assert len(server.received) == 1
