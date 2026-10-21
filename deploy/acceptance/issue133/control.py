"""Operate only lane E's owned resources and retained synthetic capabilities."""

import argparse
import hashlib
import json
import re
import sqlite3
import time

from deploy.acceptance.fault_drill import _owned_scanners
from deploy.acceptance.issue133.observe import laboratory, observe
from deploy.acceptance.provision import execute
from deploy.acceptance.topology import Topology, request


def scope_context(lab, alias):
    observe(lab)  # Capture new native requests; raw bearer values never leave the lab.
    scopes = json.loads((lab.root / "e-private/scopes.json").read_text())
    matches = [(draft, entry) for draft, entry in scopes.items() if entry["alias"] == alias]
    if len(matches) != 1 or "token" not in matches[0][1]:
        raise ValueError("private synthetic scope not captured")
    draft, entry = matches[0]
    web = lab.run("ps", "-q", "web")
    info = json.loads(execute(["docker", "inspect", web]))[0]
    network = lab.project + "_edge"
    connected = json.loads(execute(["docker", "inspect", "pt133e-controller"]))[0][
        "NetworkSettings"
    ]["Networks"]
    if network not in connected:
        execute(["docker", "network", "connect", network, "pt133e-controller"])
    ip = info["NetworkSettings"]["Networks"][network]["IPAddress"]
    topology = Topology(
        base_url="https://127.0.0.1:8443",
        host="127.0.0.1",
        instance_id=lab.state["instance_id"],
        ca_file=lab.root / "public-ca.pem",
        connect_ip=ip,
        allow_writes=True,
        allow_destructive=True,
    )
    return topology, draft, entry["token"]


