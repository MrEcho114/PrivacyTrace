"""Freeze the real consumer before it can commit a completed Runner result."""

import hashlib
import json
import sqlite3
import time

from .r2_business_loop import Fixtures, create_scope, poll_job, start_job, upload_apk
from .topology import request


def _row(lab, job_id):
    source = (
        "import os,json;from pathlib import Path;"
        "from privacytrace.storage_factory import create_store;"
        "from privacytrace.postgres_execution import PostgresExecution;"
        "s=create_store(Path(os.environ['PRIVACYTRACE_STORE_ROOT']));"
        f"r=PostgresExecution(s).status({job_id!r});"
        "print(json.dumps({'state':r['state'],'fence':r['fence']}));s.close()"
    )
    return json.loads(lab.python(source))


def drill(lab, topology):
    from .fault_drill import _boot, _owned_scanners, scanner_override
    from .provision import execute

    original = json.loads((lab.root / "laboratory.json").read_text())
    tag = "privacytrace-delayed-scan:" + lab.project
    base = "privacytrace-delay-base:" + lab.project
    execute(["docker", "tag", lab.state["images"]["api"], base])
    context = lab.root / "delayed-scan-build"
    context.mkdir(mode=0o700, exist_ok=True)
    # Delay the actual parser, so pausing the consumer cannot race ahead of
    # sending its Runner request. The result still comes from apk_worker.
    (context / "Dockerfile").write_text(
        f"FROM {base}\nUSER 65534:65534\nHEALTHCHECK NONE\nENTRYPOINT "
        + json.dumps(
            [
                "/opt/venv/bin/python",
                "-c",
                "import time,runpy;time.sleep(5);"
                "runpy.run_module('privacytrace.apk_worker',run_name='__main__')",
            ]
        )
        + "\n"
    )
    execute(["docker", "build", "--network=none", "-t", tag, str(context)])
    image = execute(["docker", "image", "inspect", tag, "--format", "{{.Id}}"])
    fixture = Fixtures.build()
    scope = create_scope(topology, "late-result-canary", "Synthetic cancellation policy.")
    assert upload_apk(topology, scope, fixture.single_apk).status == 200
    database = lab.root / "runner/requests.sqlite"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
        watermark = conn.execute("SELECT coalesce(max(rowid),0) FROM operations").fetchone()[0]
    worker_paused = False
    try:
        _boot(lab, scanner_override(original, image))
        assert start_job(topology, scope).status == 200 and scope.job_id
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            active = _row(lab, scope.job_id)
            if active["state"] == "RUNNING" and _owned_scanners(lab):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("real consumer did not start the controlled delayed scanner")
        lab.run("pause", "worker")
        worker_paused = True
        deadline = time.monotonic() + 20
        result = None
        while time.monotonic() < deadline:
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "SELECT result FROM operations WHERE rowid>? AND state='DONE'", (watermark,)
                ).fetchone()
            if row:
                result = json.loads(row[0])
                break
            time.sleep(0.05)
        assert result and result.get("error") is None and result.get("receipt")
        assert result["result"]["apk_sha256"] == fixture.single_sha256
        assert (
            request(
                topology, f"/api/v1/jobs/{scope.job_id}/cancel", method="POST", token=scope.token
            ).status
            == 200
        )
        revoked = _row(lab, scope.job_id)
        assert revoked["fence"] > active["fence"]
        lab.run("unpause", "worker")
        worker_paused = False
        final = poll_job(topology, scope, budget_s=20, interval_s=0.1)
        time.sleep(2)  # let the actual resumed consumer attempt its fenced commit
        final = poll_job(topology, scope, budget_s=10, interval_s=0.1)
        report = request(topology, f"/api/v1/jobs/{scope.job_id}/report", token=scope.token)
        assert final["state"] == "CANCELLED" and report.status != 200
        return {
            "old_fence": active["fence"],
            "revoked_fence": revoked["fence"],
            "completed_output_sha256": hashlib.sha256(
                json.dumps(result, sort_keys=True).encode()
            ).hexdigest(),
            "input_sha256": fixture.single_sha256,
            "final_state": final["state"],
            "report_status": report.status,
            "runner_isolation": result["receipt"],
        }
    finally:
        if worker_paused:
            lab.run("unpause", "worker")
        _boot(lab, original)
