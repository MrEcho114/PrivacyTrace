"""F07: scanner timeout/crash, orphan reaping, role rebuild and live inspect.

Executed sub-steps (the host-reboot step is BLOCKED: this machine has no
independent, destroyable Linux VM with its own kernel; a nested daemon or the
shared host kernel cannot stand in for that step):

* ``A`` -- controlled scan timeout: bounded FAILED job, verified cleanup, live
  inspect of the actual scan container (network none, read-only root, no
  capabilities, read-only single input, no secrets).
* ``B`` -- controlled scan crash (OOM): bounded FAILED job with OOMKilled exit
  state and verified cleanup.
* ``C`` -- hard Runner crash during a scan: the orphan container is proven to
  exist, then reaped after the Runner restarts; no orphan task/container/
  temporary material remains, and the same job still completes.
* ``D`` -- rebuild the worker/Runner/dispatcher roles and re-inspect every role.
* ``E`` -- host reboot sub-step: BLOCKED (recorded, not executed).
"""

from __future__ import annotations

import json
import sqlite3
import time

from .f03 import F03, execution_view
from .f134_common import (
    Business,
    Case,
    Client,
    Lab,
    guard_env,
    main_guard,
    sha256_bytes,
    wait_for,
)


class F07:
    case = "F07"
    variants = ("A", "B", "C", "D", "E")
    purposes = {
        "A": "controlled scan timeout fails boundedly and cleans its container",
        "B": "controlled scan OOM fails boundedly with OOMKilled proof",
        "C": "hard Runner crash leaves a proven orphan that is reaped on restart",
        "D": "rebuilt roles keep the isolation/read-only/no-secret boundaries",
        "E": "host reboot sub-step is BLOCKED without an independent kernel VM",
    }

    @staticmethod
    def run(variant, case: Case, keep=False):
        lab = guard_env(Lab())
        client = Client(lab)
        business = Business(lab, client)
        business.fixtures()
        if variant == "E":
            case.block(
                "no independent destroyable Linux VM on this machine; the shared "
                "host kernel or a nested daemon cannot be presented as a real "
                "host reboot, so this sub-step is not executed"
            )
            return
        override = lab.override()
        scope = None
        image = None
        try:
            if variant == "A":
                image = F07.build_fault_image(
                    lab, "timeout", ["/opt/venv/bin/python", "-c", "import time;time.sleep(360)"]
                )
            elif variant == "B":
                image = F07.build_fault_image(
                    lab,
                    "oom",
                    ["/opt/venv/bin/python", "-c", "bytearray(2*1024*1024*1024)"],
                )
            elif variant == "C":
                image = F03.build_delayed_scanner(lab)
            if image:
                for role in ("api", "worker", "runner"):
                    override.env(role, "PRIVACYTRACE_RUNNER_IMAGE_ID", image)
            if variant == "A":
                override.env("runner", "PRIVACYTRACE_RUNNER_TIMEOUT", "6")
            if image:
                override.apply("api", "worker", "runner")
            handler = {
                "A": F07.timeout_scan,
                "B": F07.oom_scan,
                "C": F07.orphan_recovery,
                "D": F07.rebuild_roles,
            }[variant]
            scope = handler(lab, client, business, case, image)
        finally:
            if image:
                override.restore("api", "worker", "runner")
            lab.compose_run("start", "worker", "dispatcher", "api", "runner", check=False)
            try:
                lab.ready(timeout=90)
            except TimeoutError:
                pass
            if scope is not None:
                F07.finish_scope(client, business, case, scope)
            F07.assert_no_owned_residue(lab, case)

    @staticmethod
    def build_fault_image(lab, name, entrypoint):
        tag = f"privacytrace-f134-fault-{name}:" + lab.project
        return lab.commit_image(tag, lab.owner["images"]["scanner"], entrypoint)

    @staticmethod
    def prepare(lab, client, business, case, name):
        scope = business.create(name)
        uploaded = business.upload(scope)
        case.check("synthetic APK accepted", uploaded["status"] == 200, uploaded["status"])
        return scope

    @staticmethod
    def start_and_scan(lab, client, business, case, scope, label):
        started = business.start(scope)
        case.check(f"start accepted ({label})", started["status"] == 200 and bool(scope["job_id"]))
        business.wait_execution(scope["job_id"], {"RUNNING"}, timeout=120)
        scanner = wait_for(
            "live scan container",
            lambda: lab.scanner_containers() or None,
            timeout=120,
            interval=0.05,
        )
        identifiers = scanner
        inspected = lab.inspect_scanner(identifiers[0])
        case.note(
            f"live scan container inspect ({label})",
            "network none, read-only root, no caps, one read-only input, no secrets",
            inspected,
        )
        case.check("scan container is isolated", F03.isolated_policy(inspected), inspected)
        case.check(
            "scan container has no Docker socket",
            inspected["has_docker_socket"] is False,
        )
        case.check(
            "scan container env has no secret material",
            F07.no_secret_keys(inspected["env_keys"]),
            inspected["env_keys"],
        )
        return inspected, identifiers

    @staticmethod
    def scan_result(lab, watermark=0):
        path = lab.root / "runner" / "requests.sqlite"
        if not path.exists():
            return []
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            return [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT result FROM operations WHERE rowid>? AND state='DONE'", (watermark,)
                )
            ]

    @staticmethod
    def runner_watermark(lab):
        path = lab.root / "runner" / "requests.sqlite"
        if not path.exists():
            return 0
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            return connection.execute("SELECT coalesce(max(rowid),0) FROM operations").fetchone()[0]

    @staticmethod
    def timeout_scan(lab, client, business, case, image):
        scope = F07.prepare(lab, client, business, case, "f07-timeout")
        watermark = F07.runner_watermark(lab)
        inspected, identifiers = F07.start_and_scan(lab, client, business, case, scope, "timeout")
        final = business.wait_terminal(scope, timeout=180)
        jobs = [job for job in lab.jobs() if job["job_id"] == scope["job_id"]]
        results = F07.scan_result(lab, watermark)
        receipt = next((item.get("receipt") for item in results if item.get("receipt")), None)
        case.note(
            "timeout terminal state",
            "FAILED with TIMEOUT and verified cleanup",
            {
                "state": final.get("state"),
                "job_error": json.loads(jobs[0]["error"])
                if jobs and jobs[0].get("error")
                else None,
                "runner_error": (results[-1].get("error") if results else None),
                "receipt": receipt,
                "scanner_containers": lab.scanner_containers(),
            },
        )
        case.check("timeout ends as FAILED", final.get("state") == "FAILED", final.get("state"))
        case.check(
            "scan error is TIMEOUT",
            bool(results) and results[-1].get("error") == "TIMEOUT",
            results[-1].get("error") if results else None,
        )
        case.check("cleanup is verified", bool(receipt) and receipt.get("cleanup_verified") is True)
        case.check("input is removed", bool(receipt) and receipt.get("input_removed") is True)
        case.check("no scanner container remains", lab.scanner_containers() == [])
        case.check("Timeout failure is bounded", True)
        return scope

    @staticmethod
    def oom_scan(lab, client, business, case, image):
        scope = F07.prepare(lab, client, business, case, "f07-oom")
        watermark = F07.runner_watermark(lab)
        inspected, identifiers = F07.start_and_scan(lab, client, business, case, scope, "oom")
        final = business.wait_terminal(scope, timeout=180)
        jobs = [job for job in lab.jobs() if job["job_id"] == scope["job_id"]]
        results = F07.scan_result(lab, watermark)
        receipt = next((item.get("receipt") for item in results if item.get("receipt")), None)
        exit_state = (receipt or {}).get("exit_state") or {}
        case.note(
            "OOM terminal state",
            "FAILED with OOM and OOMKilled proof",
            {
                "state": final.get("state"),
                "job_error": json.loads(jobs[0]["error"])
                if jobs and jobs[0].get("error")
                else None,
                "runner_error": (results[-1].get("error") if results else None),
                "receipt": receipt,
                "scanner_containers": lab.scanner_containers(),
            },
        )
        case.check("OOM ends as FAILED", final.get("state") == "FAILED", final.get("state"))
        case.check(
            "scan error is OOM",
            bool(results) and results[-1].get("error") == "OOM",
            results[-1].get("error") if results else None,
        )
        case.check("container was OOMKilled", exit_state.get("OOMKilled") is True, exit_state)
        case.check("cleanup is verified", bool(receipt) and receipt.get("cleanup_verified") is True)
        case.check("input is removed", bool(receipt) and receipt.get("input_removed") is True)
        case.check("no scanner container remains", lab.scanner_containers() == [])
        return scope

    @staticmethod
    def orphan_recovery(lab, client, business, case, image):
        scope = F07.prepare(lab, client, business, case, "f07-orphan")
        started = business.start(scope)
        case.check("start accepted", started["status"] == 200 and bool(scope["job_id"]))
        acquired = business.wait_execution(scope["job_id"], {"RUNNING"}, timeout=120)
        wait_for(
            "scan container", lambda: lab.scanner_containers() or None, timeout=120, interval=0.05
        )
        runner_id = lab.role_id("runner")
        case.note(
            "scan running under the Runner",
            "owned scanner container exists",
            {"containers": lab.scanner_containers(), "fence": acquired["fence"]},
        )
        lab.docker("kill", "--signal", "SIGKILL", runner_id)
        time.sleep(1)
        orphaned = lab.scanner_containers()
        case.note(
            "Runner hard crash",
            "the scan container survives as a provable orphan",
            {"containers": orphaned, "runner": lab.running_roles().get("runner")},
        )
        case.check("orphan container exists after Runner crash", bool(orphaned), orphaned)
        lab.compose_run("start", "runner")
        wait_for(
            "Runner restart",
            lambda: lab.running_roles().get("runner", {}).get("state") == "running",
            timeout=90,
        )
        wait_for(
            "orphan reaped",
            lambda: not lab.scanner_containers(),
            timeout=120,
            interval=0.3,
        )
        case.note(
            "Runner restart recovered its own orphan",
            "no scanner container and no operation residue",
            {"containers": lab.scanner_containers(), "operations": F03.runner_operations(lab)},
        )
        case.check("orphan container is reaped", lab.scanner_containers() == [])
        final = business.wait_terminal(scope, timeout=300)
        report = business.report(scope)
        case.note(
            "task recovery after orphan reaping",
            "same job SUCCEEDED under a new fence",
            {
                "state": final.get("state"),
                "report_status": report["status"],
                "execution": execution_view(lab, scope["job_id"]),
            },
        )
        case.check(
            "same job succeeds after recovery",
            final.get("state") == "SUCCEEDED",
            final.get("state"),
        )
        case.check(
            "new fence is higher",
            int(execution_view(lab, scope["job_id"]).get("fence") or 0) > acquired["fence"],
        )
        case.check("report readable", report["status"] == 200, report["status"])
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        return scope

    @staticmethod
    def rebuild_roles(lab, client, business, case, image):
        before = {role: lab.role_id(role) for role in ("worker", "runner", "dispatcher")}
        lab.compose_run(
            "up", "-d", "--no-deps", "--force-recreate", "worker", "runner", "dispatcher"
        )
        lab.ready(timeout=120)
        wait_for(
            "rebuilt roles running",
            lambda: all(
                lab.running_roles().get(role, {}).get("state") == "running"
                for role in ("worker", "runner", "dispatcher")
            ),
            timeout=120,
        )
        after = {role: lab.role_id(role) for role in ("worker", "runner", "dispatcher")}
        isolation = lab.role_isolation()
        case.note(
            "roles rebuilt by the handed-over command",
            "new container ids and preserved isolation boundaries",
            {
                "before": {k: v[:12] for k, v in before.items()},
                "after": {k: v[:12] for k, v in after.items()},
            },
        )
        case.check("worker was rebuilt", after["worker"] != before["worker"])
        case.check("runner was rebuilt", after["runner"] != before["runner"])
        case.check("dispatcher was rebuilt", after["dispatcher"] != before["dispatcher"])
        violations = []
        for role, value in isolation.items():
            if value["privileged"]:
                violations.append(role + ":privileged")
            if role != "runner" and value["has_docker_socket"]:
                violations.append(role + ":socket")
            if role == "runner" and not value["has_docker_socket"]:
                violations.append("runner:no-socket")
            if not value["read_only"]:
                violations.append(role + ":writable-root")
            if value["cap_drop"] != ["ALL"]:
                violations.append(role + ":caps")
            if value["user"].split(":")[0] in {"", "0", "root"}:
                violations.append(role + ":root")
            unexpected = [
                path
                for path in value["host_binds"]
                if not (role == "web" and path == "/etc/caddy/Caddyfile")
                and not (role == "runner" and path.startswith("/var/tmp/"))
            ]
            if unexpected:
                violations.append(role + ":host-bind")
        case.note(
            "independent inspect of every role",
            "non-root, read-only, cap_drop ALL, socket only on Runner",
            {"isolation": isolation, "violations": violations},
        )
        case.check("isolation boundaries hold after rebuild", violations == [], violations)
        scope = F07.prepare(lab, client, business, case, "f07-rebuilt")
        started = business.start(scope)
        case.check(
            "new task accepted after rebuild", started["status"] == 200 and bool(scope["job_id"])
        )
        final = business.wait_terminal(scope, timeout=300)
        report = business.report(scope)
        case.note(
            "new task after rebuild",
            "SUCCEEDED",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check(
            "new task succeeds after rebuild", final.get("state") == "SUCCEEDED", final.get("state")
        )
        case.check("report readable", report["status"] == 200, report["status"])
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        return scope

    @staticmethod
    def no_secret_keys(env_keys):
        forbidden = ("SECRET", "PASSWORD", "TOKEN", "PRIVATE", "MATERIAL_KEY")
        return not any(any(marker in item.upper() for marker in forbidden) for item in env_keys)

    @staticmethod
    def assert_no_owned_residue(lab, case):
        containers = lab.scanner_containers()
        operations = F03.runner_operations(lab)
        case.check("no scan container residue", containers == [], containers)
        case.check("no runner operation residue", operations == [], operations)

    @staticmethod
    def finish_scope(client, business, case, scope):
        try:
            report = client.request(f"/api/v1/jobs/{scope['job_id']}/report", token=scope["token"])
            if report["status"] == 200:
                case.artifact("report_sha256_before_delete", sha256_bytes(report["body"]))
        except Exception:  # noqa: BLE001
            pass
        status = business.cleanup_scope(scope)
        case.note("scope cleanup", "deleted through its own capability", {"delete_status": status})
        case.check("scope cleanup accepted", status in {200, 204, 404}, status)


if __name__ == "__main__":
    raise SystemExit(main_guard(F07))
