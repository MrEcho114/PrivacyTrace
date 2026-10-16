"""Backend selection must never turn incomplete remote configuration into JSON access."""

import pytest

from privacytrace.job_store import JobStore
from privacytrace.storage_factory import create_store


def test_default_json_and_operator_migration_url_are_independent(tmp_path, monkeypatch):
    monkeypatch.delenv("PRIVACYTRACE_STORAGE", raising=False)
    monkeypatch.setenv("PRIVACYTRACE_MIGRATION_DATABASE_URL", "never-use-as-runtime")
    assert isinstance(create_store(tmp_path), JobStore)
    assert not (tmp_path / "instances").exists()


@pytest.mark.parametrize("runtime,instance", [(None, None), (None, "a"), ("invalid", None)])
def test_postgres_missing_runtime_configuration_refuses_fallback(
    tmp_path,
    monkeypatch,
    runtime,
    instance,
):
    monkeypatch.setenv("PRIVACYTRACE_STORAGE", "postgres")
    monkeypatch.setenv("PRIVACYTRACE_MIGRATION_DATABASE_URL", "never-use-as-runtime")
    for name, value in (
        ("PRIVACYTRACE_DATABASE_URL", runtime),
        ("PRIVACYTRACE_INSTANCE_ID", instance),
    ):
        monkeypatch.delenv(name, raising=False)
        if value:
            monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="runtime database URL"):
        create_store(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unknown_backend_refuses_json_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVACYTRACE_STORAGE", "postgress")
    with pytest.raises(ValueError, match="json or postgres"):
        create_store(tmp_path)
    assert list(tmp_path.iterdir()) == []
