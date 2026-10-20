"""Explicit backend selection; the local CLI continues to instantiate JSON storage."""

import os
from pathlib import Path

from .job_store import JobStore
from .resources import ROOT


def resolve_secret(env_var: str, file_env_var: str | None = None) -> str | None:
    """Resolve a credential from an environment variable or a file path."""
    val = os.environ.get(env_var)
    if val is not None and val.strip():
        return val.strip()
    if file_env_var:
        file_path = os.environ.get(file_env_var)
        if file_path is not None and file_path.strip():
            p = Path(file_path.strip())
            if not p.is_file():
                raise ValueError(f"Secret file not found or invalid: {file_env_var}")
            content = p.read_text(encoding="utf-8").strip()
            if not content:
                raise ValueError(f"Secret file not found or invalid: {file_env_var}")
            return content
    return None


def resolve_database_url() -> str | None:
    return resolve_secret("PRIVACYTRACE_DATABASE_URL", "PRIVACYTRACE_DATABASE_URL_FILE")


def resolve_redis_url() -> str | None:
    url = resolve_secret("PRIVACYTRACE_REDIS_URL", "PRIVACYTRACE_REDIS_URL_FILE")
    if not url:
        url = resolve_secret("PRIVACYTRACE_BROKER_URL", "PRIVACYTRACE_BROKER_URL_FILE")
    return url


def create_store(root: Path | None = None):
    backend = os.environ.get("PRIVACYTRACE_STORAGE", "json").strip().lower()
    root = Path(root) if root is not None else ROOT / "data" / "jobs"
    if backend == "json":
        return JobStore(root)
    if backend != "postgres":
        raise ValueError("PRIVACYTRACE_STORAGE must be json or postgres")
    url = resolve_database_url()
    instance = os.environ.get("PRIVACYTRACE_INSTANCE_ID")
    if not url or not instance:
        raise ValueError("PostgreSQL requires a runtime database URL and a stable instance UUID")
    from .postgres_store import PostgresJobStore

    return PostgresJobStore(url, instance, root)

