from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import app

client = TestClient(app)


@pytest.mark.parametrize("length,status", [(12032, 200), (200000, 200), (200001, 422)])
def test_http_api_accepts_full_artifact_and_clearly_rejects_over_limit(bundle_data, length, status):
    text = "甲" * length
    doc = bundle_data["policy_documents"][0]
    doc["artifact"] = {"text": text, "sha256": sha256(text.encode()).hexdigest()}
    bundle_data["policy_claims"] = []
    bundle_data["evidence"] = [e for e in bundle_data["evidence"] if e["kind"] != "POLICY_SENTENCE"]
    next(e for e in bundle_data["evidence"] if e["id"] == doc["evidence_id"])["artifact_sha256"] = (
        doc["artifact"]["sha256"]
    )
    response = client.post("/api/v1/consistency/evaluate", json=bundle_data)
    assert response.status_code == status
    if status == 422:
        assert response.json()["detail"][0]["loc"] == [
            "body",
            "policy_documents",
            0,
            "artifact",
            "text",
        ]
        assert response.json()["detail"][0]["type"] == "string_too_long"


def test_http_api_rejects_fake_api_label(bundle_data):
    api = next(e for e in bundle_data["evidence"] if e["id"] == "ev-location-api")
    api.pop("api_call")
    api["excerpt"] = "location logging, not an invoke"
    assert client.post("/api/v1/consistency/evaluate", json=bundle_data).status_code == 422


def test_http_api_distinguishes_failed_extraction_from_complete_snapshot(bundle_data):
    bundle_data["policy_claims"] = []
    bundle_data["policy_documents"][0]["extraction_status"] = "FAILED"
    response = client.post("/api/v1/consistency/evaluate", json=bundle_data)
    assert response.status_code == 200
    issue = response.json()["issues"][0]
    assert issue["status"] == "INSUFFICIENT_EVIDENCE"
    assert issue["requires_review"] is True
    assert issue["scope"] == "DATA_TYPE_DISCLOSURE"
