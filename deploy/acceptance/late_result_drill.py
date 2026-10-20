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
    fixture = Fixtures.build()
    scope = create_scope(topology, "late-result-canary", "Synthetic cancellation policy.")
    assert upload_apk(topology, scope, fixture.single_apk).status == 200
    database = lab.root / "runner/requests.sqlite"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
        watermark = conn.execute("SELECT coalesce(max(rowid),0) FROM operations").fetchone()[0]
    runner_paused = worker_paused = False
    try:
        lab.run("pause", "runner")
        runner_paused = True
        assert start_job(topology, scope).status == 200 and scope.job_id
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            active = _row(lab, scope.job_id)
            if active["state"] == "RUNNING":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("real consumer did not acquire a lease")
        lab.run("pause", "worker")
        worker_paused = True
        lab.run("unpause", "runner")
        runner_paused = False
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
        if runner_paused:
            lab.run("unpause", "runner")
        if worker_paused:
            lab.run("unpause", "worker")
        lab.ready()
