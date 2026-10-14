"""Bounded public HTML capture, with DNS pinning and revalidated redirects."""

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 200000
FAKE_IP_RANGE = ipaddress.ip_network("198.18.0.0/15")


def display_url(url):
    """Keep origin/path and query keys, never publish potentially signed query values."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return "Unparseable source URL"
    query = urlencode(
        [(key, "REDACTED") for key, _ in parse_qsl(parts.query, keep_blank_values=True)]
    )
    return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, query, ""))


class FetchError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _public_dns_direct(host, port, timeout):
    """Resolve only benchmark-range DNS answers through a fixed authenticated resolver.

    Proxy fake-IP answers cannot be connected to by this public-fetch seam. Only
    global A records from HTTPS DNS may replace them; private/mixed DNS remains rejected.
    """
    try:
        request = urllib.request.Request(
            "https://dns.alidns.com/resolve?name=" + quote(host, safe="") + "&type=1",
            headers={"Accept": "application/dns-json"},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError
        payload = json.loads(raw)
        if payload.get("Status") != 0:
            raise ValueError
        ips = [
            ipaddress.ip_address(a["data"]) for a in payload.get("Answer", []) if a.get("type") == 1
        ]
        if not ips or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in ips):
            raise ValueError
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (str(ip), port)) for ip in ips]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise FetchError("FETCH_DNS_FAILED") from exc


def resolve_addresses(host, port, timeout=5, mode="system"):
    # A socket timeout does not bound getaddrinfo. An owned short-lived resolver
    # process bounds both system DNS and DNS-over-HTTPS, including their DNS step.
    if timeout <= 0:
        raise FetchError("FETCH_TIMEOUT")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "privacytrace.policy_fetch",
                mode,
                host,
                str(port),
                str(timeout),
            ],
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode or len(result.stdout) > 65536:
            raise ValueError
        values = json.loads(result.stdout)
        return [(a[0], a[1], a[2], a[3], tuple(a[4])) for a in values]
    except subprocess.TimeoutExpired as exc:
        raise FetchError("FETCH_TIMEOUT") from exc
    except (OSError, ValueError) as exc:
        raise FetchError("FETCH_DNS_FAILED") from exc


def public_dns(host, port, timeout=5):
    return resolve_addresses(host, port, timeout, mode="public")


def public_target(url, timeout=15):
    deadline = time.monotonic() + timeout
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise FetchError("PUBLIC_URL_REQUIRED") from exc
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise FetchError("PUBLIC_URL_REQUIRED")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("PUBLIC_URL_REQUIRED") from exc
    if port not in {80, 443}:
        raise FetchError("PUBLIC_URL_REQUIRED")
    addresses = resolve_addresses(parts.hostname, port, min(5, deadline - time.monotonic()))
    ips = [ipaddress.ip_address(a[4][0]) for a in addresses]
    if ips and all(ip.version == 4 and ip in FAKE_IP_RANGE for ip in ips):
        try:
            ipaddress.ip_address(parts.hostname)
        except ValueError:
            addresses = public_dns(parts.hostname, port, min(5, deadline - time.monotonic()))
            ips = [ipaddress.ip_address(a[4][0]) for a in addresses]
    if not ips or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in ips):
        raise FetchError("PUBLIC_URL_REQUIRED")
    return parts, port, addresses[0]


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.skip += 1
        elif not self.skip and tag in {"p", "div", "br", "li", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "template", "noscript"} and self.skip:
            self.skip -= 1
        elif not self.skip and tag in {"p", "div", "li", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def fetch_policy(url, budget_seconds=15):
    deadline = time.monotonic() + budget_seconds
    for redirect in range(4):
        parts, port, address = public_target(url, timeout=deadline - time.monotonic())
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("FETCH_TIMEOUT")
        connection = http.client.HTTPConnection(parts.hostname, port, timeout=remaining)
        watchdog = None
        expired = threading.Event()
        try:
            # Connect to the exact validated address; do not resolve the host a second time.
            family, socktype, proto, _, sockaddr = address
            sock = socket.socket(family, socktype, proto)
            connection.sock = sock
            sock.settimeout(remaining)

            def end_budget(owned_socket):
                expired.set()
                try:
                    owned_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            watchdog = threading.Timer(remaining, end_budget, args=(sock,))
            watchdog.daemon = True
            watchdog.start()
            sock.connect(sockaddr)
            if parts.scheme == "https":
                connection.sock = ssl.create_default_context().wrap_socket(
                    sock, server_hostname=parts.hostname, do_handshake_on_connect=False
                )
                # TLS takes ownership of the raw descriptor, so replace the watchdog's target.
                watchdog.cancel()
                watchdog = threading.Timer(
                    max(0, deadline - time.monotonic()), end_budget, args=(connection.sock,)
                )
                watchdog.daemon = True
                watchdog.start()
                connection.sock.settimeout(max(0.001, deadline - time.monotonic()))
                connection.sock.do_handshake()
            active_socket = connection.sock
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            connection.request(
                "GET",
                path,
                headers={
                    "Host": parts.netloc,
                    "User-Agent": "PrivacyTrace/0.1 policy capture",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Encoding": "identity",
                },
            )
            response = connection.getresponse()
            if expired.is_set() or time.monotonic() >= deadline:
                raise FetchError("FETCH_TIMEOUT")
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location or redirect == 3:
                    raise FetchError("FETCH_REDIRECT_LIMIT")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise FetchError("FETCH_HTTP_FAILED")
            content_type = response.getheader("Content-Type", "")
            if (
                content_type.split(";", 1)[0].strip().lower()
                not in {"text/html", "application/xhtml+xml"}
                or response.getheader("Content-Encoding", "identity") != "identity"
            ):
                raise FetchError("FETCH_HTML_REQUIRED")
            raw = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FetchError("FETCH_TIMEOUT")
                active_socket.settimeout(remaining)
                chunk = response.read1(min(65536, MAX_HTML_BYTES + 1 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) > MAX_HTML_BYTES:
                    raise FetchError("FETCH_TOO_LARGE")
            charset = re.search(r"charset\s*=\s*[\"']?([\w-]+)", content_type, re.I)
            if expired.is_set() or time.monotonic() >= deadline:
                raise FetchError("FETCH_TIMEOUT")
            encoding = charset[1].lower() if charset else "utf-8"
            if encoding not in {"utf-8", "utf8", "gbk", "gb2312", "gb18030", "iso-8859-1"}:
                raise FetchError("FETCH_ENCODING_UNSUPPORTED")
            parser = HTMLText()
            parser.feed(bytes(raw).decode(encoding))
            text = re.sub(r"\n[ \t\n]+", "\n", "".join(parser.parts)).strip()
            if not text:
                raise FetchError("FETCH_TEXT_MISSING")
            if len(text) > MAX_TEXT_CHARS:
                raise FetchError("FETCH_TOO_LARGE")
            if time.monotonic() >= deadline:
                raise FetchError("FETCH_TIMEOUT")
            return {
                "text": text,
                "final_url": url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "status": "ready",
                "error_code": None,
            }
        except (OSError, http.client.HTTPException, UnicodeError) as exc:
            timed_out = expired.is_set() or isinstance(exc, TimeoutError) or time.monotonic() >= deadline
            raise FetchError("FETCH_TIMEOUT" if timed_out else "FETCH_FAILED") from exc
        finally:
            if watchdog:
                watchdog.cancel()
            connection.close()
    raise FetchError("FETCH_REDIRECT_LIMIT")


if __name__ == "__main__":
    try:
        mode, host, port, timeout = sys.argv[1:]
        addresses = (
            _public_dns_direct(host, int(port), float(timeout))
            if mode == "public"
            else socket.getaddrinfo(host, int(port), type=socket.SOCK_STREAM)
        )
        print(json.dumps(addresses))
    except Exception:
        raise SystemExit(2) from None
