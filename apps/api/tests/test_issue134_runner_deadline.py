"""Real private mTLS reproduction of the caller's remaining Runner budget.

The peer deliberately stalls; synthetic material references avoid APK analysis.
These transport checks do not replace F01-F04/F07 Android acceptance.
"""

import json
import time
from contextlib import nullcontext
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
        assert time.monotonic() - started < 0.7


@pytest.mark.parametrize("stream", [None, SimpleNamespace(raw=object())])
def test_unknown_response_wrapper_fails_closed_without_reading(monkeypatch, stream):
    response = SimpleNamespace(
        fp=stream,
        isclosed=lambda: False,
        read1=lambda size: pytest.fail("Unbounded response read"),
    )
    client = PrivateClient.__new__(PrivateClient)
    client.timeout = 1
    monkeypatch.setattr(client, "open", lambda *args, **kwargs: nullcontext(response))
    with pytest.raises(RuntimeUnavailable, match="read timeout"):
        client.json("/v1/health")


def test_response_timeout_setter_attribute_error_is_unavailable(monkeypatch):
    def rejected(timeout):
        raise AttributeError("private wrapper detail")

    response = SimpleNamespace(
        fp=SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=rejected))),
        isclosed=lambda: False,
        read1=lambda size: pytest.fail("Unbounded response read"),
    )
    client = PrivateClient.__new__(PrivateClient)
    client.timeout = 1
    monkeypatch.setattr(client, "open", lambda *args, **kwargs: nullcontext(response))
    with pytest.raises(RuntimeUnavailable, match="read timeout"):
        client.json("/v1/health")


def test_response_reads_share_the_budget_consumed_by_headers(monkeypatch):
    now, timeouts = [0.0], []
    blocks = iter([b'{"status":', b'"ready"}'])
    remaining_blocks = [2]

    def read(size):
        now[0] += 0.25
        remaining_blocks[0] -= 1
        return next(blocks)

    response = SimpleNamespace(
        fp=SimpleNamespace(raw=SimpleNamespace(_sock=SimpleNamespace(settimeout=timeouts.append))),
        isclosed=lambda: remaining_blocks[0] == 0,
        read1=read,
    )

    def opened(*args, **kwargs):
        now[0] += 0.25
        return nullcontext(response)

    client = PrivateClient.__new__(PrivateClient)
    client.timeout = 1
    monkeypatch.setattr(client, "open", opened)
    monkeypatch.setattr("privacytrace.runtime_tls.time.monotonic", lambda: now[0])
    assert client.json("/v1/health") == {"status": "ready"}
    assert timeouts == pytest.approx([0.75, 0.5])


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


@pytest.mark.parametrize("timeout", [0, -1, True, None, "1", float("inf"), float("nan")])
def test_invalid_transport_cap_is_a_configuration_error_before_io(tmp_path, timeout):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid transport cap reached material registration or network")

    client = RunnerClient(
        SimpleNamespace(root=tmp_path),
        SimpleNamespace(timeout=timeout, json=forbidden),
        "sha256:" + "b" * 64,
        SimpleNamespace(register=forbidden),
    )
    with pytest.raises(ValueError, match="transport timeout"):
        client.inspect_metadata(tmp_path / "unused")
    with pytest.raises(ValueError, match="transport timeout"):
        client.scanner({}, None)(tmp_path / "unused")


def test_long_scan_budget_still_respects_transport_cap(tls_materials, tmp_path, monkeypatch):
    tls = tls_materials
    server = PrivateServer(
        ("127.0.0.1", 0), StalledRunner, tls["server"], [tls["client_fingerprint"]]
    )
    server.received = []
    with serving(server):
        client, draft, path, lease = client_at(server, tls, tmp_path)
        client.remote.timeout = 0.15
        # At this clock value, (now + 0.15) - now is slightly greater than 0.15.
        monkeypatch.setattr(
            "privacytrace.runner_client.time", SimpleNamespace(monotonic=lambda: 32768.0)
        )
        with pytest.raises(RuntimeUnavailable):
            client.scanner(draft, lease)(path, timeout=120)
        assert len(server.received) == 1
