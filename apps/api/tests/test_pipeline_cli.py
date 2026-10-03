"""Pipeline subprocess boundary: malformed captures fail before any APK parser."""

import json
import subprocess
import sys

import pytest


def pipeline(tmp_path, policy, apk=None, job_id="test-job", timeout="120", product_scope=None):
    if apk is None:
        apk = tmp_path / "sample.apk"
        apk.write_bytes(b"not parsed: intake is invalid")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.pipeline",
            "--apk",
            str(apk),
            "--policy",
            str(policy),
            "--name",
            "Test",
            "--job-id",
            job_id,
            "--timeout",
            timeout,
            "--store-dir",
            str(tmp_path / "jobs"),
            *(["--product-scope", product_scope] if product_scope is not None else []),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return process, json.loads(process.stdout)


@pytest.fixture
def capture(tmp_path):
    raw = tmp_path / "policy.txt"
    raw.write_text("我们不访问联系人。", encoding="utf-8")
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        '[{"data_type":"CONTACTS","excerpt":"我们不访问联系人。"}]', encoding="utf-8"
    )
    out = tmp_path / "capture"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.policy_intake",
            "--raw",
            str(raw),
            "--source-url",
            "https://example.org/privacy",
            "--version",
            "1",
            "--candidates",
            str(candidates),
            "--output-dir",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert process.returncode == 0, process.stdout + process.stderr
    return out / "policy.capture.json"


@pytest.mark.parametrize(
    "tamper",
    ["raw", "processed", "audits", "escape", "span", "audit_ref", "review", "chunk", "bad_hash"],
)
def test_capture_corruption_rejected_before_scan(tmp_path, capture, tamper):
    record = json.loads(capture.read_bytes())
    root = capture.parent
    if tamper in {"raw", "processed", "audits"}:
        (root / record["files"][tamper]["path"]).write_bytes(b"corrupt")
    elif tamper == "escape":
        record["files"]["raw"]["path"] = "../policy.txt"
    elif tamper == "span":
        record["evidence"][1]["end_offset"] -= 1
    elif tamper == "audit_ref":
        import hashlib

        audit_path = root / "policy.audits.json"
        audits = json.loads(audit_path.read_bytes())
        audits[0]["evidence_ids"] = ["unknown"]
        data = json.dumps(audits).encode()
        audit_path.write_bytes(data)
        record["files"]["audits"]["sha256"] = hashlib.sha256(data).hexdigest()
    elif tamper == "review":
        record["document"]["review_status"] = "REVIEWED"
    elif tamper == "chunk":
        record["chunks"][0]["start"] = 1
    elif tamper == "bad_hash":
        record["document"]["artifact"]["sha256"] = "0" * 64
    capture.write_text(json.dumps(record), encoding="utf-8")
    process, body = pipeline(tmp_path, capture)
    assert process.returncode == 1
    assert body["status"] == "FAILED"
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"
    assert "我们不访问" not in process.stdout
    stored = json.loads((tmp_path / "jobs/test-job.json").read_bytes())
    assert stored["job"]["state"] == "FAILED"
    assert stored["bundle"] is None


def test_missing_apk_and_invalid_timeout(tmp_path):
    process, body = pipeline(tmp_path, tmp_path / "absent.json", apk=tmp_path / "absent.apk")
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "INPUT_NOT_FOUND"
    process, body = pipeline(tmp_path, tmp_path / "absent.json", job_id="timeout", timeout="181")
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "INVALID_ARGUMENT"


def test_duplicate_job_does_not_overwrite(tmp_path):
    policy = tmp_path / "absent.json"
    pipeline(tmp_path, policy)
    before = (tmp_path / "jobs/test-job.json").read_bytes()
    process, body = pipeline(tmp_path, policy)
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "PIPELINE_INPUT_INVALID"
    assert (tmp_path / "jobs/test-job.json").read_bytes() == before


