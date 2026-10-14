"""Bounded public HTML capture, with DNS pinning and revalidated redirects."""

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

MAX_HTML_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 200000
FAKE_IP_RANGE = ipaddress.ip_network("198.18.0.0/15")


class FetchError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def public_dns(host, port):
    """Resolve only benchmark-range DNS answers through a fixed authenticated resolver.

    Proxy fake-IP answers cannot be connected to by this public-fetch seam. Only
    global A records from HTTPS DNS may replace them; private/mixed DNS remains rejected.
    """
    try:
        request = urllib.request.Request(
            "https://dns.google/resolve?name=" + quote(host, safe="") + "&type=A",
            headers={"Accept": "application/dns-json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
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


def public_target(url):
    parts = urlsplit(url)
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
    try:
        addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError("FETCH_DNS_FAILED") from exc
    ips = [ipaddress.ip_address(a[4][0]) for a in addresses]
    if ips and all(ip.version == 4 and ip in FAKE_IP_RANGE for ip in ips):
        try:
            ipaddress.ip_address(parts.hostname)
        except ValueError:
            addresses = public_dns(parts.hostname, port)
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


def fetch_policy(url):
    deadline = time.monotonic() + 15
    for redirect in range(4):
        parts, port, address = public_target(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("FETCH_TIMEOUT")
        connection = http.client.HTTPConnection(parts.hostname, port, timeout=remaining)
        try:
            # Connect to the exact validated address; do not resolve the host a second time.
            family, socktype, proto, _, sockaddr = address
            sock = socket.socket(family, socktype, proto)
            connection.sock = sock
            sock.settimeout(remaining)
            sock.connect(sockaddr)
            if parts.scheme == "https":
                connection.sock = ssl.create_default_context().wrap_socket(
                    sock, server_hostname=parts.hostname
                )
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
            return {
                "text": text,
                "final_url": url,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "status": "ready",
                "error_code": None,
            }
        except (OSError, http.client.HTTPException, UnicodeError) as exc:
            raise FetchError("FETCH_FAILED") from exc
        finally:
            connection.close()
    raise FetchError("FETCH_REDIRECT_LIMIT")
