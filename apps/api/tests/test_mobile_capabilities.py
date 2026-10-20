"""HTTP contract checks; fake durable state is not a deployment acceptance."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from privacytrace.config import ServerConfig
from privacytrace.main import create_app
from privacytrace.mobile_capabilities import install_mobile_capabilities

INSTANCE = "12345678-1234-4234-8234-123456789abc"


@pytest.mark.parametrize(
    "mode,durable,postgres,instance,deletion,supported",
    [
        ("remote", True, True, INSTANCE, True, True),
        ("local", True, True, INSTANCE, True, False),
        ("remote", False, True, INSTANCE, True, False),
        ("remote", True, False, INSTANCE, True, False),
        ("remote", True, True, "invalid", True, False),
        ("remote", True, True, INSTANCE, False, False),
    ],
)
def test_transport_contract(mode, durable, postgres, instance, deletion, supported):
    app = FastAPI()
    app.state.config = ServerConfig(mode=mode, max_apk_body_bytes=1024)
    app.state.job_store = SimpleNamespace(uses_postgres=postgres, instance_id=instance)
    app.state.web_intake = SimpleNamespace(delete_draft=(lambda: None) if deletion else None)
    install_mobile_capabilities(app, durable=durable)
    response = TestClient(app).get("/api/v1/mobile-capabilities")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    value = response.json()
    assert value["supported"] is supported
    if supported:
        assert value == {
            "protocol": "privacytrace-mobile/1", "supported": True,
            "instance_id": INSTANCE, "upload_format": "apk-or-zip",
            "max_upload_bytes": 1024, "max_file_bytes": 150 * 1024 * 1024,
            "max_total_bytes": 150 * 1024 * 1024, "max_files": 101,
            "retention": "UNTIL_EXPLICIT_DELETE", "delete_draft": True,
        }
    else:
        assert value == {"protocol": "privacytrace-mobile/1", "supported": False}


def test_legacy_app_declines_mobile_upload_without_changing_health(tmp_path):
    app = create_app(store_root=tmp_path, mode="remote")
    with TestClient(app) as client:
        assert client.get("/api/v1/mobile-capabilities").json()["supported"] is False
        assert set(client.get("/api/v1/health").json()) == {"status", "mode", "version"}
