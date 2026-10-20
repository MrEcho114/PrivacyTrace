"""Private, mutually authenticated runtime HTTP; no environment proxies or redirects."""

import hashlib
import ipaddress
import json
import os
import socket
import ssl
import time
from dataclasses import dataclass, field
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

MAX_JSON = 8 * 1024 * 1024


class RuntimeUnavailable(RuntimeError):
    pass


def private_file(path, *, secret=False):
    path = Path(path).absolute()
    if any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)
    ):
        raise ValueError("Unsafe runtime credential file")
    info = path.stat()
    if not path.is_file() or info.st_size > 1024 * 1024:
        raise ValueError("Invalid runtime credential file")
    if secret and os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("Runtime private key requires private ownership and permissions")
    return path


def private_endpoint(value):
    try:
        parsed = urlsplit(value)
        host = ipaddress.ip_address(parsed.hostname)
        if (
            parsed.scheme != "https"
            or not (host.is_private or host.is_loopback)
            or host.is_unspecified
            or host.is_multicast
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or not parsed.port
            or not 1 <= parsed.port <= 65535
        ):
            raise ValueError
        return value.rstrip("/")
    except (ValueError, TypeError, AttributeError):
        raise ValueError("A fixed private HTTPS endpoint is required") from None


def json_value(raw):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate runtime field")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON")),
    )


@dataclass(frozen=True)
class RuntimeTLS:
    ca: Path = field(repr=False)
    cert: Path = field(repr=False)
    key: Path = field(repr=False)

    @classmethod
    def from_env(cls, prefix):
        try:
            return cls(*(Path(os.environ[prefix + suffix]) for suffix in ("_CA", "_CERT", "_KEY")))
        except (KeyError, TypeError):
            raise ValueError("Private runtime TLS configuration required") from None

    def context(self, *, server=False):
        try:
            ca, cert, key = (
                private_file(self.ca),
                private_file(self.cert),
                private_file(self.key, secret=True),
            )
            purpose = ssl.Purpose.CLIENT_AUTH if server else ssl.Purpose.SERVER_AUTH
            context = ssl.create_default_context(purpose, cafile=str(ca))
            context.minimum_version = ssl.TLSVersion.TLSv1_3
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_cert_chain(str(cert), str(key))
            return context
        except (OSError, ValueError, ssl.SSLError):
            raise ValueError("Private runtime TLS configuration rejected") from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PrivateClient:
    def __init__(self, endpoint, tls, *, timeout=200):
        self.endpoint = private_endpoint(endpoint)
        self.opener = build_opener(
            ProxyHandler({}), NoRedirect(), HTTPSHandler(context=tls.context())
        )
        self.timeout = timeout

    def open(self, path, *, data=None, ticket=None, timeout=None):
        if timeout is not None and (
            type(timeout) not in (int, float) or not 0 < timeout <= self.timeout
        ):
            raise ValueError("Invalid private operation deadline")
        if path not in {"/v1/run", "/v1/material", "/v1/permit", "/v1/health"}:
            raise ValueError("Unknown private runtime operation")
        headers = {"Accept": "application/json"}
        if ticket is not None:
            if (
                type(ticket) is not str
                or not 1 <= len(ticket) <= 2048
                or any(c.isspace() for c in ticket)
            ):
                raise ValueError("Invalid private material ticket")
            headers["Authorization"] = "Bearer " + ticket
        raw = (
            None
            if data is None
            else json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
        )
        if raw is not None:
            if len(raw) > 128 * 1024:
                raise ValueError("Runtime manifest too large")
            headers["Content-Type"] = "application/json"
        request = Request(self.endpoint + path, data=raw, headers=headers)
        try:
            return self.opener.open(request, timeout=self.timeout if timeout is None else timeout)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if status in {401, 403, 404, 409, 410, 422}:
                raise PermissionError("Private runtime operation rejected") from None
            raise RuntimeUnavailable("Private runtime unavailable") from None
        except (URLError, OSError, TimeoutError, ssl.SSLError):
            raise RuntimeUnavailable("Private runtime unavailable") from None

    def json(self, path, *, data=None, ticket=None, timeout=None):
        try:
            effective_timeout = self.timeout if timeout is None else timeout
            with self.open(path, data=data, ticket=ticket, timeout=timeout) as response:
                chunks, count = [], 0
                deadline = time.monotonic() + effective_timeout
                while block := response.read1(min(65536, MAX_JSON + 1 - count)):
                    count += len(block)
                    if count > MAX_JSON or time.monotonic() >= deadline:
                        raise RuntimeUnavailable("Private runtime response exceeds limits")
                    chunks.append(block)
                raw = b"".join(chunks)
        except PermissionError:
            raise
        except (OSError, HTTPException):
            raise RuntimeUnavailable("Private runtime response interrupted") from None
        if len(raw) > MAX_JSON:
            raise RuntimeUnavailable("Private runtime response exceeds limit")
        try:
            return json_value(raw)
        except (ValueError, UnicodeError):
            raise RuntimeUnavailable("Invalid private runtime response") from None


class PrivateServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, handler, tls, peers):
        host = ipaddress.ip_address(address[0])
        if not (host.is_private or host.is_loopback) or host.is_unspecified or host.is_multicast:
            raise ValueError("Private runtime listener required")
        self.context = tls.context(server=True)
        self.address_family = socket.AF_INET6 if host.version == 6 else socket.AF_INET
        self.slots = BoundedSemaphore(16)
        self.peers = frozenset(peers)
        if not self.peers or any(
            len(v) != 64 or any(c not in "0123456789abcdef" for c in v) for v in self.peers
        ):
            raise ValueError("Explicit permitted TLS peer fingerprints required")
        super().__init__(address, handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        try:
            wrapped = self.context.wrap_socket(connection, server_side=True)
            wrapped.settimeout(15)
            return wrapped, address
        except Exception:
            connection.close()
            raise

    def handle_error(self, request, client_address):
        # Never print peer bodies, material tickets or credential-bearing errors.
        return

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class PrivateHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PrivacyTraceRuntime/1"
    sys_version = ""

    def setup(self):
        super().setup()
        self.response_started = False

    def end_headers(self):
        super().end_headers()
        self.response_started = True

    def log_message(self, *args):
        return

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"error": "RUNTIME_REQUEST_REJECTED"})

    def authorized(self):
        certificate = self.connection.getpeercert(binary_form=True)
        return bool(certificate and hashlib.sha256(certificate).hexdigest() in self.server.peers)

    def body(self):
        length = int(self.headers.get("Content-Length", "-1"))
        if (
            not self.authorized()
            or self.headers.get("Transfer-Encoding") is not None
            or self.headers.get("Content-Type") != "application/json"
            or not 0 < length <= 128 * 1024
        ):
            raise ValueError("Invalid private request")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise ValueError("Incomplete private request")
        return json_value(raw)

    def reply(self, status, value):
        raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        if len(raw) > MAX_JSON:
            raise ValueError("Runtime response too large")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def do_GET(self):
        self.reply(404, {"error": "UNKNOWN_RUNTIME_OPERATION"})

    def do_POST(self):
        self.reply(404, {"error": "UNKNOWN_RUNTIME_OPERATION"})
