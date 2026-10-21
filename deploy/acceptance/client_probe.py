"""Drive one real client identity against the control plane from inside the lab.

The API keys its admission budgets on the peer address of the connection, so a
single external client cannot exhaust the queue or disk budgets: it runs out of
its own retained-draft quota first. Each probe container therefore acts as one
distinct, real identity on the laboratory network instead of forging forwarding
headers, which the request guard rejects for untrusted peers.

The plan arrives as one JSON argument and the result leaves as one JSON line so
the host side never has to parse command output.
"""

import json
import socket
import sys
import urllib.error
import urllib.request
import uuid


def call(base_url, host, method, path, *, body=None, token="", timeout=120):
    """Issue one request and report the status instead of raising for it."""
    headers = {"Host": host}
    payload = body
    if isinstance(body, (dict, list)):
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if payload is not None:
        headers["Content-Length"] = str(len(payload))
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        base_url + path, data=payload, headers=headers, method=method
    )
    # Laboratory traffic is loopback-only; never let a proxy setting intercept it.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read()
            status = response.status
            returned = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as error:
        raw = error.read()
        status = error.code
        returned = {key.lower(): value for key, value in error.headers.items()}
    try:
        decoded = json.loads(raw) if raw else None
    except ValueError:
        decoded = None
    code = None
    if isinstance(decoded, dict):
        detail = decoded.get("detail")
        code = detail if isinstance(detail, str) else decoded.get("code")
    return {
        "status": status,
        "code": code,
        "retry_after": returned.get("retry-after"),
        "json": decoded,
        "body_bytes": len(raw),
    }


def _draft_body(name):
    return {
        "name": name,
        "sources": [
            {
                "id": "policy",
                "title": "Synthetic acceptance policy",
                "text": "Synthetic capacity policy.",
                "url": "",
                "source_type": "OFFICIAL_WEB_POLICY",
            }
        ],
    }


def run(plan):
    base_url = plan["base_url"]
    host = plan["host"]
    with open(plan["apk"], "rb") as handle:
        apk = handle.read()
    drafts = {}
    results = []
    for step in plan["steps"]:
        operation = step["op"]
        name = step.get("draft")
        entry = {"op": operation, "draft": name}
        if operation == "draft":
            reply = call(
                base_url, host, "POST", "/api/v1/web/drafts", body=_draft_body(step["name"])
            )
            entry.update(reply)
            if reply["status"] == 200 and isinstance(reply["json"], dict):
                payload = reply["json"]
                drafts[name] = {
                    "id": str(payload["id"]),
                    "token": payload.get("capability_token") or payload.get("token") or "",
                    "revision": int(payload.get("revision", 1)),
                }
                entry["draft_id"] = drafts[name]["id"]
                # Returned so the host can poll and clean up; never put in evidence.
                entry["token"] = drafts[name]["token"]
        elif operation in {"upload", "start", "state", "delete"}:
            target = drafts.get(name)
            if target is None:
                # A refused draft leaves nothing to act on; record it instead of
                # dying with a KeyError so the whole plan stays observable.
                entry.update({"status": None, "code": "STEP_UNAVAILABLE", "retry_after": None})
                results.append(entry)
                continue
            if operation == "upload":
                reply = call(
                    base_url,
                    host,
                    "POST",
                    f"/api/v1/web/drafts/{target['id']}/apk",
                    body=apk,
                    token=target["token"],
                    timeout=300,
                )
                entry.update(reply)
                if reply["status"] == 200 and isinstance(reply["json"], dict):
                    target["revision"] = int(
                        reply["json"].get("revision", target["revision"] + 1)
                    )
            elif operation == "start":
                reply = call(
                    base_url,
                    host,
                    "POST",
                    f"/api/v1/web/drafts/{target['id']}/start",
                    body={
                        "revision": target["revision"],
                        # The start contract requires a 32-hex idempotency key; the
                        # draft name is a label, not one, and would be rejected as
                        # INPUT_VALIDATION_FAILED before any budget is consulted.
                        "request_id": step.get("request_id") or uuid.uuid4().hex,
                    },
                    token=target["token"],
                )
                entry.update(reply)
                if reply["status"] == 200 and isinstance(reply["json"], dict):
                    target["job_id"] = str(
                        reply["json"].get("id") or reply["json"].get("job_id")
                    )
                    entry["job_id"] = target["job_id"]
            elif operation == "state":
                if "job_id" not in target:
                    entry.update(
                        {"status": None, "code": "STEP_UNAVAILABLE", "retry_after": None}
                    )
                    results.append(entry)
                    continue
                reply = call(
                    base_url,
                    host,
                    "GET",
                    f"/api/v1/jobs/{target['job_id']}",
                    token=target["token"],
                )
                entry.update(reply)
                if isinstance(reply["json"], dict):
                    entry["state"] = reply["json"].get("state")
            else:
                entry.update(
                    call(
                        base_url,
                        host,
                        "DELETE",
                        f"/api/v1/web/drafts/{target['id']}",
                        token=target["token"],
                    )
                )
        else:
            raise ValueError(f"unknown probe step: {operation}")
        entry.pop("json", None)
        results.append(entry)
    return {"peer_ip": socket.gethostbyname(socket.gethostname()), "steps": results}


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run(json.loads(sys.argv[1]))) + "\n")
