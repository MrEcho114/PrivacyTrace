"""Policy discovery must use the same isolated inspector as upload validation.

Regression for BUG-01: the durable control plane has no Docker socket, so
``_discover_sources`` may not call the module-level local container inspector.
"""

from fastapi.testclient import TestClient

from privacytrace import web_intake
from privacytrace.durable_intake import DurableWebIntake
from privacytrace.main import create_app

HEADERS = {"X-PrivacyTrace-Local": "1"}
DISCOVERED = "https://example.invalid/policy.html"


def _metadata():
    return {
        "policy_urls": [DISCOVERED],
        "package_file": {"package_name": "org.privacytrace.probe.fixture", "version_code": 1},
        "coverage": {"limitations": []},
    }


def test_discovery_uses_the_injected_inspector(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={
                "name": "org.privacytrace.probe.fixture",
                "sources": [{"id": "pending", "title": "政策待补充"}],
            },
        )
        assert created.status_code == 200, created.text
        draft_id = created.json()["id"]
        service = app.state.web_intake

        packages = service.directory(draft_id) / "packages"
        packages.mkdir(parents=True)
        (packages / "base.apk").write_bytes(b"controlled-fixture-bytes")

        calls = []

        def injected(path, *, timeout=120):
            calls.append(str(path))
            return _metadata()

        monkeypatch.setattr(service, "inspect_metadata", injected)
        monkeypatch.setattr(
            web_intake,
            "inspect_package_isolated",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("local inspector used")
            ),
        )

        result = service._discover_sources(draft_id)

        assert calls, "discovery did not call the injected inspector"
        urls = {source.get("url") for source in result["sources"]}
        assert DISCOVERED in urls


def test_durable_inspector_is_runner_backed():
    class Runner:
        def __init__(self):
            self.calls = []

        def inspect_metadata(self, path, *, timeout=120):
            self.calls.append((str(path), timeout))
            return _metadata()

    runner = Runner()
    service = object.__new__(DurableWebIntake)
    service.runner = runner

    metadata = service.inspect_metadata("base.apk", timeout=7)

    assert metadata["policy_urls"] == [DISCOVERED]
    assert runner.calls == [("base.apk", 7)]
