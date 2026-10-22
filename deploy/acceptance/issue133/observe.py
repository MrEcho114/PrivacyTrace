"""Read lane E's real proxy/DB/Runner state without exporting capabilities."""

import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from deploy.acceptance.provision import Laboratory, execute


def laboratory():
    """Resolve only the lab this lane owns.

    The harness-created marker at ``/var/tmp/pt133e/current`` is the default.
    ``PT133E_LAB_STATE`` (or ``PT_LAB_STATE``) lets the same read-only observer
    inspect one explicitly assigned lab without touching another lane's stack.
    """
    explicit = (os.environ.get("PT133E_LAB_STATE") or os.environ.get("PT_LAB_STATE") or "").strip()
    if explicit:
        root = Path(explicit).resolve()
        expected_parent = Path("/var/tmp")
        if (
            root.parent != expected_parent
            or root.is_symlink()
            or not re.fullmatch(r"pt81-[a-f0-9]{12}", root.name)
        ):
            raise ValueError("lane E ownership mismatch")
    else:
        marker = Path("/var/tmp/pt133e/current")
        candidate = Path(marker.read_text())
        root = candidate.resolve()
        if root.parent != marker.parent or candidate.is_symlink():
            raise ValueError("lane E ownership mismatch")
    if not (root / "owner.json").is_file():
        raise ValueError("lane E owner marker missing")
    return Laboratory(root)


def observe(lab):
    private = lab.root / "e-private"
    private.mkdir(mode=0o700, exist_ok=True)
    registry = private / "scopes.json"
    scopes = json.loads(registry.read_text()) if registry.exists() else {}
    log_present = True
    try:
        raw = lab.run("exec", "-T", "web", "cat", "/tmp/pt133e-access.json")
    except RuntimeError:
        raw = ""
        log_present = False
    requests = []
    for line in raw.splitlines():
        item = json.loads(line)
        req = item["request"]
        route = req["uri"].split("?", 1)[0]
        match = re.search(r"/web/drafts/([a-f0-9]{32})(?:/|$)", route)
        if match:
            draft_id = match[1]
            entry = scopes.setdefault(draft_id, {"alias": f"D{len(scopes) + 1}"})
            authorization = req.get("headers", {}).get("Authorization", [])
            if authorization and authorization[0].startswith("Bearer "):
                entry["token"] = authorization[0][7:]
        else:
            job_match = re.search(r"/jobs/([A-Za-z0-9_-]{1,100})(?:/|$)", route)
            if job_match:
                identity = job_match[1]
            else:
                identity = None
        if match:
            identity = match[1]
        user_agent = " ".join(req.get("headers", {}).get("User-Agent", []))
        actor = "ANDROID_NATIVE" if user_agent == "PrivacyTrace-Android" else "OBSERVER"
        requests.append(
            {
                "at": item["ts"],
                "actor": actor,
                "scope_alias": hashlib.sha256(identity.encode()).hexdigest()[:12]
                if identity
                else None,
                "method": req["method"],
                "route": re.sub(r"[a-f0-9]{32}", "{id}", route),
                "status": item["status"],
            }
        )
    registry.write_text(json.dumps(scopes))
    registry.chmod(0o600)
    database = json.loads(lab.python(Path(__file__).with_name("state_query.py").read_text()))

    # Identity stays comparable through one-way aliases; no scope ID or token is exported.
    def alias(value):
        return hashlib.sha256(value.encode()).hexdigest()[:12]

    for job in database["jobs"]:
        job["job_alias"] = job.get("job_alias") or alias(job.pop("job_id"))
    for scope in database["scopes"]:
        scope["scope_alias"] = scope.get("scope_alias") or alias(scope.pop("scope_id"))
    runner = []
    runner_path = lab.root / "runner/requests.sqlite"
    if runner_path.exists():
        with sqlite3.connect(f"file:{runner_path}?mode=ro", uri=True) as connection:
            for rowid, state, raw_result in connection.execute(
                "SELECT rowid,state,result FROM operations"
            ):
                data = json.loads(raw_result) if raw_result else {}
                runner.append(
                    {
                        "row": rowid,
                        "state": state,
                        "operation_alias": alias(str(rowid)),
                        "error": data.get("error"),
                        "has_receipt": bool(data.get("receipt")),
                        "result_sha256": hashlib.sha256(
                            raw_result
                            if isinstance(raw_result, bytes)
                            else (raw_result or "").encode()
                        ).hexdigest(),
                    }
                )
    identifiers = execute(["docker", "ps", "-q", "--filter", "label=privacytrace.run"]).splitlines()
    active = []
    if identifiers:
        for container in json.loads(execute(["docker", "inspect", *identifiers])):
            if any(
                Path(m["Source"]).is_relative_to(lab.root / "runner") for m in container["Mounts"]
            ):
                active.append(
                    {
                        "network": container["HostConfig"]["NetworkMode"],
                        "read_only": container["HostConfig"]["ReadonlyRootfs"],
                        "cap_drop": container["HostConfig"]["CapDrop"],
                        "privileged": container["HostConfig"]["Privileged"],
                    }
                )
    return {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha": lab.state["source_sha"],
        "project": lab.project,
        "instance_suffix": lab.state["instance_id"][-12:],
        "access_log_present": log_present,
        "credential_capture": any("token" in entry for entry in scopes.values()),
        "request_counts": dict(Counter(r["method"] + " " + r["route"] for r in requests)),
        "native_request_counts": dict(
            Counter(
                r["method"] + " " + r["route"] for r in requests if r["actor"] == "ANDROID_NATIVE"
            )
        ),
        "requests": requests,
        "persistent": database,
        "runner": runner,
        "active_scanners": active,
        "captured_private_scopes": len(scopes),
        "case_passed": False,
    }


if __name__ == "__main__":
    if os.name != "posix":
        raise SystemExit("Use the owned Linux controller")
    print(json.dumps(observe(laboratory()), indent=2))
