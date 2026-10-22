"""Operate only lane E's owned resources and retained synthetic capabilities."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from deploy.acceptance.fault_drill import _owned_scanners
from deploy.acceptance.issue133.observe import laboratory, observe
from deploy.acceptance.provision import execute
from deploy.acceptance.topology import Topology, request

MAX_WAIT_SECONDS = 900


def state_snapshot(lab):
    """Read-only persistent state; aliases only, no raw scope or job ids."""
    return json.loads(lab.python(Path(__file__).with_name("state_query.py").read_text()))


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
    base_url = os.environ.get("PT133E_WEB_BASE_URL", "https://127.0.0.1:8443")
    host = os.environ.get("PT133E_WEB_HOST", "127.0.0.1")
    ca_file = Path(os.environ.get("PT133E_WEB_CA") or (lab.root / "public-ca.pem"))
    topology = Topology(
        base_url=base_url,
        host=host,
        instance_id=lab.state["instance_id"],
        ca_file=ca_file,
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


def resolve_draft_alias(lab, alias):
    """Map the private control alias (D1...) to the read-only observer alias."""
    scopes = json.loads((lab.root / "e-private/scopes.json").read_text())
    matches = [draft for draft, entry in scopes.items() if entry["alias"] == alias]
    if len(matches) != 1:
        raise ValueError("private synthetic scope not captured")
    return hashlib.sha256(matches[0].encode()).hexdigest()[:12]


def material_layers(lab, alias, job_aliases=()):
    """Read every storage layer for one draft scope through the read-only observer."""
    draft_alias = resolve_draft_alias(lab, alias)
    state = state_snapshot(lab)
    scope = next(
        (
            item
            for item in state["scopes"]
            if item["scope_alias"] == draft_alias and item["kind"] == "DRAFT"
        ),
        None,
    )
    known = set(job_aliases)
    for row in state.get("runtime_inputs", []):
        if row["draft_alias"] == draft_alias:
            known.add(row["job_alias"])
    jobs = [item for item in state["jobs"] if item["job_alias"] in known]
    outbox = [item for item in state["outbox"] if item["job_alias"] in known]
    audit = [
        item
        for item in state["audit"]
        if item["scope_alias"] == draft_alias or item["scope_alias"] in known
    ]
    documents = [item for item in state["documents"] if item["scope_alias"] == draft_alias]
    inputs = [
        item
        for item in state["runtime_inputs"]
        if item["draft_alias"] == draft_alias or item["job_alias"] in known
    ]
    runner = [
        item
        for item in state["runner_materials"]
        if item["draft_alias"] == draft_alias or item["scope_alias"] in known
    ]
    uploads = [item for item in state["uploads"] if item["draft_alias"] == draft_alias]
    deletions = [
        item
        for item in state["deletions"]
        if item["scope_alias"] == draft_alias or item["scope_alias"] in known
    ]
    reports = [item for item in state["reports"] if item["job_alias"] in known]
    result = {
        "scope": alias,
        "draft_alias": draft_alias,
        "scope_row": scope,
        "known_job_aliases": sorted(known),
        "jobs": jobs,
        "outbox": outbox,
        "audit": audit,
        "documents": documents,
        "runtime_inputs": inputs,
        "runner_materials": runner,
        "uploads": uploads,
        "deletions": deletions,
        "reports": reports,
        "journal": {
            "path_present": state["journal"]["path_present"],
            "tail_kinds": [
                {
                    "kind": item["kind"],
                    "scope_alias": item["scope_alias"],
                    "sequence": item["sequence"],
                }
                for item in state["journal"]["entries_tail"]
                if scope and item["scope_alias"] == scope["scope_alias"]
            ],
        },
        "objects": state["objects"],
        "draft_dir": state["drafts"].get(draft_alias),
        "material_files": state["material_files"],
        "counts": state["counts"],
        "case_passed": False,
    }
    return result


def scope_list(lab):
    observe(lab)
    state = state_snapshot(lab)
    registry = json.loads((lab.root / "e-private/scopes.json").read_text())
    aliases = {}
    for draft_id, entry in registry.items():
        aliases[entry["alias"]] = {
            "scope_alias": hashlib.sha256(draft_id.encode()).hexdigest()[:12],
            "has_captured_token": "token" in entry,
            "job_aliases": [],
        }
    for row in state["runtime_inputs"]:
        for item in aliases.values():
            if item["scope_alias"] == row["draft_alias"]:
                item["job_aliases"].append(row["job_alias"])
    scopes = [
        {
            "alias": alias,
            "draft_alias": info["scope_alias"],
            "has_captured_token": info["has_captured_token"],
            "job_aliases": sorted(set(info["job_aliases"])),
            "db_scope_present": any(
                item["scope_alias"] == info["scope_alias"] and item["kind"] == "DRAFT"
                for item in state["scopes"]
            ),
            "tombstone": any(
                item["scope_alias"] == info["scope_alias"] and item["tombstone"]
                for item in state["scopes"]
            ),
        }
        for alias, info in sorted(aliases.items(), key=lambda pair: int(pair[0][1:]))
    ]
    return {"scopes": scopes, "counts": state["counts"], "captured_private_scopes": len(registry)}


def wait_job_state(lab, draft_alias, states, timeout):
    deadline = time.monotonic() + min(timeout, MAX_WAIT_SECONDS)
    last = None
    while time.monotonic() < deadline:
        state = state_snapshot(lab)
        aliases = {
            row["job_alias"] for row in state["runtime_inputs"] if row["draft_alias"] == draft_alias
        }
        matching = [item for item in state["jobs"] if item["job_alias"] in aliases]
        last = matching
        if any(item["state"] in states for item in matching):
            return {"draft_alias": draft_alias, "states": sorted(states), "jobs": matching}
        time.sleep(0.5)
    raise AssertionError(f"job state did not reach {sorted(states)}; last={last}")


def wait_scope_tombstone(lab, alias, job_aliases, timeout):
    draft_alias = resolve_draft_alias(lab, alias)
    deadline = time.monotonic() + min(timeout, MAX_WAIT_SECONDS)
    last = None
    while time.monotonic() < deadline:
        state = state_snapshot(lab)
        scope = next(
            (
                item
                for item in state["scopes"]
                if item["scope_alias"] == draft_alias and item["kind"] == "DRAFT"
            ),
            None,
        )
        jobs = [item for item in state["jobs"] if item["job_alias"] in set(job_aliases)]
        last = {"scope": scope, "jobs": jobs}
        if (
            scope
            and scope["tombstone"]
            and all(item["execution_state"] == "REVOKED" for item in jobs)
        ):
            return {"draft_alias": alias, "scope": scope, "jobs": jobs}
        time.sleep(0.5)
    raise AssertionError(f"scope tombstone not observed; last={last}")


def wait_runner_idle(lab, timeout):
    deadline = time.monotonic() + min(timeout, MAX_WAIT_SECONDS)
    last = None
    while time.monotonic() < deadline:
        active = _owned_scanners(lab)
        running = []
        path = lab.root / "runner/requests.sqlite"
        if path.exists():
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                running = connection.execute(
                    "SELECT count(*) FROM operations WHERE state='RUNNING'"
                ).fetchone()[0]
        last = {"active_scanners": len(active), "runner_running": running}
        if not active and not running:
            return last
        time.sleep(0.5)
    raise AssertionError(f"runner did not become idle; last={last}")


def replay_deleted(lab, alias):
    topology, draft, token = scope_context(lab, alias)
    saved = json.loads((lab.root / "e-private/scopes.json").read_text())[draft]
    probes = [
        ("GET", f"/api/v1/web/drafts/{draft}", None),
        ("POST", f"/api/v1/web/drafts/{draft}/start", {"revision": 1, "request_id": "0" * 32}),
        ("DELETE", f"/api/v1/web/drafts/{draft}", None),
    ]
    for job in saved.get("jobs", []):
        probes += [
            ("GET", f"/api/v1/jobs/{job}", None),
            ("GET", f"/api/v1/jobs/{job}/report", None),
            ("GET", f"/api/v1/jobs/{job}/evidence/{'0' * 32}", None),
            ("POST", f"/api/v1/jobs/{job}/cancel", {}),
            ("POST", f"/api/v1/jobs/{job}/retry", {}),
            ("DELETE", f"/api/v1/jobs/{job}", None),
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
    private = lab.root / "e-private"
    private.mkdir(mode=0o700, exist_ok=True)
    context = private / "delayed-scanner"
    context.mkdir(mode=0o700, exist_ok=True)
    tag = "pt133e-delayed:" + lab.project
    base_tag = "pt133e-delay-base:" + lab.project
    execute(["docker", "tag", lab.state["images"]["api"], base_tag])
    (context / "Dockerfile").write_text(
        f"FROM {base_tag}\nUSER 65534:65534\nHEALTHCHECK NONE\nENTRYPOINT "
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


def restore_scanner(lab):
    original = lab.root / "e-private/original-laboratory.json"
    if not original.is_file():
        raise ValueError("original laboratory configuration is not retained")
    config_path = lab.root / "laboratory.json"
    config_path.write_bytes(original.read_bytes())
    lab.run("up", "-d", "--no-deps", "--force-recreate", "api", "worker", "runner")
    lab.ready()
    image = json.loads(config_path.read_text())["services"]["runner"].get("image")
    return {"restored": True, "runner_image": image}


def wait_scan(lab):
    until = time.monotonic() + 120
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
    until = time.monotonic() + 120
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
            "identity",
            "health",
            "observe",
            "scope-list",
            "scope",
            "material-layers",
            "replay-deleted",
            "delete-scope",
            "stop-worker",
            "start-worker",
            "stop-web",
            "start-web",
            "set-rate-limit",
            "pause-worker",
            "unpause-worker",
            "restart-api",
            "restart-runner",
            "delay-scanner",
            "restore-scanner",
            "runner-ledger",
            "wait-scan",
            "wait-result",
            "wait-job-state",
            "wait-tombstone",
            "wait-runner-idle",
        ),
    )
    parser.add_argument("--scope", default="D1")
    parser.add_argument("--states", default="SUCCEEDED")
    parser.add_argument("--job-alias", action="append", default=[])
    parser.add_argument("--draft-alias", default="")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--delay-seconds", type=int, choices=(20, 40, 80), default=20)
    parser.add_argument("--rate-limit", type=int, default=600)
    args = parser.parse_args()
    lab = laboratory()
    if args.action == "identity":
        result = {
            "project": lab.project,
            "instance_id": lab.state["instance_id"],
            "source_sha": lab.state["source_sha"],
            "images": lab.state["images"],
            "https_port": lab.state["https_port"],
            "scan_host_separate": lab.state.get("scan_host_separate", False),
        }
    elif args.action == "health":
        lab.ready()
        result = {"ready": True}
    elif args.action == "observe":
        result = observe(lab)
    elif args.action == "scope-list":
        result = scope_list(lab)
    elif args.action == "scope":
        result = inspect_scope(lab, args.scope)
    elif args.action == "material-layers":
        result = material_layers(lab, args.scope, args.job_alias)
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
    elif args.action == "stop-web":
        lab.run("stop", "web")
        result = {"owned_role": "web", "operation": "stop", "transport_unreachable": True}
    elif args.action == "start-web":
        lab.run("up", "-d", "--no-deps", "web")
        result = {"owned_role": "web", "operation": "start", "transport_reachable": True}
    elif args.action == "set-rate-limit":
        config_path = lab.root / "laboratory.json"
        config = json.loads(config_path.read_text())
        config.setdefault("services", {}).setdefault("api", {}).setdefault("environment", {})[
            "PRIVACYTRACE_RATE_LIMIT"
        ] = str(args.rate_limit)
        config_path.write_text(json.dumps(config))
        lab.run("up", "-d", "--no-deps", "--force-recreate", "api")
        lab.ready(timeout=360)
        result = {"owned_role": "api", "rate_limit_per_minute": args.rate_limit}
    elif args.action == "restart-runner":
        lab.run("restart", "runner")
        time.sleep(3)
        result = {"owned_role": "runner", "operation": "restart", "faulted_state_cleared": True}
    elif args.action == "restore-scanner":
        result = restore_scanner(lab)
    elif args.action == "wait-scan":
        result = wait_scan(lab)
    elif args.action == "wait-result":
        result = wait_result(lab)
    elif args.action == "wait-job-state":
        if not args.draft_alias:
            raise SystemExit("wait-job-state requires --draft-alias")
        result = wait_job_state(
            lab,
            args.draft_alias,
            {item.strip() for item in args.states.split(",") if item.strip()},
            args.timeout,
        )
    elif args.action == "wait-tombstone":
        result = wait_scope_tombstone(lab, args.scope, args.job_alias, args.timeout)
    elif args.action == "wait-runner-idle":
        result = wait_runner_idle(lab, args.timeout)
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
        # API recovery after a large store can take longer than the default
        # 120s readiness budget; keep the bounded wait explicit.
        lab.ready(timeout=360)
        result = {"owned_role": "api", "operation": "restart", "ready": True}
    else:
        operation = args.action.removesuffix("-worker")
        lab.run(operation, "worker")
        result = {"owned_role": "worker", "operation": operation}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
