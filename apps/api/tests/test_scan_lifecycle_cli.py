"""Public CLI lifecycle; faults injected only at OS/Docker boundaries."""

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from apk_fixture_builder import apk

from privacytrace import isolated_scan


def test_unavailable_docker_does_not_retain_copied_apk(tmp_path, monkeypatch, capsys):
    root = tmp_path / "apk-runs"
    before = set(root.glob("*/input.apk"))
    sample = apk(tmp_path / "controlled.apk")
    monkeypatch.setattr(sys, "argv", ["scan", str(sample)])
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, b"", b"runtime unavailable"),
    )
    assert isolated_scan.main() == 1
    record = json.loads(capsys.readouterr().out)
    assert not (set(root.glob("*/input.apk")) - before)
    proof = json.loads(Path(record["tools"]["isolation_receipt"]).read_text(encoding="utf-8"))
    assert proof["input_removed"] is True
    assert proof["primary_error"]["code"] == "CONTAINER_ERROR"


def invoke(sample, monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["scan", str(sample), *args])
    code = isolated_scan.main()
    return code, json.loads(capsys.readouterr().out)


class DockerBoundary:
    """A controlled OS process boundary, not an implementation/parser mock."""

    def __init__(self, sample, fault=None, cleanup_fault=None):
        self.sample, self.fault, self.cleanup_fault = sample, fault, cleanup_fault
        self.created = False
        self.removed = False
        self.started = False

    def run(self, args, **kwargs):
        def result(code=0, out=b"", err=b""):
            return subprocess.CompletedProcess(args, code, out, err)

        if "wslpath" in args:
            if self.fault == "path":
                return result(1, err=b"private diagnostic must not be echoed")
            return result(out=args[-1].encode())
        if "image" in args:
            if self.fault == "image":
                return result(1, err=b"private diagnostic must not be echoed")
            return result(out=b"sha256:" + b"a" * 64)
        if "create" in args:
            self.created = True
            self.name = args[args.index("--name") + 1]
            self.label = args[args.index("--label") + 1].split("=", 1)[1]
            self.mount = (
                args[args.index("--mount") + 1].split("source=", 1)[1].split(",target=", 1)[0]
            )
            if self.fault in {"create", "foreign"}:
                if self.fault == "foreign":
                    self.label = "other-owned-run"
                return result(1, err=b"transport failed after create")
            return result(out=self.name.encode())
        if "rm" in args:
            assert args[-1] == self.name
            if self.cleanup_fault == "rm":
                return result(1, err=b"private rm diagnostic")
            self.removed = True
            return result()
        if "inspect" in args:
            if self.removed:
                if self.cleanup_fault == "inspect":
                    raise OSError("private inspect diagnostic")
                return result(1, err=("No such object: " + self.name).encode())
            host = dict(
                NetworkMode="none",
                ReadonlyRootfs=True,
                Memory=1073741824,
                MemorySwap=1073741824,
                NanoCpus=1000000000,
                PidsLimit=32,
                LogConfig={"Type": "none"},
                CapDrop=["ALL"],
                SecurityOpt=["no-new-privileges:true"],
                Privileged=False,
                CapAdd=None,
                Devices=[],
                DeviceRequests=None,
                DeviceCgroupRules=None,
                VolumesFrom=None,
                PidMode="",
                IpcMode="private",
                CgroupnsMode="private",
                ShmSize=8388608,
                Tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=16m,nr_inodes=4096"},
            )
            record = {
                "Config": {"User": "65534:65534", "Labels": {"privacytrace.run": self.label}},
                "HostConfig": host,
                "Mounts": [
                    {
                        "Destination": "/input/sample.apk",
                        "RW": False,
                        "Source": self.mount,
                        "Propagation": "rprivate",
                    }
                ],
            }
            return result(out=json.dumps([record]).encode())
        raise AssertionError(args)

    def popen(self, args, **kwargs):
        self.started = True
        boundary = self

        class Process:
            returncode = None if boundary.fault in {"timeout", "cancel"} else 0
            stdout = io.BytesIO(
                b"not-json"
                if boundary.fault == "json"
                else json.dumps(
                    {
                        "apk_sha256": hashlib.sha256(boundary.sample.read_bytes()).hexdigest(),
                        "tools": {},
                        "errors": [],
                    }
                ).encode()
            )
            stderr = io.BytesIO(b"private worker diagnostic")

            def poll(self):
                return self.returncode

            def kill(self):
                self.returncode = -9

            def wait(self, **kw):
                return self.returncode

        if self.fault == "cancel":
            (self.sample.parent / "cancel").touch()
        return Process()


