"""Receipt serialization regressions; controlled results do not certify live cases."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from deploy.acceptance.issue132 import access_matrix, verify_native  # noqa: E402


@pytest.fixture(params=[False, True], ids=["platform-default", "windows-crlf"])
def receipt_environment(tmp_path, monkeypatch, request):
    if request.param:
        original_open = Path.open

        def windows_text_open(path, mode="r", *args, **kwargs):
            if "b" not in mode and any(flag in mode for flag in "wxa"):
                if kwargs.get("newline") is None:
                    kwargs["newline"] = "\r\n"
            return original_open(path, mode, *args, **kwargs)

        # Make the Windows failure reproducible on Linux CI as well. Binary
        # opens retain their real behavior; universal text reads still hide CRLF.
        monkeypatch.setattr(Path, "open", windows_text_open)
    return tmp_path


def assert_receipt(path, output):
    raw = path.read_bytes()
    assert output["receipt_sha256"] == hashlib.sha256(raw).hexdigest()
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n") and len(raw.splitlines()) > 1
    return json.loads(raw.decode("utf-8"))


def corrupt_receipt_readback(monkeypatch, target):
    original_read = Path.read_bytes

    def changed_read(path):
        raw = original_read(path)
        return raw.replace(b"\n", b"\r\n") if path == target else raw

    monkeypatch.setattr(Path, "read_bytes", changed_read)


@pytest.mark.parametrize("corrupt_readback", [False, True], ids=["intact", "changed-readback"])
def test_http_cli_digest_matches_actual_utf8_file_bytes(
    receipt_environment, monkeypatch, capsys, corrupt_readback,
):
    directory = receipt_environment
    config = directory / "config.json"
    output = directory / "receipt.json"
    config.write_text(json.dumps({
        "disposable": True, "origin": "https://localhost:29443", "instance_id": "test-instance",
        "target": {}, "owner_token_env": "PT132_OWNER", "other_token_env": "PT132_OTHER",
    }), encoding="utf-8")
    monkeypatch.setenv("PT132_OWNER", "controlled-owner-token")
    monkeypatch.setenv("PT132_OTHER", "controlled-other-token")
    monkeypatch.setattr(sys, "argv", [
        "access_matrix", "--config", str(config), "--output", str(output), "--pause", "0",
    ])

    class ControlledClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, path):
            assert path == "/api/v1/mobile-capabilities"
            return httpx.Response(200, json={"supported": True, "instance_id": "test-instance"})

    monkeypatch.setattr(access_matrix.httpx, "Client", ControlledClient)
    monkeypatch.setattr(access_matrix, "run_matrix", lambda *args, **kwargs: [
        {"status": "PASSED", "note": "Controlled serialization result"} for _ in range(95)
    ])
    if corrupt_readback:
        corrupt_receipt_readback(monkeypatch, output)
        with pytest.raises(OSError, match="receipt readback failed"):
            access_matrix.main()
        assert capsys.readouterr().out == ""
        return
    assert access_matrix.main() == 0
    printed = json.loads(capsys.readouterr().out)
    receipt = assert_receipt(output, printed)
    assert receipt["subset_status"] == "PASSED" and len(receipt["checks"]) == 95
    assert "controlled-owner-token" not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("corrupt_readback", [False, True], ids=["intact", "changed-readback"])
def test_native_cli_uses_the_same_fixed_byte_serialization(
    receipt_environment, monkeypatch, capsys, corrupt_readback,
):
    directory = receipt_environment
    dependencies = directory / "dependencies"
    dependencies.mkdir()
    for name in verify_native.JARS:
        (dependencies / name).write_bytes(b"controlled dependency placeholder")
    output = directory / "native"
    monkeypatch.setattr(sys, "argv", [
        "verify_native", "--dependency-cache", str(dependencies), "--output-dir", str(output),
    ])
    original_run = subprocess.run

    def controlled_jvm(command, **kwargs):
        if command[0] == "git":
            return original_run(command, **kwargs)
        return subprocess.CompletedProcess(command, 0, b"controlled JVM result\n", b"")

    monkeypatch.setattr(verify_native.subprocess, "run", controlled_jvm)
    if corrupt_readback:
        corrupt_receipt_readback(monkeypatch, output / "receipt.json")
        with pytest.raises(OSError, match="receipt readback failed"):
            verify_native.main()
        assert capsys.readouterr().out == ""
        return
    assert verify_native.main() == 0
    printed = json.loads(capsys.readouterr().out)
    receipt = assert_receipt(output / "receipt.json", printed)
    assert receipt["status"] == "PASSED" and receipt["android_acceptance"] is False
    assert receipt["compile"]["exit_code"] == receipt["junit"]["exit_code"] == 0
