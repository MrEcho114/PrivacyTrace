"""Fault-injection checks for Runner restart; Docker is simulated in these cases.

The real Docker orphan/revocation tests remain in test_runner_service.py.
Only the Runner's owned ledger and exact image/label/mount proof permit removal.
"""

import json
import os
import sqlite3
import time
from uuid import uuid4

import pytest

from privacytrace import runner_service
from privacytrace.runner_service import Runner, RunnerConfig


@pytest.mark.skipif(os.name != "posix", reason="Dedicated Runner is Linux-only")
@pytest.mark.parametrize(
    "failure",
    ["wrong_label", "wrong_image", "wrong_mount", "remove_error", "untracked"],
)
def test_restart_fails_closed_preserves_residue_then_recovers_only_owned_artifacts(
    tmp_path, monkeypatch, failure
):
    instance = str(uuid4())
    image = "sha256:" + "a" * 64
    root = tmp_path / "private-runner"
    operation_id = str(uuid4())
    workspace_id = "b" * 32
    workspace = root / "operations" / operation_id / "scans" / workspace_id
    workspace.mkdir(parents=True)
    root.chmod(0o700)
    (workspace / "input.apk").write_bytes(b"fault-injection-only")
    database = root / "requests.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute(
            "CREATE TABLE operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
            "state TEXT NOT NULL, result BLOB, expires INTEGER NOT NULL)"
        )
        if failure != "untracked":
            conn.execute(
                "INSERT INTO operations VALUES (?, ?, 'RUNNING', NULL, ?)",
                (operation_id, "ledger-digest", int(time.time()) + 360),
            )

    mode = {"value": failure}
    removals = []

    def fake_command(args):
        # No Docker daemon calls in this fault-injection unit test.
        if "image" in args and "inspect" in args:
            return image
        if "ps" in args:
            return "owned-container\n"
        if "inspect" in args:
            return json.dumps(
                [{
                    "Image": ("sha256:" + "c" * 64) if mode["value"] == "wrong_image" else image,
                    "Config": {
                        "Labels": {
                            "privacytrace.run": (
                                "unrelated-workspace"
                                if mode["value"] == "wrong_label"
                                else workspace_id
                            )
                        }
                    },
                    "Mounts": [{
                        "Type": "bind",
                        "Destination": "/input/sample.apk",
                        "RW": False,
                        "Source": str(
                            (root / "foreign" / "input.apk")
                            if mode["value"] == "wrong_mount"
                            else workspace / "input.apk"
                        ),
                    }],
                }]
            )
        if "rm" in args:
            if mode["value"] == "remove_error":
                raise OSError("simulated Docker remove failure: sensitive path")
            removals.append(tuple(args))
            return ""
        raise AssertionError("Unexpected Docker command")

    monkeypatch.setattr(runner_service, "docker_prefix", lambda: ["docker"])
    monkeypatch.setattr(runner_service, "command", fake_command)
    config = RunnerConfig(instance, image, root)
    with pytest.raises((ValueError, OSError)):
        Runner(config, gateway=None)
    assert workspace.exists()
    assert removals == []
    with sqlite3.connect(database) as conn:
        state = conn.execute(
            "SELECT state FROM operations WHERE id=?", (operation_id,)
        ).fetchone()
    assert (state is None and failure == "untracked") or state == ("RUNNING",)

    # Operator correction / confirmed cleanup followed by a new start.
    # Recovery must not force-prune an unknown workspace or skip ownership proof.
    if failure == "untracked":
        with sqlite3.connect(database) as conn:
            conn.execute(
                "INSERT INTO operations VALUES (?, ?, 'RUNNING', NULL, ?)",
                (operation_id, "ledger-digest", int(time.time()) + 360),
            )
    mode["value"] = "valid"
    recovered = Runner(config, gateway=None)
    try:
        assert not workspace.exists()
        assert not any(recovered.operations.iterdir())
        assert len(removals) == 1
        assert recovered.faulted is False
        with recovered._database() as conn:
            state = conn.execute(
                "SELECT state FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            assert state == ("ABORTED",)
    finally:
        recovered.close()
