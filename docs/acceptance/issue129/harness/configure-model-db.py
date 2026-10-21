"""Configure the lab web intake through its own Postgres-backed document store.

The HTTP settings endpoint is intentionally forbidden in remote mode; the
operator configures the controlled extractor directly here, exactly where the
product stores model.json.
"""
import os
from pathlib import Path

from privacytrace.postgres_intake import PostgresWebIntake
from privacytrace.storage_factory import create_store
from privacytrace.web_models import ModelSettings

store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
intake = PostgresWebIntake(store)
print("root:", intake.root)
try:
    print("before:", intake.settings(private=True))
except Exception as exc:  # noqa: BLE001
    print("before-error:", type(exc).__name__, exc)
intake.configure(ModelSettings(
    enabled=True,
    api_base="http://127.0.0.1:19545/v1",
    model="controlled-extractor",
))
print("after:", intake.settings(private=True))