@pytest.mark.parametrize(
    "fault,expected",
    [
        (None, None),
        ("image", "CONTAINER_ERROR"),
        ("create", "CONTAINER_ERROR"),
        ("json", "WORKER_INVALID_OUTPUT"),
        ("timeout", "TIMEOUT"),
        ("cancel", "CANCELLED"),
    ],
)
def test_run_exit_always_removes_owned_copy_and_keeps_receipt(
    tmp_path, monkeypatch, capsys, fault, expected
):
    sample = apk(tmp_path / "sample.apk")
    boundary = DockerBoundary(sample, fault)
    monkeypatch.setattr(subprocess, "run", boundary.run)
    monkeypatch.setattr(subprocess, "Popen", boundary.popen)
    code, record = invoke(
        sample, monkeypatch, capsys, "--timeout", "1", "--cancel-file", str(tmp_path / "cancel")
    )
    assert code == (1 if expected else 0)
    if expected:
        assert record["errors"][0]["code"] == expected
    proof = json.loads(Path(record["tools"]["isolation_receipt"]).read_text(encoding="utf-8"))
    assert proof["apk_sha256"] == hashlib.sha256(sample.read_bytes()).hexdigest()
    assert proof["input_removed"] is True
    assert proof["cleanup_verified"] is True
    assert not list((tmp_path / "apk-runs").glob("*/input.apk"))
    assert sample.exists()  # Never delete the caller's original.
    assert "private" not in json.dumps(record)
    assert not list((tmp_path / "apk-runs").glob("*/stdout.json"))


@pytest.mark.parametrize(
    "fault,cleanup,primary",
    [
        ("timeout", "rm", "TIMEOUT"),
        ("cancel", "rm", "CANCELLED"),
        ("json", "inspect", "WORKER_INVALID_OUTPUT"),
    ],
)
def test_primary_error_survives_cleanup_failure(
    tmp_path, monkeypatch, capsys, fault, cleanup, primary
):
    sample = apk(tmp_path / "sample.apk")
    boundary = DockerBoundary(sample, fault, cleanup)
    monkeypatch.setattr(subprocess, "run", boundary.run)
    monkeypatch.setattr(subprocess, "Popen", boundary.popen)
    code, record = invoke(
        sample, monkeypatch, capsys, "--timeout", "1", "--cancel-file", str(tmp_path / "cancel")
    )
    assert code == 1
    assert record["errors"][0]["code"] == primary
    assert record["primary_error"]["code"] == primary
    assert record["cleanup_errors"]
    proof = json.loads(Path(record["tools"]["isolation_receipt"]).read_text(encoding="utf-8"))
    assert proof["primary_error"]["code"] == primary
    assert proof["cleanup_errors"] == record["cleanup_errors"]
    assert proof["cleanup_verified"] is False
    assert proof["input_removed"] is True


def test_cumulative_quota_rejects_before_copy_without_deleting_prior_receipts(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "apk-runs"
    old = root / "old/isolation.json"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"historical audit")
    sample = apk(tmp_path / "sample.apk")
    code, record = invoke(sample, monkeypatch, capsys, "--quota-bytes", "1")
    assert code == 1
    assert record["errors"][0]["code"] == "STORAGE_QUOTA_EXCEEDED"
    assert old.read_bytes() == b"historical audit"
    assert not list(root.glob("*/input.apk"))
    assert sorted(p.name for p in root.iterdir()) == [".quota.lock", "old"]


def test_partial_copy_error_is_structured_and_partial_file_removed(tmp_path, monkeypatch, capsys):
    sample = apk(tmp_path / "sample.apk")
    original_open = Path.open

    class BrokenWrite:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            self.file.__enter__()
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def write(self, data):
            self.file.write(data[:64])
            raise OSError("private disk failure")

    def open_file(path, mode="r", *args, **kwargs):
        file = original_open(path, mode, *args, **kwargs)
        return BrokenWrite(file) if path.name == "input.apk" and mode == "xb" else file

    monkeypatch.setattr(Path, "open", open_file)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 1
    assert record["errors"][0]["code"] == "COPY_FAILED"
    proof = json.loads(Path(record["tools"]["isolation_receipt"]).read_text(encoding="utf-8"))
    assert proof["input_removed"] is True
    assert not list((tmp_path / "apk-runs").glob("*/input.apk"))


