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
    marker = Path("/var/tmp/pt133e/current")
    candidate = Path(marker.read_text())
    root = candidate.resolve()
    if root.parent != marker.parent or candidate.is_symlink():
        raise ValueError("lane E ownership mismatch")
    return Laboratory(root)


def observe(lab):
    private = lab.root / "e-private"
    private.mkdir(mode=0o700, exist_ok=True)
    registry = private / "scopes.json"
    scopes = json.loads(registry.read_text()) if registry.exists() else {}
    raw = lab.run("exec", "-T", "web", "cat", "/tmp/pt133e-access.json")
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
        user_agent = " ".join(req.get("headers", {}).get("User-Agent", []))
        actor = "ANDROID_NATIVE" if user_agent == "PrivacyTrace-Android" else "OBSERVER"
        identity = re.search(r"\b[a-f0-9]{32}\b", route)
        requests.append(
            {
                "at": item["ts"],
                "actor": actor,
                "scope_alias": hashlib.sha256(identity[0].encode()).hexdigest()[:12]
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
        job["job_alias"] = alias(job.pop("job_id"))
    for scope in database["scopes"]:
        scope["scope_alias"] = alias(scope.pop("scope_id"))
    runner = []
    runner_path = lab.root / "runner/requests.sqlite"
    if runner_path.exists():
        with sqlite3.connect(f"file:{runner_path}?mode=ro", uri=True) as connection:
            for state, result in connection.execute("SELECT state,result FROM operations"):
                data = json.loads(result) if result else {}
                runner.append(
                    {
                        "state": state,
                        "error": data.get("error"),
                        "has_receipt": bool(data.get("receipt")),
                        "result_sha256": hashlib.sha256(
                            result if isinstance(result, bytes) else (result or "").encode()
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