def inspect_scope(lab, alias):
    topology, draft, token = scope_context(lab, alias)
    value = request(topology, f"/api/v1/web/drafts/{draft}", token=token)
    registry = lab.root / "e-private/scopes.json"
    saved = json.loads(registry.read_text())
    if value.status == 200:
        saved[draft]["jobs"] = [r["job_id"] for r in value.json.get("jobs", [])]
        registry.write_text(json.dumps(saved))
    result = {"scope": alias, "draft_status": value.status, "jobs": []}
    for run in (value.json or {}).get("jobs", []):
        job_id = run["job_id"]
        state = request(topology, f"/api/v1/jobs/{job_id}", token=token)
        report = request(topology, f"/api/v1/jobs/{job_id}/report", token=token)
        report_bytes = json.dumps(report.json, sort_keys=True, ensure_ascii=False).encode()
        entry = {
            "job_alias": hashlib.sha256(job_id.encode()).hexdigest()[:12],
            "state": (state.json or {}).get("state"),
            "report_status": report.status,
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        }
        if report.status == 200:
            path = lab.root / "e-private" / (entry["job_alias"] + "-report.json")
            path.write_bytes(report_bytes)
            path.chmod(0o600)
            body = report.json
            entry["report_keys"] = sorted(body)
            entry["evidence_count"] = len(body.get("evidence", []))
            entry["behavior_count"] = len(body.get("behaviors", []))
            core = {
                key: body.get(key)
                for key in (
                    "job",
                    "result",
                    "evidence",
                    "behaviors",
                    "policy_documents",
                    "metadata",
                    "coverage",
                )
            }
            entry["report_content_sha256"] = hashlib.sha256(
                json.dumps(core, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
        result["jobs"].append(entry)
    return result


def replay_deleted(lab, alias):
    topology, draft, token = scope_context(lab, alias)
    saved = json.loads((lab.root / "e-private/scopes.json").read_text())[draft]
    probes = [
        ("GET", f"/api/v1/web/drafts/{draft}", None),
        ("POST", f"/api/v1/web/drafts/{draft}/start", {"revision": 1, "request_id": "0" * 32}),
    ]
    for job in saved.get("jobs", []):
        probes += [
            ("GET", f"/api/v1/jobs/{job}", None),
            ("GET", f"/api/v1/jobs/{job}/report", None),
            ("POST", f"/api/v1/jobs/{job}/cancel", {}),
            ("POST", f"/api/v1/jobs/{job}/retry", {}),
        ]
    statuses = [
        {
            "method": method,
            "route": re.sub(r"[a-f0-9]{32}", "{id}", route),
            "status": request(topology, route, method=method, token=token, json_body=body).status,
        }
        for method, route, body in probes
    ]
    return {
        "scope": alias,
        "old_access": statuses,
        "all_rejected": all(r["status"] in {403, 404, 410} for r in statuses),
    }


def delay_scanner(lab, seconds):
    context = lab.root / "e-private/delayed-scanner"
    context.mkdir(mode=0o700, exist_ok=True)
    (context / "Dockerfile").write_text(
        f"FROM {lab.state['images']['api']}\nUSER 65534:65534\nHEALTHCHECK NONE\nENTRYPOINT "
        + json.dumps(
            [
                "/opt/venv/bin/python",
                "-c",
                f"import time,runpy;time.sleep({seconds});"
                "runpy.run_module('privacytrace.apk_worker',run_name='__main__')",
            ]
        )
        + "\n"
    )
    tag = "pt133e-delayed:" + lab.project
    execute(["docker", "build", "--network=none", "-t", tag, str(context)])
    image = execute(["docker", "image", "inspect", tag, "--format", "{{.Id}}"])
    config_path = lab.root / "laboratory.json"
    original = lab.root / "e-private/original-laboratory.json"
    if not original.exists():
        original.write_bytes(config_path.read_bytes())
    config = json.loads(config_path.read_text())
    for role in ("api", "worker", "runner"):
        config["services"].setdefault(role, {}).setdefault("environment", {})[
            "PRIVACYTRACE_RUNNER_IMAGE_ID"
        ] = image
    config_path.write_text(json.dumps(config))
    lab.run("up", "-d", "--no-deps", "--force-recreate", "api", "worker", "runner")
    lab.ready()
    return {
        "image_id": image,
        "delay_seconds": seconds,
        "scanner": "real apk_worker after controlled delay",
    }


def wait_scan(lab):
    until = time.monotonic() + 60
    while time.monotonic() < until:
        if _owned_scanners(lab):
            with sqlite3.connect(
                f"file:{lab.root}/runner/requests.sqlite?mode=ro", uri=True
            ) as connection:
                rows = connection.execute(
                    "SELECT id FROM operations WHERE state='RUNNING'"
                ).fetchall()
            if len(rows) == 1:
                (lab.root / "e-private/current-operation").write_text(rows[0][0])
                return observe(lab)
        time.sleep(0.1)
    raise AssertionError("actual owned scan did not start")


def wait_result(lab):
    operation = (lab.root / "e-private/current-operation").read_text()
    until = time.monotonic() + 60
    while time.monotonic() < until:
        with sqlite3.connect(
            f"file:{lab.root}/runner/requests.sqlite?mode=ro", uri=True
        ) as connection:
            row = connection.execute(
                "SELECT result FROM operations WHERE id=? AND state='DONE'", (operation,)
            ).fetchone()
        if row:
            value = json.loads(row[0])
            if value.get("error") or not value.get("receipt"):
                raise AssertionError("controlled scan did not produce a genuine result")
            return {
                "operation_alias": hashlib.sha256(operation.encode()).hexdigest()[:12],
                "completed_output_sha256": hashlib.sha256(row[0]).hexdigest(),
                "receipt_keys": sorted(value["receipt"]),
                "has_actual_scan_result": True,
                "observation": observe(lab),
            }
        time.sleep(0.1)
    raise AssertionError("actual Runner result was not observed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "observe",
            "scope",
            "replay-deleted",
            "delete-scope",
            "stop-worker",
            "start-worker",
            "pause-worker",
            "unpause-worker",
            "restart-api",
            "delay-scanner",
            "runner-ledger",
            "wait-scan",
            "wait-result",
        ),
    )
    parser.add_argument("--scope", default="D1")
    parser.add_argument("--delay-seconds", type=int, choices=(20, 40, 80), default=20)
    args = parser.parse_args()
    lab = laboratory()
    if args.action == "observe":
        result = observe(lab)
    elif args.action == "scope":
        result = inspect_scope(lab, args.scope)
    elif args.action == "replay-deleted":
        result = replay_deleted(lab, args.scope)
    elif args.action == "delete-scope":
        topology, draft, token = scope_context(lab, args.scope)
        result = {
            "scope": args.scope,
            "delete_status": request(
                topology, f"/api/v1/web/drafts/{draft}", method="DELETE", token=token
            ).status,
        }
    elif args.action == "delay-scanner":
        result = delay_scanner(lab, args.delay_seconds)
    elif args.action == "wait-scan":
        result = wait_scan(lab)
    elif args.action == "wait-result":
        result = wait_result(lab)
    elif args.action == "runner-ledger":
        with sqlite3.connect(
            f"file:{lab.root}/runner/requests.sqlite?mode=ro", uri=True
        ) as connection:
            result = [
                {"row": row, "state": state, "has_result": bool(raw)}
                for row, state, raw in connection.execute(
                    "SELECT rowid,state,result FROM operations"
                )
            ]
    elif args.action == "restart-api":
        lab.run("restart", "api")
        result = {"owned_role": "api", "operation": "restart"}
    else:
        operation = args.action.removesuffix("-worker")
        lab.run(operation, "worker")
        result = {"owned_role": "worker", "operation": operation}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
