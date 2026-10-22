"""Regression tests for issue #240: the whole response must obey the total time budget.

``urllib``'s timeout only caps a single blocking socket operation, so a controlled model
that trickles small chunks just under that timeout used to keep a single ``resp.read()``
alive past ``max_elapsed_seconds`` and still report an error-free ``SUCCESS``. The same
holds for bytes that never reach the body loop: chunked framing (chunk extensions and
trailers are read with ``readline``) and the response status line and headers.
"""

import json
import shutil
import ssl
import subprocess
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
# HTTPS is only allowed with an API key; this placeholder never leaves the loopback test.
LOOPBACK_TLS_KEY = "test-loopback-only"


@pytest.fixture(autouse=True)
def _bypass_loopback_proxies(monkeypatch):
    """Keep the controlled loopback model out of any host proxy configuration."""
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


class _WriteLog:
    """Server-side evidence about how the client treated the connection."""

    def __init__(self, total_chunks: int = 0):
        self.total_chunks = total_chunks
        self.sent_chunks = 0
        self.sent_bytes = 0
        self.broken = False
        self.done = threading.Event()

    def _write(self, handler, data: bytes) -> bool:
        try:
            handler.wfile.write(data)
            handler.wfile.flush()
        except OSError:
            # The peer closed the connection: the read was really released.
            self.broken = True
            return False
        self.sent_bytes += len(data)
        return True

    def write_blocks(self, handler, body: bytes, chunk: int = TRICKLE_CHUNK,
                     interval: float = TRICKLE_INTERVAL) -> bool:
        for index in range(0, len(body), chunk):
            if not self._write(handler, body[index:index + chunk]):
                return False
            self.sent_chunks += 1
            time.sleep(interval)
        return True

    def write_bytes(self, handler, data: bytes, interval: float = TRICKLE_INTERVAL) -> bool:
        """Send one byte at a time, each one inside the socket timeout."""
        for byte in data:
            if not self._write(handler, bytes([byte])):
                return False
            time.sleep(interval)
        return True


def _model_body(content: str = "[]") -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


def _chunk(data: bytes) -> bytes:
    return f"{len(data):x}\r\n".encode() + data + b"\r\n"


