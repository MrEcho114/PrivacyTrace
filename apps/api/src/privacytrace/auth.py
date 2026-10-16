"""Capability token generation, hashing, and SecuritySeam authorization."""

import hashlib
import hmac
import re
import secrets

from fastapi import HTTPException, Request

from .config import ServerConfig
from .storage_seam import JobStorageProtocol

TOKEN_REGEX = re.compile(r"^pt_cap_[A-Za-z0-9_-]{20,}$")


def generate_capability_token() -> tuple[str, str]:
    """Generate (plaintext_token, sha256_digest). Format: pt_cap_<urlsafe_base64>."""
    random_part = secrets.token_urlsafe(32)
    token = f"pt_cap_{random_part}"
    digest = hash_token(token)
    return token, digest


def hash_token(token: str) -> str:
    """Compute SHA-256 hex digest of the plaintext token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def extract_token_from_request(request: Request) -> str | None:
    """Extract token from Authorization Bearer or X-PrivacyTrace-Token header.

    If query params contain token or capability_token, immediately raise 400.
    """
    for qk, qv in request.query_params.multi_items():
        qk_lower = qk.lower()
        if (
            qk_lower in ("token", "capability_token", "pt_token", "access_token")
            or "token" in qk_lower
            or qv.startswith("pt_cap_")
        ):
            raise HTTPException(
                status_code=400,
                detail="Token in query parameters is prohibited",
            )

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[len("Bearer ") :].strip()

    custom_header = request.headers.get("X-PrivacyTrace-Token")
    if custom_header:
        return custom_header.strip()

    return None


def authorize_draft_access(request: Request, service, draft_id: str) -> None:
    """Shared pre-body and route check for a remote draft capability."""
    token = extract_token_from_request(request)
    if not token or not TOKEN_REGEX.fullmatch(token):
        raise HTTPException(status_code=401, detail="Draft capability token required")
    try:
        digest = service.get_draft_token_digest(draft_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="DRAFT_NOT_FOUND") from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="DRAFT_NOT_FOUND") from exc
    if not digest or not hmac.compare_digest(hash_token(token), digest):
        raise HTTPException(status_code=403, detail="Draft access denied")


class SecuritySeam:
    """Enforces endpoint access matrix and token verification."""

    def __init__(self, config: ServerConfig, storage: JobStorageProtocol):
        self.config = config
        self.storage = storage

    def authorize_jobs_listing(self, request: Request) -> None:
        if self.config.mode == "remote":
            raise HTTPException(
                status_code=403, detail="Jobs listing forbidden in remote mode"
            )

    def authorize_admin_settings(self, request: Request) -> None:
        if self.config.mode == "remote":
            raise HTTPException(
                status_code=403, detail="Admin settings forbidden in remote mode"
            )

    def authorize_job_access(
        self, request: Request, job_id: str, action: str = "read"
    ) -> None:
        # In local mode, standard loopback checks apply
        if self.config.mode == "local":
            if action in ("write", "delete", "review", "cancel"):
                from .main import local_write

                local_write(request)
            return

        # In remote mode: check tombstone status first
        if self.storage.is_tombstoned(job_id):
            raise HTTPException(status_code=404, detail="Job not found or deleted")

        # In remote mode:
        token = extract_token_from_request(request)
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Capability token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not TOKEN_REGEX.match(token) or len(token) < 32:
            raise HTTPException(
                status_code=401,
                detail="Invalid capability token format",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            stored_digest = self.storage.get_token_digest(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Job not found")

        if not stored_digest:
            raise HTTPException(
                status_code=403, detail="Access to job denied with provided token"
            )

        token_hash = hash_token(token)
        if not hmac.compare_digest(token_hash, stored_digest):
            raise HTTPException(
                status_code=403, detail="Access to job denied with provided token"
            )
