from fastapi.testclient import TestClient

from privacytrace.main import app
from privacytrace.resources import read_json

client = TestClient(app)


def test_health_and_taxonomy():
    assert client.get("/api/v1/health").json()["mode"] == "scaffold"
    assert client.get("/api/v1/taxonomy").json()["version"] == "0.1.0"


def test_demo_report_and_evidence():
    response = client.get("/api/v1/demo/report")
    assert response.status_code == 200
    report = response.json()
    assert report["demo"] is True
    assert report["job"]["input_mode"] == "SYNTHETIC"
    for issue in report["result"]["issues"]:
        for ref in issue["evidence_ids"]:
            assert client.get(f"/api/v1/demo/evidence/{ref}").status_code == 200
    assert client.get("/api/v1/demo/evidence/missing").status_code == 404


def test_evaluate_and_reject_unknown_references():
    data = read_json("samples/demo/evaluation-input.json")
    assert client.post("/api/v1/consistency/evaluate", json=data).status_code == 200
    data["behaviors"][0]["evidence_ids"] = ["invented"]
    assert client.post("/api/v1/consistency/evaluate", json=data).status_code == 422
