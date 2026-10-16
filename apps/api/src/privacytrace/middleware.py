"""Transport security, resource bounds, rate limiting, and log redaction middleware."""

import ipaddress
import logging
import re
import time
from collections import defaultdict
from threading import Lock
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import ServerConfig

TOKEN_PATTERN = re.compile(r"pt_cap_[A-Za-z0-9_-]{20,}")


def redact_log_value(value, depth=0):
    """Mask tokens in structured and non-string logging fields before formatting."""
    if isinstance(value, str):
        return TOKEN_PATTERN.sub("pt_cap_***", value)
    if depth >= 12:
        return TOKEN_PATTERN.sub("pt_cap_***", str(value))
    if isinstance(value, dict):
        return {
            redact_log_value(key, depth + 1): redact_log_value(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_log_value(item, depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_log_value(item, depth + 1) for item in value)
    if isinstance(value, (set, frozenset)):
        return type(value)(redact_log_value(item, depth + 1) for item in value)
    if isinstance(value, (int, float, bool, type(None))):
        return value
    # Unknown objects and bytes may render sensitive data via str()/repr().
    rendered = str(value)
    return TOKEN_PATTERN.sub("pt_cap_***", rendered) if TOKEN_PATTERN.search(rendered) else value


class TokenRedactionFilter(logging.Filter):
    """Sanitize structured records before formatter/handler access."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            import traceback

            formatted = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = TOKEN_PATTERN.sub("pt_cap_***", formatted)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = TOKEN_PATTERN.sub("pt_cap_***", record.exc_text)

        # Includes msg, args, stack_info and user-defined "extra" fields. This
        # also covers non-string msg objects and nested dictionaries.
        for key, value in list(record.__dict__.items()):
            if key not in ("exc_info", "exc_text"):
                record.__dict__[key] = redact_log_value(value)
        return True


def install_log_redaction() -> None:
    # Sanitize before any logger routes records to existing or future handlers.
    current_factory = logging.getLogRecordFactory()
    if not getattr(current_factory, "_privacytrace_redacts_tokens", False):
        sanitizer = TokenRedactionFilter()

        def redacting_factory(*args, **kwargs):
            record = current_factory(*args, **kwargs)
            sanitizer.filter(record)
            return record

        redacting_factory._privacytrace_redacts_tokens = True
        logging.setLogRecordFactory(redacting_factory)

    redaction_filter = TokenRedactionFilter()
    root_logger = logging.getLogger()
    if redaction_filter not in root_logger.filters:
        root_logger.addFilter(redaction_filter)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "privacytrace"):
        logger = logging.getLogger(name)
        if redaction_filter not in logger.filters:
            logger.addFilter(redaction_filter)


class RateLimiter:
    """Sliding-window in-memory rate limiter per client IP."""

    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self.window = 60.0
        self.history: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()

    def is_allowed(self, client_ip: str) -> bool:
        now = time.monotonic()
        with self.lock:
            timestamps = self.history[client_ip]
            self.history[client_ip] = [t for t in timestamps if now - t < self.window]
            if len(self.history[client_ip]) >= self.limit:
                return False
            self.history[client_ip].append(now)
            return True


class RemoteTransportSecurityMiddleware(BaseHTTPMiddleware):
    """Enforces Host validation, Origin checking, proxy verification,
    anti-spoofing, and rate limits."""

    def __init__(self, app, config: ServerConfig):
        super().__init__(app)
        self.config = config
        self.rate_limiter = RateLimiter(config.rate_limit_per_minute)
        self.trusted_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for p in self.config.trusted_proxies:
            p = p.strip()
            if not p:
                continue
            try:
                self.trusted_networks.append(ipaddress.ip_network(p, strict=False))
            except ValueError:
                pass
        install_log_redaction()

    def is_host_allowed(self, host_part: str) -> bool:
        host_part = host_part.strip().rstrip(".").lower()
        if not host_part:
            return False
        for pattern in self.config.allowed_hosts:
            pat = pattern.strip().rstrip(".").lower()
            if pat == "*":
                return True
            if pat.startswith("*."):
                suffix = pat[2:]
                if host_part.endswith("." + suffix):
                    prefix = host_part[: -(len(suffix) + 1)]
                    if prefix and "." not in prefix:
                        return True
            elif host_part == pat:
                return True
            elif (
                host_part.startswith("[")
                and host_part.endswith("]")
                and host_part[1:-1] == pat
            ):
                return True
            elif (
                pat.startswith("[")
                and pat.endswith("]")
                and pat[1:-1] == host_part
            ):
                return True
        return False

    def validate_host_header(self, host_header: str | None) -> bool:
        if host_header is None:
            return False
        host_header = host_header.strip()
        if not host_header or "," in host_header:
            return False

        if host_header.startswith("["):
            end_idx = host_header.find("]")
            if end_idx == -1:
                return False
            ipv6_str = host_header[1:end_idx]
            try:
                ipaddress.IPv6Address(ipv6_str)
            except ValueError:
                return False
            host_part = f"[{ipv6_str.lower()}]"
            rest = host_header[end_idx + 1 :]
            if rest:
                if not rest.startswith(":"):
                    return False
                port_str = rest[1:]
                if not port_str.isdigit():
                    return False
                port = int(port_str)
                if not (0 < port <= 65535):
                    return False
        else:
            if ":" in host_header:
                parts = host_header.split(":")
                if len(parts) > 2:
                    # Unbracketed IPv6 (e.g. ::1)
                    return False
                host_part, port_str = parts[0], parts[1]
                if not port_str.isdigit():
                    return False
                port = int(port_str)
                if not (0 < port <= 65535):
                    return False
            else:
                host_part = host_header

        return self.is_host_allowed(host_part)

    async def dispatch(self, request: Request, call_next):
        # 1. Reject capability tokens in query parameters
        for qk, qv in request.query_params.multi_items():
            qk_lower = qk.lower()
            if (
                qk_lower in ("token", "capability_token", "pt_token", "access_token")
                or "token" in qk_lower
                or qv.startswith("pt_cap_")
            ):
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Capability token in query parameters is prohibited"
                    },
                )

        # 2. Anti-spoofing of local header in remote mode
        if self.config.mode == "remote":
            for header_name in request.headers.keys():
                if header_name.lower() == "x-privacytrace-local":
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Local header forbidden in remote mode"},
                    )

        # 3. Robust Host validation (replacing Starlette's flawed split)
        host_header = request.headers.get("host")
        if not self.validate_host_header(host_header):
            return PlainTextResponse("Invalid host header", status_code=400)

        # 4. Origin header validation on write requests (POST, PUT, DELETE, PATCH)
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            if origin:
                origin = origin.strip()
                try:
                    parsed_origin = urlparse(origin)
                except Exception:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Cross-origin write rejected"},
                    )
                if (
                    parsed_origin.scheme not in ("http", "https")
                    or not parsed_origin.hostname
                    or parsed_origin.username
                    or parsed_origin.password
                    or "@" in (parsed_origin.netloc or "")
                ):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Cross-origin write rejected"},
                    )
                origin_host = parsed_origin.hostname.lower()
                if self.config.mode == "local":
                    allowed_origins = {"127.0.0.1", "localhost", "::1", "testserver"}
                    if origin_host not in allowed_origins:
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Cross-origin write rejected"},
                        )
                else:
                    if not self.is_host_allowed(origin_host):
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Cross-origin write rejected"},
                        )

        # 5. Reverse proxy header validation
        peer_host = request.client.host if request.client else None
        if peer_host in ("testclient", "localhost"):
            peer_ip_obj = ipaddress.ip_address("127.0.0.1")
        elif peer_host:
            try:
                peer_ip_obj = ipaddress.ip_address(peer_host)
            except ValueError:
                peer_ip_obj = None
        else:
            peer_ip_obj = None

        is_trusted_peer = False
        if peer_ip_obj:
            is_trusted_peer = any(peer_ip_obj in net for net in self.trusted_networks)

        has_proxy_headers = any(
            h in request.headers
            for h in (
                "x-forwarded-for",
                "x-forwarded-proto",
                "x-forwarded-host",
                "forwarded",
            )
        )

        if has_proxy_headers and not is_trusted_peer:
            return JSONResponse(
                status_code=400,
                content={"detail": "Untrusted forwarding headers"},
            )

        effective_client_ip = (
            str(peer_ip_obj) if peer_ip_obj else (peer_host or "unknown")
        )

        if has_proxy_headers and is_trusted_peer:
            # Validate X-Forwarded-Proto
            xf_proto = request.headers.get("x-forwarded-proto")
            if xf_proto and xf_proto.lower().strip() not in ("http", "https"):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Malformed X-Forwarded-Proto header"},
                )

            # Validate RFC 7239 Forwarded header
            forwarded = request.headers.get("forwarded")
            if forwarded:
                for element in forwarded.split(","):
                    directives = [d.strip() for d in element.split(";") if d.strip()]
                    for directive in directives:
                        if "=" in directive:
                            k, v = directive.split("=", 1)
                            k = k.lower().strip()
                            v = v.strip().strip('"')
                            if k == "proto" and v.lower() not in ("http", "https"):
                                return JSONResponse(
                                    status_code=400,
                                    content={"detail": "Malformed Forwarded header"},
                                )
                            if k == "for":
                                v_clean = v.strip("[]")
                                if ":" in v_clean and "." in v_clean:
                                    v_clean = v_clean.split(":")[0]
                                try:
                                    ipaddress.ip_address(v_clean)
                                except ValueError:
                                    return JSONResponse(
                                        status_code=400,
                                        content={"detail": "Malformed Forwarded header"},
                                    )

            # Validate and traverse X-Forwarded-For
            xf_for = request.headers.get("x-forwarded-for")
            if xf_for:
                entries = [e.strip() for e in xf_for.split(",")]
                parsed_chain: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
                for entry in entries:
                    if not entry:
                        return JSONResponse(
                            status_code=400,
                            content={"detail": "Malformed X-Forwarded-For header"},
                        )
                    entry_clean = entry.strip('"').strip("'")
                    if entry_clean.startswith("["):
                        idx = entry_clean.find("]")
                        if idx == -1:
                            return JSONResponse(
                                status_code=400,
                                content={"detail": "Malformed X-Forwarded-For header"},
                            )
                        entry_clean = entry_clean[1:idx]
                    elif ":" in entry_clean and "." in entry_clean:
                        entry_clean = entry_clean.split(":")[0]
                    try:
                        ip_obj = ipaddress.ip_address(entry_clean)
                        parsed_chain.append(ip_obj)
                    except ValueError:
                        return JSONResponse(
                            status_code=400,
                            content={"detail": "Malformed X-Forwarded-For header"},
                        )

                # Reverse traversal (right-to-left) to find first non-trusted IP
                found_non_trusted = None
                for ip_obj in reversed(parsed_chain):
                    if not any(ip_obj in net for net in self.trusted_networks):
                        found_non_trusted = str(ip_obj)
                        break
                if found_non_trusted is not None:
                    effective_client_ip = found_non_trusted
                elif parsed_chain:
                    effective_client_ip = str(parsed_chain[0])

        request.state.client_ip = effective_client_ip

        # 6. Rate limiting in remote mode
        if self.config.mode == "remote":
            if not self.rate_limiter.is_allowed(effective_client_ip):
                return JSONResponse(
                    status_code=429,
                    headers={
                        "Retry-After": "60",
                        "Content-Type": "application/json",
                    },
                    content={"detail": "Rate limit exceeded"},
                )

        # 7. Local write enforcement in local mode for /api/v1/web/ writes
        if (
            self.config.mode == "local"
            and request.method in ("POST", "PUT", "DELETE", "PATCH")
            and request.url.path.startswith("/api/v1/web/")
        ):
            try:
                from .main import local_write

                local_write(request)
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code, content={"detail": exc.detail}
                )

        response = await call_next(request)
        return response


class JobWriteBoundsMiddleware(BaseHTTPMiddleware):
    """Enforces request payload size limits across endpoints."""

    def __init__(self, app, config: ServerConfig):
        super().__init__(app)
        self.config = config

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if request.method == "POST":
            if self.config.mode == "local" and path.startswith("/api/v1/web/"):
                from .main import local_write

                try:
                    local_write(request)
                except HTTPException as exc:
                    return JSONResponse(
                        status_code=exc.status_code, content={"detail": exc.detail}
                    )

            # APK upload bound (150 MiB)
            if "/drafts/" in path and path.endswith("/apk"):
                length = request.headers.get("content-length")
                if length and (
                    not length.isdigit()
                    or int(length) > self.config.max_apk_body_bytes
                ):
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "UPLOAD_TOO_LARGE"},
                    )
                # Preserve request streaming: WebIntake.upload validates the
                # draft capability before consuming any body bytes, then
                # streams directly to a bounded private temporary file.

            # Web drafts bound (8 MiB)
            elif path.startswith("/api/v1/web/drafts"):
                length = request.headers.get("content-length")
                if length and (
                    not length.isdigit()
                    or int(length) > self.config.max_draft_body_bytes
                ):
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "INPUT_TOO_LARGE"},
                    )
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > self.config.max_draft_body_bytes:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "INPUT_TOO_LARGE"},
                        )
                    chunks.append(chunk)
                request._body = b"".join(chunks)

            # Jobs writes bound (512 KiB)
            elif path == "/api/v1/jobs" or path.startswith("/api/v1/jobs/"):
                length = request.headers.get("content-length")
                if length and (
                    not length.isdigit()
                    or int(length) > self.config.max_json_body_bytes
                ):
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request too large"},
                    )
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > self.config.max_json_body_bytes:
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Request too large"},
                        )
                    chunks.append(chunk)
                request._body = b"".join(chunks)

        return await call_next(request)