@pytest.mark.parametrize(
    "malformed",
    [
        "missing_snapshot",
        "null_source",
        "wrong_record_type",
        "null_document",
        "non_object_evidence",
    ],
)
def test_malformed_capture_always_structured_failure(tmp_path, capture, malformed):
    record = json.loads(capture.read_bytes())
    if malformed == "missing_snapshot":
        record["evidence"] = record["evidence"][1:]
    elif malformed == "null_source":
        record["evidence"][0]["source"] = None
    elif malformed == "wrong_record_type":
        record = 42
    elif malformed == "null_document":
        record["document"] = None
    elif malformed == "non_object_evidence":
        record["evidence"] = [None]
    capture.write_text(json.dumps(record), encoding="utf-8")
    process, body = pipeline(tmp_path, capture)
    assert process.returncode == 1
    assert "Traceback" not in process.stderr
    assert body["status"] == "FAILED"
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"
    stored = json.loads((tmp_path / "jobs/test-job.json").read_bytes())
    assert stored["job"]["state"] == "FAILED"


@pytest.mark.parametrize("product_scope", [None, "GKD"])
def test_job_scope_comes_only_from_cli_input(tmp_path, capture, product_scope):
    record = json.loads(capture.read_bytes())
    record["document"]["applicability"]["product_scope"] = "Policy-only assertion"
    record["document"]["artifact"]["sha256"] = "0" * 64
    capture.write_text(json.dumps(record), encoding="utf-8")
    process, body = pipeline(tmp_path, capture, product_scope=product_scope)
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"
    stored = json.loads((tmp_path / "jobs/test-job.json").read_bytes())
    assert stored["job"]["product_scope"] == product_scope
    assert stored["job"]["region"] is None


@pytest.mark.skipif(
    __import__("os").environ.get("PRIVACYTRACE_DOCKER_TESTS") != "1",
    reason="Opt-in real isolated Docker pipeline acceptance",
)
def test_docker_pipeline_http_cancel_then_new_job_recovers(tmp_path, capture):
    """Cancel at observed STATIC_ANALYSIS, then recover through a fresh CLI job.

    This tests the lifecycle boundary, not a promised in-container interruption
    latency: cancellation may be noticed before container creation or by the next
    transition. The self-built binary-format APK is never installed or executed.
    """
    import time

    from apk_fixture_builder import apk
    from fastapi.testclient import TestClient

    from privacytrace.main import create_app
    from privacytrace.resources import ROOT

    fixture_apk = apk(tmp_path / "controlled-binary.apk")
    client = TestClient(create_app(store_root=tmp_path / "jobs"))
    command = [
        sys.executable,
        "-m",
        "privacytrace.pipeline",
        "--apk",
        str(fixture_apk),
        "--policy",
        str(capture),
        "--name",
        "Self-built cancellation fixture",
        "--job-id",
        "cancel-in-static",
        "--timeout",
        "120",
        "--store-dir",
        str(tmp_path / "jobs"),
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8"
    )
    try:
        deadline = time.monotonic() + 15
        observed_static = False
        while time.monotonic() < deadline:
            response = client.get("/api/v1/jobs/cancel-in-static")
            if response.status_code == 200:
                state = response.json()["state"]
                if state == "STATIC_ANALYSIS":
                    observed_static = True
                    break
                assert state not in {"FAILED", "SUCCEEDED", "CANCELLED"}, response.json()
            else:
                assert response.status_code == 404
            time.sleep(0.02)
        assert observed_static, "Did not observe STATIC_ANALYSIS within 15 seconds"
        cancelled = client.post(
            "/api/v1/jobs/cancel-in-static/cancel", headers={"X-PrivacyTrace-Local": "1"}
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["state"] == "CANCELLED"
        stdout, stderr = process.communicate(timeout=180)
        assert process.returncode == 1, stdout + stderr
        outcome = json.loads(stdout)
        assert outcome["status"] == "CANCELLED"
        assert client.get("/api/v1/jobs/cancel-in-static").json()["state"] == "CANCELLED"
        assert client.get("/api/v1/jobs/cancel-in-static/report").status_code == 409
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=20)

    recovered_process, recovered = pipeline(
        tmp_path, capture, apk=fixture_apk, job_id="after-cancel"
    )
    assert recovered_process.returncode == 0, recovered_process.stdout + recovered_process.stderr
    assert recovered["status"] == "SUCCEEDED"
    report = client.get("/api/v1/jobs/after-cancel/report")
    assert report.status_code == 200
    assert report.json()["job"]["state"] == "SUCCEEDED"
    receipt = json.loads((ROOT / report.json()["tools"]["isolation_receipt"]).read_bytes())
    assert receipt["cleanup_verified"] is True
