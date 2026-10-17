"""Explicit backend selection; the local CLI continues to instantiate JSON storage."""

import os
from pathlib import Path

from .job_store import JobStore
from .resources import ROOT


def create_store(root: Path | None = None):
    backend = os.environ.get("PRIVACYTRACE_STORAGE", "json").strip().lower()
    root = Path(root) if root is not None else ROOT / "data" / "jobs"
    if backend == "json":
        return JobStore(root)
    if backend != "postgres":
        raise ValueError("PRIVACYTRACE_STORAGE must be json or postgres")
    url = os.environ.get("PRIVACYTRACE_DATABASE_URL")
    instance = os.environ.get("PRIVACYTRACE_INSTANCE_ID")
    if not url or not instance:
        raise ValueError("PostgreSQL requires a runtime database URL and a stable instance UUID")
    from .postgres_store import PostgresJobStore

    return PostgresJobStore(url, instance, root)
