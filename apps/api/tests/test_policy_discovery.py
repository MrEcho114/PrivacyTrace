"""Policy discovery completeness at the real binary parser and HTTP seams."""

import os

import pytest
from apk_fixture_builder import apk, package_set_archive
from fastapi.testclient import TestClient
from policy_discovery_fixture import policy_resource_apk
from test_web_intake import HEADERS, new_draft

from privacytrace.apk_worker import inspect_package_metadata
from privacytrace.main import create_app

POLICY = "https://example.com/privacy"
LOCALIZED = "https://example.com/fr/privacy"


@pytest.mark.parametrize("attribute", ["value", "resource"])
@pytest.mark.parametrize("reference", [
    0x7F010000, "@string/policy", "@org.privacytrace.fixture:string/policy"
])
def test_manifest_string_resource_urls(tmp_path, attribute, reference):
    sample = policy_resource_apk(
        tmp_path / "policy.apk", attribute=attribute, reference=reference,
        values={"policy": 0x7F010001, "target": POLICY, "unreferenced": "https://other.test/"},
        localized={"fr": {"target": LOCALIZED}},
    )
    assert inspect_package_metadata(sample)["policy_urls"] == [POLICY, LOCALIZED]


@pytest.mark.parametrize("values,reference", [
    (None, 0x7F010000),
    ({"policy": POLICY}, "@string/missing"),
    ({"policy": POLICY}, "@drawable/policy"),
    ({"policy": "javascript:alert(1)", "unreferenced": POLICY}, 0x7F010000),
    ({"policy": "https://", "unreferenced": POLICY}, 0x7F010000),
    ({"policy": "https://example.com/\nprivacy"}, 0x7F010000),
    ({"policy": 0x7F010001, "cycle": 0x7F010000}, 0x7F010000),
])
def test_unresolved_or_non_url_resources_are_not_sources(tmp_path, values, reference):
    sample = policy_resource_apk(tmp_path / "policy.apk", values=values, reference=reference)
    assert inspect_package_metadata(sample)["policy_urls"] == []


@pytest.mark.usefixtures("synthetic_package_metadata")
@pytest.mark.parametrize("base_name,split_name", [
    ("base.apk", "FEATURE.APK"), ("BASE.APK", "Feature.ApK")
])
def test_uppercase_split_only_policy_discovery(tmp_path, base_name, split_name):
    base = apk(tmp_path / base_name)
    split = policy_resource_apk(
        tmp_path / split_name, attribute="resource", values={"policy": POLICY}, split="feature"
    )
    archive = package_set_archive(
        tmp_path / "set.zip", {base_name: base.read_bytes(), split_name: split.read_bytes()}
    )
    with TestClient(create_app(tmp_path / "jobs")) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(
            route + "/package-set", headers=HEADERS, content=archive.read_bytes()
        )
        assert response.status_code == 200, response.text
        for _ in range(2):
            response = client.post(route + "/sources/discover", headers=HEADERS)
            assert response.status_code == 200, response.text
            found = [s for s in response.json()["sources"] if s["url"] == POLICY]
            assert len(found) == 1
            assert found[0]["status"] == "url_only" and not found[0]["text"]
            assert found[0]["provenance"] == "MANIFEST_METADATA"
        assert any(s["url"] == POLICY for s in client.get(route).json()["sources"])


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam")
def test_real_worker_resource_policy_discovery(tmp_path):
    """HTTP intake/discovery with actual ARSC in uppercase split; no parser doubles."""
    base = apk(tmp_path / "BASE.APK")
    split = policy_resource_apk(
        tmp_path / "FEATURE.APK", attribute="resource", split="feature",
        values={"policy": 0x7F010001, "target": POLICY, "unreferenced": "https://other.test/"},
        localized={"fr": {"target": LOCALIZED}},
    )
    archive = package_set_archive(
        tmp_path / "set.zip", {base.name: base.read_bytes(), split.name: split.read_bytes()}
    )
    with TestClient(create_app(tmp_path / "jobs")) as client:
        draft = new_draft(client)
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(
            route + "/package-set", headers=HEADERS, content=archive.read_bytes()
        )
        assert response.status_code == 200, response.text
        response = client.post(route + "/sources/discover", headers=HEADERS)
        assert response.status_code == 200, response.text
        sources = [s for s in response.json()["sources"] if s["provenance"] == "MANIFEST_METADATA"]
        assert {s["url"] for s in sources} == {POLICY, LOCALIZED}
        assert all(s["status"] == "url_only" and not s["text"] for s in sources)
