"""Real local HTTP seam, with explicit test-only public DNS targets."""

import json
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from privacytrace import policy_fetch
from privacytrace.policy_llm_extractor import UrllibLLMClient


@pytest.fixture
def http_fixture(monkeypatch):
    seen = []
    bodies = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append(self.path)
            if self.path in {"/redirect", "/private", "/loop"}:
                target = {
                    "/redirect": "/ok",
                    "/private": "http://127.0.0.1/private",
                    "/loop": "/loop",
                }[self.path]
                self.send_response(302)
                self.send_header("Location", target)
                self.end_headers()
                return
            content_type = "application/pdf" if self.path == "/pdf" else "text/html; charset=utf-8"
            body = (
                b"<script>hidden</script>"
                if self.path == "/empty"
                else (
                    b"x" * (policy_fetch.MAX_HTML_BYTES + 1)
                    if self.path == "/large"
                    else "<p>我们不会读取联系人。</p><script>hidden</script>".encode()
                )
            )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            if self.path == "/slow":
                time.sleep(0.5)
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            body["has_authorization"] = bool(self.headers.get("Authorization"))
            raw = json.dumps({"choices": [{"message": {"content": "[]"}}], "usage": {}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    original = policy_fetch.public_target

    def target(url, timeout=15):
        parts = urlsplit(url)
        if parts.hostname == "public.privacytrace.test":
            return (
                parts._replace(netloc=f"127.0.0.1:{port}"),
                port,
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
            )
        return original(url, timeout)

    monkeypatch.setattr(policy_fetch, "public_target", target)
    try:
        yield seen, bodies, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_redirect_pin_text_snapshot_and_private_redirect(http_fixture):
    seen, _, _ = http_fixture
    captured = policy_fetch.fetch_policy("http://public.privacytrace.test/redirect")
    assert captured["final_url"] == "http://public.privacytrace.test/ok"
    assert captured["text"] == "我们不会读取联系人。"
    assert captured["sha256"] and captured["captured_at"]
    with pytest.raises(policy_fetch.FetchError, match="PUBLIC_URL_REQUIRED"):
        policy_fetch.fetch_policy("http://public.privacytrace.test/private")
    assert seen == ["/redirect", "/ok", "/private"]


@pytest.mark.parametrize(
    "path,code",
    [
        ("/empty", "FETCH_TEXT_MISSING"),
        ("/pdf", "FETCH_HTML_REQUIRED"),
        ("/large", "FETCH_TOO_LARGE"),
        ("/loop", "FETCH_REDIRECT_LIMIT"),
    ],
)
def test_capture_rejects_unsupported_or_unbounded_material(http_fixture, path, code):
    with pytest.raises(policy_fetch.FetchError, match=code):
        policy_fetch.fetch_policy("http://public.privacytrace.test" + path)


def test_system_dns_and_public_dns_have_process_timeouts(monkeypatch):
    limits = []

    def timeout(args, **kwargs):
        limits.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(policy_fetch.FetchError, match="FETCH_TIMEOUT"):
        policy_fetch.public_target("https://public.example/policy", timeout=0.05)
    with pytest.raises(policy_fetch.FetchError, match="FETCH_TIMEOUT"):
        policy_fetch.public_dns("public.example", 443, timeout=0.1)
    assert 0 < limits[0] <= 0.05 and limits[1] == 0.1


def test_optional_non_thinking_payload_preserves_legacy_client(http_fixture, monkeypatch):
    _, bodies, port = http_fixture
    base = f"http://127.0.0.1:{port}/v1"
    assert UrllibLLMClient(api_base=base).call("system", "policy")[0] == "[]"
    assert "thinking" not in bodies[-1]
    assert UrllibLLMClient(api_base=base, thinking_mode=False).call("system", "policy")[0] == "[]"
    assert bodies[-1]["thinking"] == {"type": "disabled"}
    monkeypatch.setenv("PRIVACYTRACE_LLM_API_KEY", "test-environment-only")
    UrllibLLMClient(api_base=base, api_key="").call("system", "policy")
    assert bodies[-1]["has_authorization"] is False


def test_network_body_is_bounded_by_total_budget(http_fixture):
    started = time.monotonic()
    with pytest.raises(policy_fetch.FetchError, match="FETCH_TIMEOUT"):
        policy_fetch.fetch_policy("http://public.privacytrace.test/slow", budget_seconds=0.1)
    assert time.monotonic() - started < 1


def test_html_parsing_cannot_return_success_after_budget(http_fixture, monkeypatch):
    original = policy_fetch.HTMLText.feed
    parsed = []

    def slow_parse(parser, data):
        parsed.append(True)
        time.sleep(0.25)
        original(parser, data)

    monkeypatch.setattr(policy_fetch.HTMLText, "feed", slow_parse)
    with pytest.raises(policy_fetch.FetchError, match="FETCH_TIMEOUT"):
        policy_fetch.fetch_policy("http://public.privacytrace.test/ok", budget_seconds=0.2)
    assert parsed


def test_query_values_are_redacted_without_losing_origin_path_or_keys():
    result = policy_fetch.display_url("https://public.example/policy?token=PRIVATE&version=7")
    assert result == "https://public.example/policy?token=REDACTED&version=REDACTED"


def test_manual_source_url_cannot_publish_userinfo_or_invalid_authority():
    assert policy_fetch.display_url("https://user:PRIVATE@public.example/policy?key=SECRET") == (
        "https://public.example/policy?key=REDACTED"
    )
    assert policy_fetch.display_url("https://user:PRIVATE@[invalid/policy") == "Unparseable source URL"


def test_resolver_json_roundtrip_preserves_socket_address_tuple(monkeypatch):
    addresses = [[socket.AF_INET, socket.SOCK_STREAM, 6, "", ["8.8.8.8", 443]]]
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(addresses).encode())
    )
    assert policy_fetch.resolve_addresses("public.example", 443)[0][4] == ("8.8.8.8", 443)
