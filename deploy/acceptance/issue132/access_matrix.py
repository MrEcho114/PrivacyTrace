"""N05/N06 HTTP guard checks. This does not certify the Android scenarios.

Run only against explicitly disposable, quiescent tasks. The owner creates and
cleans them; a broken guard could let a destructive probe reach the service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx


@dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    body: dict | None = None


def endpoints(target: dict) -> list[Endpoint]:
    """Explicit inventory: additions to product routes must extend the matrix."""
    values = {
        key: quote(str(target[key]), safe="")
        for key in ("draft_id", "job_id", "source_id", "attempt_id", "evidence_id")
    }
    draft = "/api/v1/web/drafts/{draft_id}".format(**values)
    source = draft + "/sources/{source_id}".format(**values)
    job = "/api/v1/jobs/{job_id}".format(**values)
    revision = {"revision": target["revision"]}
    return [
        Endpoint("GET", draft),
        Endpoint("DELETE", draft),
        Endpoint("POST", draft + "/apk"),
        Endpoint("POST", draft + "/package-set"),
        Endpoint("POST", source + "/fetch", revision),
        Endpoint("POST", source + "/attempts", {**revision, "attempt_id": "d" * 32}),
        Endpoint("GET", source + "/attempts/{attempt_id}".format(**values)),
        Endpoint("POST", source + "/extract", {**revision, "attempt_id": target["attempt_id"]}),
        Endpoint("POST", draft + "/candidates", {**revision, "candidates": []}),
        Endpoint("POST", draft + "/start", {**revision, "request_id": "e" * 32}),
        Endpoint("POST", draft + "/sources/discover"),
        Endpoint("POST", draft + "/import-external", {
            "source": {"title": "N05 isolation probe", "text": "Controlled policy text."},
            "claims": [],
        }),
        Endpoint("GET", job),
        Endpoint("GET", job + "/report"),
        Endpoint("GET", job + "/evidence/{evidence_id}".format(**values)),
        Endpoint("POST", job + "/reviews", {"actor": "N05", "reason": "Isolation probe"}),
        Endpoint("POST", job + "/cancel"),
        Endpoint("POST", job + "/retry"),
        Endpoint("DELETE", job),
    ]


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def snapshot(client, target: dict, pause: float) -> str:
    observations = []
    for endpoint in endpoints(target):
        if endpoint.method != "GET":
            continue
        time.sleep(pause)
        response = client.get(endpoint.path, headers={"Authorization": "Bearer " + target["token"]})
        if response.status_code != 200:
            raise ValueError("Owner read precondition failed")
        observations.append(response.json())
    return digest(observations)


def run_matrix(client, target: dict, other_token: str, *, pause: float = 0) -> list[dict]:
    if not other_token or other_token == target["token"]:
        raise ValueError("Independent attacker and owner capabilities required")
    baseline = snapshot(client, target, pause)
    variants = [
        ("missing", {}, 401),
        ("malformed_bearer", {"Authorization": "Bearer damaged"}, 401),
        ("wrong_bearer", {"Authorization": "Bearer " + other_token}, 403),
        ("malformed_custom", {"X-PrivacyTrace-Token": "damaged"}, 401),
        ("wrong_custom", {"X-PrivacyTrace-Token": other_token}, 403),
    ]
    results = []
    for index, endpoint in enumerate(endpoints(target)):
        for variant, headers, expected in variants:
            time.sleep(pause)
            kwargs = {"json": endpoint.body} if endpoint.body is not None else {}
            try:
                response = client.request(endpoint.method, endpoint.path, headers=headers, **kwargs)
            except httpx.HTTPError:
                results.append({
                    "endpoint": index + 1, "method": endpoint.method, "variant": variant,
                    "expected_http": expected, "actual_http": None, "status": "FAILED",
                    "error": "HTTP_TRANSPORT_ERROR", "target_unchanged": None,
                })
                return results
            # Only the generic denial is permitted, never target material or an
            # arbitrary 401/403 emitted by an unrelated proxy/auth challenge.
            detail = (
                "Draft capability token required" if expected == 401 else "Draft access denied"
            ) if index < 12 else (
                "Invalid capability token format" if variant.startswith("malformed")
                else "Capability token required" if expected == 401
                else "Access to job denied with provided token"
            )
            try:
                unchanged = snapshot(client, target, pause) == baseline
            except (ValueError, httpx.HTTPError):
                unchanged = False
            try:
                denial = response.json() == {"detail": detail}
            except ValueError:
                denial = False
            passed = (
                response.status_code == expected
                and denial
                and unchanged
            )
            results.append({
                "endpoint": index + 1, "method": endpoint.method, "variant": variant,
                "expected_http": expected, "actual_http": response.status_code,
                "target_unchanged": unchanged, "status": "PASSED" if passed else "FAILED",
                "response_sha256": hashlib.sha256(response.content).hexdigest(),
                "target_snapshot_sha256": baseline,
            })
            if not passed:
                # A failed mutation may have changed the target. Do not keep
                # attacking it, or silently re-baseline onto the changed state.
                return results
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pause", type=float, default=1.1,
                        help="Seconds before each request; keeps the default 60/min limiter active")
    args = parser.parse_args()
    if args.pause < 0 or args.output.exists():
        parser.error("pause must be nonnegative and output must be a new file")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("disposable") is not True:
        parser.error("only explicitly disposable targets are permitted")
    origin = urlsplit(config["origin"])
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.query or origin.fragment or origin.path not in {"", "/"}):
        parser.error("origin must be a plain HTTPS origin")
    target = {**config["target"], "token": os.environ[config["owner_token_env"]]}
    other = os.environ[config["other_token_env"]]
    context = ssl.create_default_context(cafile=config.get("ca_file"))
    receipt = {
        "case": "N05/N06 HTTP subset", "record_kind": "EXTERNAL_HTTP_SUBSET",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            cwd=Path(__file__).resolve().parents[3],
        ).strip(),
        "checks": [], "error": None,
        "scenario_status": {"N05": "NOT_RUN", "N06": "NOT_RUN", "N07": "NOT_RUN", "N08": "NOT_RUN"},
        "cleanup": "CALLER_OWNS_TARGETS; verify deletion and resource cleanup separately",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    try:
        with httpx.Client(base_url=config["origin"].rstrip("/"), verify=context,
                          trust_env=False, follow_redirects=False, timeout=20) as client:
            capabilities = client.get("/api/v1/mobile-capabilities")
            if (capabilities.status_code != 200 or capabilities.json().get("supported") is not True
                    or capabilities.json().get("instance_id") != config["instance_id"]):
                raise ValueError("Live durable instance identity precondition failed")
            receipt["instance_id"] = capabilities.json()["instance_id"]
            receipt["checks"] = run_matrix(client, target, other, pause=args.pause)
    except (httpx.HTTPError, ValueError) as error:
        receipt["error"] = type(error).__name__  # never publish URLs, paths, credentials or bodies
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    receipt["subset_status"] = (
        "FAILED" if receipt["error"] or len(receipt["checks"]) != 95
        or any(row["status"] != "PASSED" for row in receipt["checks"]) else "PASSED"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
    with args.output.open("xb") as output:
        output.write(encoded)
    actual = args.output.read_bytes()
    if actual != encoded:
        raise OSError("receipt readback failed")
    print(json.dumps({"subset_status": receipt["subset_status"], "checks": len(receipt["checks"]),
                      "receipt_sha256": hashlib.sha256(actual).hexdigest()}))
    return 0 if receipt["subset_status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
