from fastapi.testclient import TestClient

from privacytrace.main import create_app


def test_private_job_reads_reject_dns_rebinding_host(tmp_path):
    client = TestClient(create_app(tmp_path), base_url="http://attacker.example")
    assert client.get("/api/v1/jobs").status_code == 400