def test_oversized_input_rejected_without_run_copy(tmp_path, monkeypatch, capsys):
    sample = tmp_path / "large.apk"
    with sample.open("wb") as file:
        file.truncate(150 * 1024 * 1024 + 1)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 1
    assert record["errors"][0]["code"] == "INPUT_TOO_LARGE"
    assert not (tmp_path / "apk-runs").exists()


def test_success_with_cleanup_failure_is_not_reported_as_success(tmp_path, monkeypatch, capsys):
    sample = apk(tmp_path / "sample.apk")
    boundary = DockerBoundary(sample, cleanup_fault="rm")
    monkeypatch.setattr(subprocess, "run", boundary.run)
    monkeypatch.setattr(subprocess, "Popen", boundary.popen)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 1
    assert record["primary_error"] is None
    assert len(record["errors"]) == 1
    assert record["cleanup_errors"][0]["code"] == "CONTAINER_ERROR"


@pytest.mark.skipif(sys.platform != "win32", reason="WSL path preflight applies on Windows")
def test_wsl_path_failure_also_removes_copy(tmp_path, monkeypatch, capsys):
    sample = apk(tmp_path / "sample.apk")
    boundary = DockerBoundary(sample, "path")
    monkeypatch.setattr(subprocess, "run", boundary.run)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 1
    assert record["errors"][0]["code"] == "CONTAINER_ERROR"
    proof = json.loads(Path(record["tools"]["isolation_receipt"]).read_text(encoding="utf-8"))
    assert proof["input_removed"] is True
    assert boundary.created is False


def test_failed_reservation_write_does_not_poison_next_run(tmp_path, monkeypatch, capsys):
    sample = apk(tmp_path / "sample.apk")
    original_open = Path.open

    class WriteFailure:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            self.file.__enter__()
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def write(self, data):
            self.file.write(data[:3])
            raise OSError("partial reservation")

    def open_file(path, mode="r", *args, **kwargs):
        file = original_open(path, mode, *args, **kwargs)
        return WriteFailure(file) if "reservation" in path.name and mode in {"w", "xb"} else file

    monkeypatch.setattr(Path, "open", open_file)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 1
    assert record["errors"][0]["code"] == "STORAGE_PREPARATION_FAILED"
    monkeypatch.setattr(Path, "open", original_open)
    boundary = DockerBoundary(sample)
    monkeypatch.setattr(subprocess, "run", boundary.run)
    monkeypatch.setattr(subprocess, "Popen", boundary.popen)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 0


def test_release_failure_is_distinct_and_preserved_in_receipt(tmp_path, monkeypatch, capsys):
    sample = apk(tmp_path / "sample.apk")
    boundary = DockerBoundary(sample)
    monkeypatch.setattr(subprocess, "run", boundary.run)
    monkeypatch.setattr(subprocess, "Popen", boundary.popen)
    original_unlink = Path.unlink

    def unlink(path, *args, **kwargs):
        if path.name == "reservation.json":
            raise OSError("reservation release fault")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 1
    assert record["errors"][0]["code"] == "RESERVATION_RELEASE_FAILED"
    proof = json.loads(Path(record["tools"]["isolation_receipt"]).read_text(encoding="utf-8"))
    assert proof["cleanup_errors"] == record["cleanup_errors"]
    assert proof["input_removed"] is True
    assert proof["primary_error"] is None


def test_ambiguous_create_never_deletes_foreign_container(tmp_path, monkeypatch, capsys):
    sample = apk(tmp_path / "sample.apk")
    boundary = DockerBoundary(sample, "foreign")
    monkeypatch.setattr(subprocess, "run", boundary.run)
    code, record = invoke(sample, monkeypatch, capsys)
    assert code == 1
    assert record["primary_error"]["code"] == "CONTAINER_ERROR"
    assert record["cleanup_errors"][0]["code"] == "CLEANUP_UNVERIFIED"
    assert boundary.removed is False
    proof = json.loads(Path(record["tools"]["isolation_receipt"]).read_text(encoding="utf-8"))
    assert proof["input_removed"] is True
