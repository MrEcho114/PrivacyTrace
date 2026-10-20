"""Controlled Docker OOM/timeout and actual owned-orphan recovery.

The fault images run trusted sleep/allocation programs; they do not parse APKs.
Business recovery uses the normal fixed scanner again and must produce a report.
"""

import copy
import json
import sqlite3
import time

from .late_result_drill import _row
from .operations_drills import SERVICES
from .provision import execute
from .r2_business_loop import (
    Fixtures,
    cleanup_created_scopes,
    create_scope,
    poll_job,
    start_job,
    upload_apk,
)


def _results(lab, watermark):
    path = lab.root / "runner/requests.sqlite"
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        return [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT result FROM operations WHERE rowid>? AND state='DONE'", (watermark,)
            )
        ]


def _watermark(lab):
    with sqlite3.connect(f"file:{lab.root}/runner/requests.sqlite?mode=ro", uri=True) as conn:
        return conn.execute("SELECT coalesce(max(rowid),0) FROM operations").fetchone()[0]


def _owned_scanners(lab):
    identifiers = execute(
        ["docker", "ps", "-aq", "--filter", "label=privacytrace.run"]
    ).splitlines()
    if not identifiers:
        return []
    from pathlib import Path

    try:
        inspected = execute(["docker", "inspect", *identifiers])
    except RuntimeError as error:
        # Runner can remove an orphan between `ps` and `inspect`. Docker still
        # emits JSON for surviving IDs; only missing-object errors are benign.
        errors = getattr(error, "stderr", "").lower().splitlines()
        if not errors or any(not line.startswith("error: no such object:") for line in errors):
            raise
        inspected = error.stdout
    return [
        item["Id"]
        for item in json.loads(inspected)
        if any(Path(m["Source"]).is_relative_to(lab.root / "runner") for m in item["Mounts"])
    ]


def _boot(lab, config):
    (lab.root / "laboratory.json").write_text(json.dumps(config))
    lab.run("stop", "runner", *SERVICES)
    lab.run("up", "-d", "--no-deps", "--force-recreate", "runner", *SERVICES)
    lab.ready()


def scanner_override(original, image):
    """Add role overrides even when those roles exist only in the base Compose."""
    config = copy.deepcopy(original)
    for role in ("api", "worker", "runner"):
        config["services"].setdefault(role, {}).setdefault("environment", {})[
            "PRIVACYTRACE_RUNNER_IMAGE_ID"
        ] = image
    return config


def drill(lab, topology):
    assert not cleanup_created_scopes()
    fixture = Fixtures.build()
    path = lab.root / "laboratory.json"
    original = json.loads(path.read_text())
    tag = "privacytrace-fault-base:" + lab.project
    execute(["docker", "tag", lab.state["images"]["api"], tag])
    images = {}
    for fault, expression in {
        "timeout": "import time;time.sleep(360)",
        "oom": "bytearray(2*1024*1024*1024)",
    }.items():
        context = lab.root / ("fault-build-" + fault)
        context.mkdir(mode=0o700, exist_ok=True)
        (context / "Dockerfile").write_text(
            f"FROM {tag}\nUSER 65534:65534\nHEALTHCHECK NONE\nENTRYPOINT "
            + json.dumps(["/opt/venv/bin/python", "-c", expression])
            + "\n"
        )
        name = "privacytrace-controlled-" + fault + ":" + lab.project
        execute(
            [
                "docker",
                "build",
                "--network=none",
                "--label",
                "privacytrace.acceptance.fault=" + fault,
                "-t",
                name,
                str(context),
            ]
        )
        images[fault] = execute(["docker", "image", "inspect", name, "--format", "{{.Id}}"])
    evidence = {}
    try:
        for fault in ("timeout", "oom", "orphan"):
            _boot(lab, original)
            scope = create_scope(topology, "controlled-" + fault, "Synthetic fault policy.")
            assert upload_apk(topology, scope, fixture.single_apk).status == 200
            watermark = _watermark(lab)
            image = images["timeout" if fault == "orphan" else fault]
            config = scanner_override(original, image)
            config["services"]["runner"]["environment"]["PRIVACYTRACE_RUNNER_TIMEOUT"] = (
                "180" if fault == "orphan" else "2" if fault == "timeout" else "20"
            )
            config["services"]["worker"]["environment"]["PRIVACYTRACE_LEASE_SECONDS"] = "5"
            _boot(lab, config)
            assert start_job(topology, scope).status == 200 and scope.job_id
            if fault != "orphan":
                final = poll_job(topology, scope, budget_s=90, interval_s=0.2)
                assert final["state"] == "FAILED"
                results = _results(lab, watermark)
                result = next(r for r in results if r.get("error") == fault.upper())
                proof = result["receipt"]
                assert proof["cleanup_verified"] and proof["input_removed"]
                if fault == "oom":
                    assert proof["exit_state"]["OOMKilled"] is True
                assert not _owned_scanners(lab)
                evidence[fault] = {
                    "error": result["error"],
                    "image_id": image,
                    "actual_isolation": proof,
                }
            else:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if _owned_scanners(lab):
                        break
                    time.sleep(0.05)
                else:
                    raise AssertionError("no owned scanner to orphan")
                before = _row(lab, scope.job_id)
                lab.run("kill", "--signal", "SIGKILL", "worker")
                lab.run("kill", "--signal", "SIGKILL", "runner")
                assert _owned_scanners(lab), "controlled orphan did not survive Runner termination"
                lab.run("start", "runner")
                deadline = time.monotonic() + 20
                while _owned_scanners(lab) and time.monotonic() < deadline:
                    time.sleep(0.1)
                assert not _owned_scanners(lab), "Runner did not reclaim its own orphan"
                # Restore the normal scanner, then let real lease recovery and
                # Celery redelivery finish this same job with a higher fence.
                _boot(lab, original)
                final = poll_job(topology, scope, budget_s=120, interval_s=0.5)
                after = _row(lab, scope.job_id)
                assert final["state"] == "SUCCEEDED" and after["fence"] > before["fence"]
                evidence[fault] = {
                    "orphan_observed": True,
                    "orphan_removed_on_restart": True,
                    "old_fence": before["fence"],
                    "new_fence": after["fence"],
                    "same_job_recovered": True,
                    "final_state": final["state"],
                }
            assert not cleanup_created_scopes()
        return evidence
    finally:
        _boot(lab, original)
