"""N08 probes from the installed app UID; provision/cleanup remain caller-owned."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

MARKER = re.compile(r"PT132STATUS:(\d{3})")
PACKAGE = "org.privacytrace.mobile"


def observation(result) -> tuple[int | None, str]:
    """A curl exit code describes its last URL; reject hidden extra transfers."""
    matches = list(MARKER.finditer(result.stdout))
    if len(matches) != 1 or result.stdout[matches[0].end():].strip():
        return None, ""
    return int(matches[0].group(1)), result.stdout[:matches[0].start()]


def http_passed(result, expected: int, body=None) -> bool:
    status, raw = observation(result)
    if result.returncode != 0 or result.stderr or status != expected:
        return False
    if body is None:
        return True
    try:
        return json.loads(raw) == body
    except ValueError:
        return False


def mtls_passed(result) -> bool:
    status, body = observation(result)
    return (
        result.returncode in {35, 55, 56}
        and status == 0
        and body == ""
        and re.search(r"certificate[_ ]required|alert.*certificate|certificate.*alert",
                      result.stderr, re.IGNORECASE) is not None
    )


def curl_arguments(hosts: list[str], args: list[str]) -> list[str]:
    # adb shell joins arguments for Android's shell. An unquoted '*' expands
    # into root-directory names and curl can still exit zero for its last URL.
    return [
        "shell", "run-as", PACKAGE, "/system/bin/curl", "--disable", "--noproxy",
        ",".join(sorted(set(hosts))), "--silent", "--show-error", "--connect-timeout", "2",
        "--max-time", "4", "--write-out", "PT132STATUS:%{http_code}", *args,
    ]


def origin(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname is None or parsed.username
            or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or not re.fullmatch(r"localhost|[0-9.]+", parsed.hostname)):
        raise ValueError("Explicit local HTTPS origin required")
    if parsed.hostname != "localhost":
        address = ipaddress.IPv4Address(parsed.hostname)
        if not address.is_private or address.is_unspecified or address.is_multicast:
            raise ValueError("Local IPv4 origin required")
    return parsed.hostname, parsed.port or 443


def adb_run(adb: str, serial: str, arguments: list[str], stdin=None):
    command = [adb, "-s", serial, *arguments]
    result = subprocess.run(
        command, input=stdin.encode() if stdin is not None else None,
        capture_output=True, timeout=15,
    )
    # Decode bytes without universal-newline conversion; hashes must describe
    # the actual UTF-8 subprocess streams on Windows as well as Linux.
    return subprocess.CompletedProcess(
        command, result.returncode, result.stdout.decode(), result.stderr.decode(),
    )


def write_receipt(path: Path, value: dict) -> str:
    data = (json.dumps(value, indent=2) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(data)
    actual = path.read_bytes()
    if actual != data:
        raise OSError("Receipt readback mismatch")
    return hashlib.sha256(actual).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_bytes())
    adb = os.environ.get(config["adb_env"], "")
    serial = os.environ.get(config["serial_env"], "")
    instances = config["instances"]
    probes = config["mtls_probes"]
    if (config.get("disposable") is not True or not adb or not serial
            or set(instances) != {"I", "J"} or len(probes) != 4
            or {p["alias"] for p in probes} != {"I-gateway", "J-gateway", "I-runner", "J-runner"}):
        parser.error("Explicit owned device, two disposable instances and four probes required")
    hosts = ["localhost", "127.0.0.1"]
    for item in instances.values():
        hosts.append(origin(item["origin"])[0])
    for item in probes:
        hosts.append(origin(item["origin"])[0])
        if item["connect_host"] != "127.0.0.1" or not 1 <= item["connect_port"] <= 65535:
            parser.error("Management probe requires a caller-owned loopback tunnel")
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    checks, private = [], {"probes": []}
    receipt = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "record_kind": "ANDROID_NETWORK_SUBSET", "scenario_status": "NOT_RUN",
        "scope": "Installed app UID on configured local Android/ADB-reverse network. Four "
                 "operator-only mTLS probe tunnels are separate from ordinary port exposure.",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[3], text=True,
        ).strip(),
        "source_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=Path(__file__).resolve().parents[3], text=True,
        ).strip()),
        "checks": checks, "error": None,
        "cleanup": "CALLER_OWNS_PUBLIC_CA_FILES_REVERSES_AND_TEMPORARY_TUNNELS",
    }

    def run(arguments, stdin=None):
        return adb_run(adb, serial, arguments, stdin)

    def probe(name, kind, arguments, expected, predicate, stdin=None):
        result = run(curl_arguments(hosts, arguments), stdin)
        status, _ = observation(result)
        passed = predicate(result)
        private["probes"].append({
            "name": name, "stdout": result.stdout, "stderr": result.stderr,
            "exit": result.returncode,
        })
        checks.append({
            "name": name, "kind": kind, "expected": expected,
            "actual_http": status, "curl_exit": result.returncode, "passed": passed,
            "stdout_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        })
        if not passed:
            raise ValueError("Probe rejected")

    try:
        identity = run(["shell", "run-as", PACKAGE, "id"])
        uid = re.search(r"\buid=(\d+)\b", identity.stdout)
        if identity.returncode != 0 or uid is None or int(uid.group(1)) < 10000:
            raise ValueError("Installed app UID precondition failed")
        private["uid"] = identity.stdout
        receipt["installed_nonroot_app_uid"] = True
        for label, item in instances.items():
            ca = f"/data/local/tmp/pt132-network-{label}-ca.pem"
            if run(["push", str(Path(item["ca_file"]).resolve()), ca]).returncode != 0:
                raise ValueError("Public CA transfer failed")
            token = os.environ[item["token_env"]]
            if not re.fullmatch(r"pt_cap_[A-Za-z0-9_-]{20,}", token):
                raise ValueError("Own task capability required")
            routes = [
                ("GET", "/api/v1/health", 200, None),
                ("GET", "/api/v1/mobile-capabilities", 200, None),
                ("GET", "/_health/live", 404, None),
                ("GET", "/_health/ready", 404, None),
                ("GET", "/api/v1/web/settings", 403,
                 {"detail": "Admin settings forbidden in remote mode"}),
                ("POST", "/api/v1/web/settings", 403,
                 {"detail": "Admin settings forbidden in remote mode"}),
                ("GET", "/api/v1/jobs", 403,
                 {"detail": "Jobs listing forbidden in remote mode"}),
            ]
            for method, route, code, body in routes:
                for authenticated in ([False, True] if code == 403 else [False]):
                    arguments = ["--cacert", ca, "--request", method]
                    stdin = None
                    if authenticated:
                        arguments += ["--config", "-"]
                        stdin = "header = " + json.dumps("Authorization: Bearer " + token) + "\n"
                    if method == "POST":
                        arguments += ["--data-binary", "{}", "--header",
                                      "Content-Type:application/json"]
                    arguments.append(item["origin"].rstrip("/") + route)

                    def valid(result, code=code, body=body, route=route, item=item):
                        if not http_passed(result, code, body):
                            return False
                        if route not in {"/api/v1/health", "/api/v1/mobile-capabilities"}:
                            return True
                        value = json.loads(observation(result)[1])
                        if not isinstance(value, dict):
                            return False
                        if route == "/api/v1/health":
                            return value.get("status") == "ok"
                        return (value.get("supported") is True
                                and value.get("instance_id") == item["instance_id"])

                    name = f"{label} {method} {route} "
                    name += "own-task" if authenticated else "absent"
                    probe(name, "public-entry", arguments, code, valid, stdin)
        for name, port in [("api", 8000), ("postgres", 5432), ("broker", 6379),
                           ("runner", 8444), ("gateway", 8443),
                           ("daemon-http", 2375), ("daemon-tls", 2376)]:
            probe(name, "ordinary-network", [f"http://127.0.0.1:{port}/"],
                  "connection refused", lambda result: result.returncode == 7
                  and observation(result) == (0, ""))
        for item in probes:
            host, port = origin(item["origin"])
            ca = f"/data/local/tmp/pt132-network-{item['alias'][0]}-ca.pem"
            arguments = ["--cacert", ca, "--connect-to",
                         f"{host}:{port}:{item['connect_host']}:{item['connect_port']}",
                         item["origin"].rstrip("/") + "/v1/health"]
            probe(item["alias"], "operator-only-probe-tunnel", arguments,
                  "client certificate required; no management response", mtls_passed)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        receipt["error"] = type(error).__name__
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    receipt["subset_status"] = (
        "PASSED" if receipt["error"] is None and len(checks) == 31
        and all(item["passed"] for item in checks) else "FAILED"
    )
    write_receipt(args.output_dir / "private-responses.json", private)
    sha = write_receipt(args.output_dir / "receipt.json", receipt)
    print(json.dumps({"subset_status": receipt["subset_status"], "checks": len(checks),
                      "receipt_sha256": sha}))
    return 0 if receipt["subset_status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
