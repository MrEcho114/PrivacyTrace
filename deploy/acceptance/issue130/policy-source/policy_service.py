#!/usr/bin/env python3
"""Controlled policy source for Issue #130 N09/N10 fault injection.

Run this inside the disposable laboratory network namespace and point the
product's globally-routable placeholder (default 1.0.0.1:80) at it with the
namespace DNAT documented in README.md. It must not be exposed outside the lab.
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LOG_DIR = Path(os.environ.get("PT130_LOG_DIR", "/var/tmp/pt130-policy"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
REQUEST_LOG = LOG_DIR / "policy-requests.jsonl"
INTERNAL_LOG = LOG_DIR / "internal-access.log"
PUBLIC_PORT = int(os.environ.get("PT130_POLICY_PORT", "8082"))
INTERNAL_PORT = int(os.environ.get("PT130_INTERNAL_PORT", "19090"))

POLICY_TEXT = "本自建测试应用申请精确位置权限，用于权限能力研究。我们访问精确位置。无附件。"
ALT_TEXT = "本自建测试应用不会读取联系人。我们仅提供离线帮助页面。"
STATE = {"flaky": 0}


def append(path, payload):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def _send(self, status, body=b"", content_type="text/html; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        append(
            REQUEST_LOG,
            {
                "at": time.time(),
                "path": path,
                "client": self.client_address[0],
                "host": self.headers.get("Host"),
            },
        )
        if path == "/policy.html":
            self._send(200, f"<html><body><p>{POLICY_TEXT}</p></body></html>".encode())
        elif path == "/policy-alt.html":
            self._send(200, f"<html><body><p>{ALT_TEXT}</p></body></html>".encode())
        elif path == "/flaky-policy":
            STATE["flaky"] += 1
            if STATE["flaky"] == 1:
                self._send(200, f"<html><body><p>{POLICY_TEXT}</p></body></html>".encode())
            else:
                self._send(500, b"injected failure")
        elif path == "/fail":
            self._send(500, b"injected failure")
        elif path == "/wrong-type":
            self._send(200, b"plain text", "text/plain; charset=utf-8")
        elif path == "/huge":
            chunk = ("<p>" + "A" * 4096 + "</p>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(3 * 1024 * 1024))
            self.end_headers()
            for _ in range((3 * 1024 * 1024) // len(chunk)):
                self.wfile.write(chunk)
        elif path == "/slow":
            time.sleep(30)
            self._send(200, b"<html><body><p>late policy</p></body></html>")
        elif path == "/redirect-local":
            self._send(302, b"", extra={"Location": f"http://127.0.0.1:{INTERNAL_PORT}/secret"})
        elif path == "/redirect-private":
            self._send(302, b"", extra={"Location": "http://10.0.0.1/secret"})
        elif path == "/redirect-metadata":
            self._send(302, b"", extra={"Location": "http://169.254.169.254/latest/meta-data/"})
        elif path == "/redirect-loop":
            self._send(302, b"", extra={"Location": "http://1.0.0.1/redirect-loop"})
        else:
            self._send(404, b"not found")


class InternalHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def do_GET(self):
        append(
            INTERNAL_LOG,
            {"at": time.time(), "path": self.path, "client": self.client_address[0]},
        )
        body = b"INTERNAL_SECRET_MARKER"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    internal = ThreadingHTTPServer(("127.0.0.1", INTERNAL_PORT), InternalHandler)
    public = ThreadingHTTPServer(("0.0.0.0", PUBLIC_PORT), Handler)
    threading.Thread(target=internal.serve_forever, daemon=True).start()
    print("POLICY_SERVICE_READY", flush=True)
    public.serve_forever()
