"""Regression for #278: a failed final cleanup must not orphan a managed operation.

A terminal `shutil.rmtree(operation)` failure leaves the DONE ledger row as the
only proof that the residue directory is ours. Retention and restart recovery
must both honour that proof: prune may not forget the row while the directory
still exists, and recovery must be able to reap it instead of refusing to start.
"""

import hashlib
import json
import os
import shutil
from uuid import uuid4

import pytest

from privacytrace import runner_service
from privacytrace.runner_service import Runner, RunnerConfig, RuntimeUnavailable

PAYLOAD = b"controlled-runner-input"
IMAGE = "sha256:" + "a" * 64


class Source:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False

    def read1(self, size):
        chunk, self.payload = self.payload, b""
        return chunk


class Gateway:
    """Permit checks pass and one registered material is served."""

    def open(self, path, **kwargs):
        return Source(PAYLOAD)

    def json(self, path, **kwargs):
        return {"version": 1, "permitted": True}


@pytest.fixture
def runner_token():
    token = {
        "instance": str(uuid4()),
        "request": str(uuid4()),
        "owner": str(uuid4()),
        "root": None,
        "cleanup": {"failing": True, "removals": []},
    }
    yield token


def _request(token):
    return {
        "version": 1,
        "operation": "scan",
        "request_id": token["request"],
        "instance_id": token["instance"],
        "scope_id": "scope-278",
        "owner": token["owner"],
        "fence": 1,
        "package_set": False,
        "files": [
            {
                "name": "sample.apk",
                "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                "size": len(PAYLOAD),
                "ticket": "controlled-ticket",
            }
        ],
    }


def _fake_command(args):
    if "ps" in args:
        return ""
    assert "image" in args and "inspect" in args
    return IMAGE


def _fake_scan(path, *, image, timeout, metadata, cancelled, run_root, quota_bytes):
    workspace = run_root / ("c" * 32)
    workspace.mkdir(parents=True)
    receipt = workspace / "isolation_receipt.json"
    receipt.write_text(
        json.dumps({"image_id": image, "input_removed": True, "cleanup_verified": True})
    )
    return {"tools": {"isolation_receipt": str(receipt)}}


def _install(tmp_path, monkeypatch, token):
    token["root"] = tmp_path / "private-runner"
    real_rmtree = shutil.rmtree
    cleanup = token["cleanup"]

    def flaky_rmtree(path, *args, **kwargs):
        cleanup["removals"].append(os.path.basename(str(path)))
        if cleanup["failing"] and os.path.basename(str(path)) == token["request"]:
            raise PermissionError(13, "Permission denied", str(path))
        return real_rmtree(path, *args, **kwargs)

    claims = {
        "instance_id": token["instance"],
        "scope_id": "scope-278",
        "owner": token["owner"],
        "fence": 1,
        "mode": "scan",
    }
    monkeypatch.setattr(shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr(runner_service, "docker_prefix", lambda: ["docker"])
    monkeypatch.setattr(runner_service, "command", _fake_command)
    monkeypatch.setattr(runner_service, "ticket_claims", lambda value: dict(claims))
    monkeypatch.setattr(runner_service, "scan_isolated", _fake_scan)


def _rows(runner, request_id):
    with runner._database() as conn:
        return conn.execute("SELECT state FROM operations WHERE id=?", (request_id,)).fetchall()


@pytest.mark.skipif(os.name != "posix", reason="Dedicated Runner is Linux-only")
def test_done_cleanup_failure_keeps_ownership_until_prune_removes_directory(
    tmp_path, monkeypatch, runner_token
):
    token = runner_token
    _install(tmp_path, monkeypatch, token)
    runner = Runner(RunnerConfig(token["instance"], IMAGE, token["root"]), Gateway())
    operation = runner.operations / token["request"]
    try:
        with pytest.raises(RuntimeUnavailable):
            runner.run(_request(token))
        # The scan succeeded, so the DONE row survives as ownership proof but
        # the runner refuses reuse until the residue is provably gone.
        assert _rows(runner, token["request"]) == [("DONE",)]
        assert runner.faulted is True
        assert operation.is_dir()

        with runner._database() as conn:
            conn.execute("UPDATE operations SET expires=0")
        runner.prune()
        assert _rows(runner, token["request"]) == [("DONE",)]
        assert operation.is_dir()

        token["cleanup"]["failing"] = False
        runner.prune()
        assert not operation.exists()
        assert _rows(runner, token["request"]) == []
    finally:
        runner.close()


@pytest.mark.skipif(os.name != "posix", reason="Dedicated Runner is Linux-only")
def test_restart_reaps_owned_done_residue_and_accepts_new_work(tmp_path, monkeypatch, runner_token):
    token = runner_token
    _install(tmp_path, monkeypatch, token)
    runner = Runner(RunnerConfig(token["instance"], IMAGE, token["root"]), Gateway())
    operation = runner.operations / token["request"]
    with pytest.raises(RuntimeUnavailable):
        runner.run(_request(token))
    runner.close()

    token["cleanup"]["failing"] = False
    recovered = Runner(RunnerConfig(token["instance"], IMAGE, token["root"]), Gateway())
    try:
        assert not operation.exists()
        assert recovered.faulted is False
        second = dict(_request(token), request_id=str(uuid4()))
        assert recovered.run(second)["request_id"] == second["request_id"]
        assert not list(recovered.operations.iterdir())
    finally:
        recovered.close()


@pytest.mark.skipif(os.name != "posix", reason="Dedicated Runner is Linux-only")
def test_prune_never_deletes_unqueued_unregistered_directories(tmp_path, monkeypatch, runner_token):
    token = runner_token
    _install(tmp_path, monkeypatch, token)
    runner = Runner(RunnerConfig(token["instance"], IMAGE, token["root"]), Gateway())
    try:
        foreign = runner.operations / str(uuid4())
        foreign.mkdir()
        (foreign / "unregistered.txt").write_text("operator-owned")
        runner.prune()
        assert foreign.is_dir()
        runner.faulted = False
        with pytest.raises(ValueError):
            runner._recover()
        assert foreign.is_dir()
    finally:
        runner.close()
