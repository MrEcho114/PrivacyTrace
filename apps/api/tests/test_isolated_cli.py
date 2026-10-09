"""Tests at the agreed public scanner CLI seam; no internal parser mocks."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from apk_fixture_builder import apk

ROOT = Path(__file__).resolve().parents[3]
DOCKER_ONLY = pytest.mark.skipif(
    os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam"
)


def public_scan(path, *args):
    process = subprocess.run(
        [sys.executable, "-m", "privacytrace.isolated_scan", str(path), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return process, json.loads(process.stdout)


def receipt(output):
    # The public CLI trace points to the authoritative, per-run isolation artifact.
    path = ROOT / output["tools"]["isolation_receipt"]
    proof = json.loads(path.read_text(encoding="utf-8"))
    assert proof["cleanup_verified"] is True
    assert proof["input_removed"] is True
    assert not (path.parent / "input.apk").exists()
    return proof


def controlled_image(dockerfile, tag):
    docker = (
        ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "docker"] if os.name == "nt" else ["docker"]
    )
    inspected = subprocess.run(
        [*docker, "image", "inspect", "privacytrace-worker:s1", "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    base = inspected.stdout.strip()
    assert base.startswith("sha256:")
    # BuildKit FROM accepts a local tag, not a bare image-config digest. Freeze an
    # exclusively owned test tag to the inspected production image before building.
    base_tag = "privacytrace-worker:controlled-base-" + base.split(":")[1][:12]
    subprocess.run(
        [*docker, "image", "tag", base, base_tag],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    context = str(ROOT)
    if os.name == "nt":
        context = subprocess.run(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-u", context],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    built = subprocess.run(
        [
            *docker,
            "build",
            "--pull=false",
            "--build-arg",
            "BASE_IMAGE=" + base_tag,
            "-f",
            context + "/apps/api/tests/" + dockerfile,
            "-t",
            tag,
            context,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert built.returncode == 0, built.stderr
    assert (
        subprocess.run(
            [*docker, "image", "inspect", base_tag, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
        == base
    )
    return tag


@pytest.fixture(scope="module")
def controlled_timeout_image():
    return controlled_image(
        "controlled-worker.Dockerfile", "privacytrace-worker:controlled-timeout-s1"
    )


@pytest.fixture(scope="module")
def controlled_invalid_image():
    return controlled_image(
        "invalid-worker.Dockerfile", "privacytrace-worker:controlled-invalid-s1"
    )


def test_missing_file_is_structured_and_does_not_start_a_worker(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "privacytrace.isolated_scan", str(tmp_path / "missing.apk")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert json.loads(result.stdout)["errors"][0]["code"] == "INPUT_NOT_FOUND"


def test_invalid_time_budget_rejected_before_container_creation(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.isolated_scan",
            str(apk(tmp_path / "test.apk")),
            "--timeout",
            "0",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["errors"][0]["code"] == "INVALID_TIMEOUT"


@pytest.mark.skipif(os.getenv("PRIVACYTRACE_DOCKER_TESTS") != "1", reason="Opt-in Docker seam")
def test_actual_container_is_nonroot_offline_readonly_and_has_hard_limits(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "privacytrace.isolated_scan",
            str(apk(tmp_path / "probe.apk")),
            "--probe",
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(result.stdout)
    probe = json.loads(output["tools"]["isolation_probe"])
    assert probe["uid"] == 65534
    assert probe["interfaces"] == ["lo"]
    assert probe["CapEff"] == "0000000000000000"
    assert probe["NoNewPrivs"] == "1"
    assert probe["input_write_denied_errno"] in {13, 30}
    assert probe["root_write_denied_errno"] in {13, 30}
    assert probe["memory.max"] == "1073741824"
    assert probe["cpu.max"] == "100000 100000"
    assert probe["pids.max"] == "32"


@DOCKER_ONLY
def test_corrupted_worker_object_is_structured_and_container_removed(
    tmp_path, controlled_invalid_image
):
    failed, output = public_scan(
        apk(tmp_path / "invalid-output.apk"), "--image", controlled_invalid_image
    )
    assert failed.returncode == 1
    assert output["errors"][0]["code"] == "WORKER_INVALID_OUTPUT"
    receipt(output)


@DOCKER_ONLY
def test_environment_cannot_redirect_the_local_isolation_daemon(tmp_path, monkeypatch):
    # Fault-inject user environment, not the runner implementation or parser.
    monkeypatch.setenv("DOCKER_HOST", "tcp://127.0.0.1:1")
    monkeypatch.setenv("DOCKER_CONTEXT", "privacytrace-nonexistent-test-context")
    monkeypatch.setenv("DOCKER_TLS_VERIFY", "1")
    monkeypatch.setenv("DOCKER_CERT_PATH", str(tmp_path / "missing-certs"))
    recovered, report = public_scan(apk(tmp_path / "environment.apk"), "--probe")
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    receipt(report)


@DOCKER_ONLY
@pytest.mark.parametrize("malformed", ["broken_zip", "path_traversal"])
def test_actual_production_worker_rejects_bad_input_then_recovers(tmp_path, malformed):
    bad = tmp_path / "bad.apk"
    if malformed == "broken_zip":
        bad.write_bytes(b"not an APK ZIP")
        expected = "ZIP_INVALID"
    else:
        apk(bad, entries={"../escape": b"x"})
        expected = "UNSAFE_ZIP"
    failed, error = public_scan(bad)
    assert failed.returncode == 1
    assert error["errors"][0]["code"] == expected
    receipt(error)
    recovered, report = public_scan(apk(tmp_path / "recovered.apk"))
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert report["package_name"] == "org.privacytrace.fixture"
    assert any(e["kind"] == "API" for e in report["evidence"])
    receipt(report)


@DOCKER_ONLY
def test_actual_timed_out_worker_is_removed_and_next_probe_succeeds(
    tmp_path, controlled_timeout_image
):
    sample = apk(tmp_path / "timeout.apk")
    timed_out, error = public_scan(sample, "--image", controlled_timeout_image, "--timeout", "1")
    assert timed_out.returncode == 1
    assert error["errors"][0]["code"] == "TIMEOUT"
    proof = receipt(error)
    assert proof["timeout_seconds"] == 1
    recovered, report = public_scan(sample, "--probe")
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert json.loads(report["tools"]["isolation_probe"])["uid"] == 65534
    receipt(report)


@DOCKER_ONLY
def test_actual_cancelled_worker_removes_container_and_input_copy(
    tmp_path, controlled_timeout_image
):
    sample = apk(tmp_path / "cancel.apk")
    cancel = tmp_path / "cancel-request"
    root = tmp_path / "cancel-runs"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "privacytrace.isolated_scan",
            str(sample),
            "--image",
            controlled_timeout_image,
            "--timeout",
            "15",
            "--run-root",
            str(root),
            "--cancel-file",
            str(cancel),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            proofs = list(root.glob("*/isolation.json"))
            if proofs and json.loads(proofs[0].read_text(encoding="utf-8")).get(
                "container_created"
            ):
                break
            assert process.poll() is None
            time.sleep(0.1)
        else:
            pytest.fail("Worker did not reach inspected state")
        cancel.touch()
        out, err = process.communicate(timeout=30)
        record = json.loads(out)
        assert process.returncode == 1, err.decode("utf-8", errors="replace")
        assert record["errors"][0]["code"] == "CANCELLED"
        proof = receipt(record)
        assert proof["apk_sha256"]
        assert sample.exists()
    finally:
        if process.poll() is None:
            cancel.touch()
            process.communicate(timeout=30)


@DOCKER_ONLY
def test_active_quota_reservation_blocks_other_run_without_disturbing_it(
    tmp_path, controlled_timeout_image
):
    sample = apk(tmp_path / "reserved.apk")
    cancel = tmp_path / "cancel-reserved"
    root = tmp_path / "shared-run-root"
    quota = str(sample.stat().st_size + 256 * 1024 + 64 * 1024)
    common = ["--run-root", str(root), "--quota-bytes", quota]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "privacytrace.isolated_scan",
            str(sample),
            "--image",
            controlled_timeout_image,
            "--timeout",
            "15",
            "--cancel-file",
            str(cancel),
            *common,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            proofs = list(root.glob("*/isolation.json"))
            if proofs:
                break
            assert process.poll() is None
            time.sleep(0.1)
        else:
            pytest.fail("Worker did not reserve storage")
        before = proofs[0].read_bytes()
        failed, record = public_scan(sample, "--probe", *common)
        assert failed.returncode == 1
        assert record["errors"][0]["code"] == "STORAGE_QUOTA_EXCEEDED"
        assert process.poll() is None
        assert proofs[0].read_bytes() == before
        assert len(list(root.glob("*/input.apk"))) == 1
        cancel.touch()
        out, _ = process.communicate(timeout=30)
        receipt(json.loads(out))
        recovered, record = public_scan(sample, "--probe", *common)
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr
        receipt(record)
    finally:
        if process.poll() is None:
            cancel.touch()
            process.communicate(timeout=30)
