"""Regression tests for issue #240: the response body must obey the total time budget.

``urllib``'s timeout only caps a single blocking socket operation, so a controlled model
that trickles small chunks just under that timeout used to keep a single ``resp.read()``
alive past ``max_elapsed_seconds`` and still report an error-free ``SUCCESS``.
"""

import json
import threading
import time
import urllib.error
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from privacytrace.policy_llm_extractor import (
    LLMExtractorConfig,
    PolicyLLMExtractor,
    UrllibLLMClient,
)

BUDGET_SECONDS = 0.1
TRICKLE_INTERVAL = 0.025
TRICKLE_CHUNK = 4
POLICY_TEXT = "我们收集位置信息。"


@pytest.fixture(autouse=True)
def _bypass_loopback_proxies(monkeypatch):
    """Keep the controlled loopback model out of any host proxy configuration."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


class _TrickleRecord:
    """Server-side evidence about how the client treated the connection."""

    def __init__(self, total_chunks: int):
        self.total_chunks = total_chunks
        self.sent_chunks = 0
        self.broken = False
        self.done = threading.Event()

    def send(self, handler, body: bytes, chunk: int = TRICKLE_CHUNK,
             interval: float = TRICKLE_INTERVAL) -> None:
        for index in range(0, len(body), chunk):
            try:
                handler.wfile.write(body[index:index + chunk])
                handler.wfile.flush()
            except OSError:
                # The peer closed the connection mid-body: the read was really released.
                self.broken = True
                break
            self.sent_chunks += 1
            time.sleep(interval)
        self.done.set()


def _model_body(content: str = "[]") -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


@contextmanager
def _loopback_model(handler_class):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()


def _read_request(handler: BaseHTTPRequestHandler) -> bytes:
    return handler.rfile.read(int(handler.headers.get("Content-Length", 0)))


def _config(port: int, **overrides) -> LLMExtractorConfig:
    settings = {
        "enabled": True,
        "api_base": f"http://127.0.0.1:{port}/v1",
        "api_key": "",
        "model": "controlled",
        "max_requests": 1,
        "max_retries": 1,
    }
    settings.update(overrides)
    return LLMExtractorConfig(**settings)


def _span(text: str = "Policy text.", start: int = 0) -> dict:
    return {"start": start, "end": start + len(text), "text": text}


def test_trickled_body_cannot_outlive_total_budget():
    """A peer sending 4 bytes every 25ms must not extend a 0.1s total budget."""
    body = _model_body()
    record = _TrickleRecord(-(-len(body) // TRICKLE_CHUNK))

    class SlowModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            record.send(self, body)

    with _loopback_model(SlowModel) as port:
        extractor = PolicyLLMExtractor(_config(
            port, timeout_seconds=BUDGET_SECONDS, max_elapsed_seconds=BUDGET_SECONDS,
        ))
        started = time.monotonic()
        result = extractor.extract_from_spans("Policy text.", [_span()])
        elapsed = time.monotonic() - started

        # Before the fix this returned at ~0.36s with SUCCESS and no errors.
        assert elapsed < 0.25
        assert result.status == "FAILED"
        assert result.candidates == []
        assert "LLM_TIMEOUT" in " ".join(result.telemetry.errors)
        assert result.telemetry.failed_spans
        # The read is abandoned in-thread: the server sees the closed connection and
        # stops writing, so nothing keeps draining the response in the background.
        assert record.done.wait(2.0)
        assert record.broken is True
        assert record.sent_chunks < record.total_chunks


def test_total_budget_is_shared_across_spans():
    """A slow first span must consume the shared budget, not restart it per span."""
    body = _model_body()
    record = _TrickleRecord(-(-len(body) // TRICKLE_CHUNK))

    class SlowModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            record.send(self, body)

    spans = [_span(start=0), _span(start=13)]
    with _loopback_model(SlowModel) as port:
        extractor = PolicyLLMExtractor(_config(
            port, timeout_seconds=BUDGET_SECONDS, max_elapsed_seconds=BUDGET_SECONDS,
            max_requests=2,
        ))
        started = time.monotonic()
        result = extractor.extract_from_spans("Policy text. Policy text.", spans)
        elapsed = time.monotonic() - started

        assert elapsed < 0.3  # one budget, not one budget per span
        assert result.candidates == []
        assert result.status in {"FAILED", "PARTIAL"}  # never an error-free SUCCESS
        # The second span never receives a fresh budget: it either fails on the already
        # expired deadline or is skipped outright.
        assert len(result.telemetry.failed_spans) + len(result.telemetry.skipped_spans) == 2
        assert all(
            "LLM_TIMEOUT" in " ".join(span["errors"])
            for span in result.telemetry.failed_spans
        )
        assert all(
            span["reason"] == "TIME_BUDGET_EXHAUSTED"
            for span in result.telemetry.skipped_spans
        )


def test_fast_response_within_budget_still_succeeds():
    """The deadline loop must not disturb a model that answers immediately."""
    content = json.dumps([{
        "excerpt": "位置信息", "data_type": "LOCATION", "polarity": "AFFIRMATIVE",
    }], ensure_ascii=False)
    body = _model_body(content)

    class FastModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _loopback_model(FastModel) as port:
        result = PolicyLLMExtractor(_config(
            port, timeout_seconds=5.0, max_elapsed_seconds=5.0,
        )).extract_from_chunk(POLICY_TEXT)

    assert result.status == "SUCCESS"
    assert [candidate["excerpt"] for candidate in result.candidates] == ["位置信息"]
    assert result.telemetry.errors == []


def test_oversized_body_is_still_rejected_at_the_cap():
    """The byte cap must still stop the read early and release the connection."""
    max_bytes = 4096
    oversized = b"x" * (8 * 1024 * 1024)
    record = _TrickleRecord(-(-len(oversized) // 1024))

    class OversizedModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(oversized)))
            self.end_headers()
            record.send(self, oversized, chunk=1024, interval=0.002)

    with _loopback_model(OversizedModel) as port:
        extractor = PolicyLLMExtractor(_config(
            port, timeout_seconds=5.0, max_elapsed_seconds=5.0,
            max_response_bytes=max_bytes,
        ))
        started = time.monotonic()
        result = extractor.extract_from_chunk(POLICY_TEXT)
        elapsed = time.monotonic() - started

    assert result.status == "FAILED"
    assert "RESPONSE_TOO_LARGE" in " ".join(result.telemetry.errors)
    assert elapsed < 1.0  # 8 MiB at 1 KiB/2ms would need ~16s to drain
    assert record.done.wait(2.0)
    assert record.broken is True
    assert record.sent_chunks < record.total_chunks


def test_stalled_body_still_hits_the_socket_timeout():
    """A peer that answers headers and then stalls keeps the idle timeout semantics."""
    class StalledModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", "64")
            self.end_headers()
            self.wfile.flush()
            time.sleep(2.0)

    with _loopback_model(StalledModel) as port:
        extractor = PolicyLLMExtractor(_config(
            port, timeout_seconds=0.2, max_elapsed_seconds=5.0,
        ))
        started = time.monotonic()
        result = extractor.extract_from_chunk(POLICY_TEXT)
        elapsed = time.monotonic() - started

    assert result.status == "FAILED"
    assert "LLM_TIMEOUT" in " ".join(result.telemetry.errors)
    assert elapsed < 1.0


def test_redirect_is_still_refused_without_following():
    class RedirectingModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/v1/chat/completions")
            self.send_header("Content-Length", "0")
            self.end_headers()

    with _loopback_model(RedirectingModel) as port:
        client = UrllibLLMClient(api_base=f"http://127.0.0.1:{port}/v1", api_key="")
        with pytest.raises(urllib.error.HTTPError) as failure:
            client.call("system", "user")
        assert failure.value.code == 302
        assert "redirects are forbidden" in str(failure.value)


def test_credential_reflection_is_still_refused():
    key = "PRIVATE_RESPONSE_CANARY"

    class EchoingModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            body = _model_body(f"leaked {key}")
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _loopback_model(EchoingModel) as port:
        client = UrllibLLMClient(
            api_base=f"http://127.0.0.1:{port}/v1", api_key=key, model="echo-key",
        )
        with pytest.raises(ValueError) as failure:
            client.call("system", "user")
        assert key not in str(failure.value)