@contextmanager
def _loopback_model(handler_class):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def _loopback_tls_model(handler_class, certificate, key):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(certificate), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
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
    record = _WriteLog(-(-len(body) // TRICKLE_CHUNK))

    class SlowModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                record.write_blocks(self, body)
            finally:
                record.done.set()

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
    record = _WriteLog(-(-len(body) // TRICKLE_CHUNK))

    class SlowModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                record.write_blocks(self, body)
            finally:
                record.done.set()

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
    record = _WriteLog(-(-len(oversized) // 1024))

    class OversizedModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(oversized)))
            self.end_headers()
            try:
                record.write_blocks(self, oversized, chunk=1024, interval=0.002)
            finally:
                record.done.set()

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


@pytest.mark.parametrize("framing", ["chunk-extension", "trailer"])
def test_slow_chunked_framing_cannot_outlive_total_budget(framing):
    """Chunked framing bytes are read inside one read1: they must share the deadline.

    ``HTTPResponse`` consumes the chunk-size line (extensions included) and the trailer
    with ``readline``, so trickling those bytes under the socket timeout used to stretch
    a single outer ``read1`` well past ``max_elapsed_seconds``.
    """
    body = _model_body()
    first, rest = body[:31], body[31:]
    record = _WriteLog()
    if framing == "chunk-extension":
        slow = f"{len(rest):x};".encode() + b"a" * 80 + b"\r\n"
        tail = rest + b"\r\n"
    else:
        slow = b"X-Trailer: " + b"b" * 50 + b"\r\n"
        tail = b"\r\n"

    class ChunkedModel(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                self.wfile.write(_chunk(first))
                self.wfile.flush()
                if framing != "chunk-extension":
                    self.wfile.write(_chunk(rest) + b"0\r\n")
                    self.wfile.flush()
                if record.write_bytes(self, slow):
                    self.wfile.write(tail)
                    self.wfile.flush()
            except OSError:
                record.broken = True
            finally:
                record.done.set()

    with _loopback_model(ChunkedModel) as port:
        extractor = PolicyLLMExtractor(_config(
            port, timeout_seconds=BUDGET_SECONDS, max_elapsed_seconds=BUDGET_SECONDS,
        ))
        started = time.monotonic()
        result = extractor.extract_from_chunk(POLICY_TEXT)
        elapsed = time.monotonic() - started

        # Before the fix: 2.16s for the extension, 1.58s and SUCCESS for the trailer.
        assert elapsed < 0.3
        assert result.status == "FAILED"
        assert result.candidates == []
        assert "LLM_TIMEOUT" in " ".join(result.telemetry.errors)
        assert record.done.wait(2.0)
        assert record.broken is True
        assert record.sent_bytes < len(slow)


def test_slow_header_trickle_cannot_outlive_total_budget():
    """The status line and headers must share the same absolute deadline."""
    body = _model_body()
    slow_header = b"X-Slow: " + b"a" * 55 + b"\r\n"  # ~1.6s at 25ms per byte
    record = _WriteLog()

    class SlowHeaderModel(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            try:
                self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                self.wfile.flush()
                if record.write_bytes(self, slow_header):
                    self.wfile.write(
                        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
                    )
                    self.wfile.flush()
            except OSError:
                record.broken = True
            finally:
                record.done.set()

    with _loopback_model(SlowHeaderModel) as port:
        extractor = PolicyLLMExtractor(_config(
            port, timeout_seconds=BUDGET_SECONDS, max_elapsed_seconds=BUDGET_SECONDS,
        ))
        started = time.monotonic()
        result = extractor.extract_from_chunk(POLICY_TEXT)
        elapsed = time.monotonic() - started

        # Before the fix urlopen() parsed these headers without any deadline: 1.64s.
        assert elapsed < 0.3
        assert result.status == "FAILED"
        assert "LLM_TIMEOUT" in " ".join(result.telemetry.errors)
        assert record.done.wait(2.0)
        assert record.broken is True
        assert record.sent_bytes < len(slow_header)


def test_injected_client_does_not_keep_a_stale_deadline():
    """The extraction deadline is call-scoped, not permanent state on the client."""
    body = _model_body()

    class FastModel(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with _loopback_model(FastModel) as port:
        client = UrllibLLMClient(
            api_base=f"http://127.0.0.1:{port}/v1", api_key="", timeout=5.0,
        )
        extractor = PolicyLLMExtractor(LLMExtractorConfig(
            enabled=True, api_base=f"http://127.0.0.1:{port}/v1", api_key="",
            model="controlled", max_retries=1, max_requests=1,
            max_elapsed_seconds=5.0, timeout_seconds=5.0, client=client,
        ))
        assert extractor.extract_from_chunk(POLICY_TEXT).status == "SUCCESS"
        assert client.deadline is None
        # The same instance still works for a later, unrelated call.
        content, _ = client.call("system", "user")
        assert content == "[]"


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


@pytest.fixture(scope="module")
def loopback_tls(tmp_path_factory):
    """Self-signed loopback server certificate, issued like test_runtime_tls.py does."""
    binary = shutil.which("openssl")
    if not binary:
        pytest.skip("openssl required for the loopback TLS case")
    root = tmp_path_factory.mktemp("llm_response_tls")
    (root / "request.cnf").write_text("[req]\ndistinguished_name=dn\n[dn]\n", encoding="utf-8")
    subprocess.run(
        [binary, "req", "-config", "request.cnf", "-x509", "-newkey", "rsa:2048",
         "-nodes", "-days", "1", "-subj", "/CN=PT240 loopback",
         "-addext", "subjectAltName=IP:127.0.0.1",
         "-keyout", "server.key", "-out", "server.pem"],
        cwd=root, capture_output=True, check=True, timeout=60,
    )
    return root / "server.pem", root / "server.key"


def test_https_transport_keeps_the_same_deadline(loopback_tls, monkeypatch):
    """The production HTTPS path reuses the bounded reader and the deadline socket."""
    certificate, key = loopback_tls
    # The loopback certificate is self-signed; this test only exercises the TLS transport.
    monkeypatch.setattr(ssl, "_create_default_https_context", ssl._create_unverified_context)
    content = json.dumps([{
        "excerpt": "位置信息", "data_type": "LOCATION", "polarity": "AFFIRMATIVE",
    }], ensure_ascii=False)
    body = _model_body(content)
    record = _WriteLog(-(-len(body) // TRICKLE_CHUNK))

    class TlsModel(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            _read_request(self)
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                record.write_blocks(self, body)
            finally:
                record.done.set()

    api_base = None
    with _loopback_tls_model(TlsModel, certificate, key) as port:
        api_base = f"https://127.0.0.1:{port}/v1"
        fast = PolicyLLMExtractor(_config(
            port, api_base=api_base, api_key=LOOPBACK_TLS_KEY,
            timeout_seconds=5.0, max_elapsed_seconds=5.0,
        )).extract_from_chunk(POLICY_TEXT)
        assert fast.status == "SUCCESS"
        assert [candidate["excerpt"] for candidate in fast.candidates] == ["位置信息"]

        record.sent_chunks = 0
        record.broken = False
        record.done.clear()
        started = time.monotonic()
        slow = PolicyLLMExtractor(_config(
            port, api_base=api_base, api_key=LOOPBACK_TLS_KEY,
            timeout_seconds=BUDGET_SECONDS, max_elapsed_seconds=BUDGET_SECONDS,
        )).extract_from_chunk(POLICY_TEXT)
        elapsed = time.monotonic() - started

    assert elapsed < 0.3
    assert slow.status == "FAILED"
    assert "LLM_TIMEOUT" in " ".join(slow.telemetry.errors)
    assert record.done.wait(2.0)
    assert record.broken is True
    assert record.sent_chunks < record.total_chunks
