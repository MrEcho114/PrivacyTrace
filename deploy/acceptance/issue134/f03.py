"""F03: worker and Runner interruption around the PostgreSQL lease boundary.

Variants:

* ``A`` -- worker interrupted after acquiring, restored *before* the lease
  expires; the attempt is not stolen early and recovery increments fence/attempt.
* ``B`` -- worker interrupted after acquiring, restored *after* the lease
  expires; the dispatcher re-arms the same event with a higher fence.
* ``C`` -- Runner interrupted after accepting the scan; material/RPC failure is
  retried, the old scan workspace is reaped on restart, and the same job
  completes under a new fencing token.
* ``D`` -- an old execution is frozen past its lease while a second worker
  completes the job; releasing the old worker must not commit a second result.

Lease duration is shortened only through the laboratory's own Compose override
and reverted afterwards. No product source is modified.
"""

from __future__ import annotations

import re
import time

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


def execution_view(lab, job_id):
    rows = lab.db(
        "SELECT json_build_object("
        "'state',state,'fence',fence,'attempt',attempt,"
        "'owner',owner,'last_error_code',last_error_code,"
        "'remaining_s',round(extract(epoch from (leased_until - clock_timestamp()))::numeric,2),"
        "'result_sha256',result_sha256)"
        " FROM privacytrace.job_executions WHERE instance_id="
        f"'{lab.instance}' AND job_id='{job_id}'"
    )
    return rows[0] if rows else {}


class F03:
    case = "F03"
    variants = ("A", "B", "C", "D")
    purposes = {
        "A": "worker interrupted after acquisition, restored before lease expiry",
        "B": "worker interrupted after acquisition, restored after lease expiry",
        "C": "Runner interrupted after accepting the scan; workspace reaped and retried",
        "D": "stale fencing token cannot commit after a new attempt completed",
    }

    @staticmethod
    def run(variant, case: Case, keep=False):
        lab = guard_env(Lab())
        client = Client(lab)
        business = Business(lab, client)
        business.fixtures()
        override = lab.override()
        scope = None
        image = None
        try:
            image = F03.build_delayed_scanner(lab)
            if variant in {"A", "B", "D"}:
                override.env("worker", "PRIVACYTRACE_LEASE_SECONDS", "5")
            for role in ("api", "worker", "runner"):
                override.env(role, "PRIVACYTRACE_RUNNER_IMAGE_ID", image)
            override.apply("api", "worker", "runner")
            handler = {
                "A": F03.worker_before_expiry,
                "B": F03.worker_after_expiry,
                "C": F03.runner_interrupted,
                "D": F03.stale_token,
            }[variant]
            scope = handler(lab, client, business, case, override, image)
        finally:
            F03.restore(lab, override)
            if scope is not None:
                F03.finish_scope(client, business, case, scope)

    @staticmethod
    def restore(lab, override):
        lab.remove_second_worker("f134-worker-2-" + lab.project[-6:])
        try:
            override.restore("api", "worker", "runner")
        except Exception:  # noqa: BLE001 - best-effort recovery
            pass
        lab.compose_run("start", "worker", "dispatcher", "api", check=False)
        try:
            lab.ready(timeout=90)
        except TimeoutError:
            pass

    @staticmethod
    def build_delayed_scanner(lab, delay=6):
        tag = "privacytrace-f134-delay:" + lab.project
        entrypoint = [
            "/opt/venv/bin/python",
            "-c",
            f"import time,runpy;time.sleep({delay});"
            "runpy.run_module('privacytrace.apk_worker',run_name='__main__')",
        ]
        return lab.commit_image(tag, lab.owner["images"]["scanner"], entrypoint)

    @staticmethod
    def prepare(lab, client, business, case, name):
        scope = business.create(name)
        uploaded = business.upload(scope)
        case.check("synthetic APK accepted", uploaded["status"] == 200, uploaded["status"])
        return scope

    @staticmethod
    def start_and_acquire(lab, client, business, case, scope, label):
        started = business.start(scope)
        case.check(f"start accepted ({label})", started["status"] == 200 and bool(scope["job_id"]))
        acquired = business.wait_execution(scope["job_id"], {"RUNNING"}, timeout=120)
        case.note(
            f"execution acquired ({label})",
            "RUNNING with fence=1 attempt=1",
            {
                "fence": acquired["fence"],
                "attempt": acquired["attempt"],
                "owner_alias": str(acquired["owner"])[:8],
                "leased_until": acquired["leased_until"],
            },
        )
        case.check("lease acquired", acquired["state"] == "RUNNING", acquired["state"])
        return acquired

    @staticmethod
    def worker_before_expiry(lab, client, business, case, override, image):
        scope = F03.prepare(lab, client, business, case, "f03-worker-before")
        acquired = F03.start_and_acquire(lab, client, business, case, scope, "before expiry")
        old_owner = str(acquired["owner"])
        # SIGKILL is the interruption: a graceful stop lets the solo worker
        # finish its current task, which would not exercise lease recovery.
        lab.kill("worker")
        stopped = execution_view(lab, scope["job_id"])
        case.note(
            "worker killed after acquisition",
            "lease still live, job not failed",
            {"remaining_s": stopped.get("remaining_s"), "job_state": F03.job_state(lab, scope)},
        )
        case.check(
            "job is not failed by the worker interruption",
            F03.job_state(lab, scope)
            in {"QUEUED", "INTAKE", "STATIC_ANALYSIS", "POLICY_PARSING", "EVALUATING", "REPORTING"},
            F03.job_state(lab, scope),
        )
        lab.start("worker")
        early = execution_view(lab, scope["job_id"])
        case.note(
            "worker restarted before lease expiry",
            "old attempt is not stolen; no duplicate RUNNING owner",
            {
                "state": early.get("state"),
                "fence": early.get("fence"),
                "attempt": early.get("attempt"),
                "remaining_s": early.get("remaining_s"),
            },
        )
        case.check(
            "no second execution while the lease is live",
            early.get("fence") == acquired["fence"] and early.get("attempt") == acquired["attempt"],
            {"fence": early.get("fence"), "attempt": early.get("attempt")},
        )
        recovered = wait_for(
            "lease expiry recovery",
            lambda: (
                execution_view(lab, scope["job_id"])
                if execution_view(lab, scope["job_id"]).get("fence") > acquired["fence"]
                else None
            ),
            timeout=120,
            interval=0.3,
        )
        case.note(
            "recovery after expiry",
            "fence and attempt advance for the same job",
            {
                "state": recovered.get("state"),
                "fence": recovered.get("fence"),
                "attempt": recovered.get("attempt"),
            },
        )
        case.check("fence advanced after lease expiry", recovered["fence"] > acquired["fence"])
        case.check("old owner is gone", str(recovered.get("owner")) != old_owner)
        final = business.wait_terminal(scope, timeout=240)
        report = business.report(scope)
        case.note(
            "terminal state",
            "SUCCEEDED with one report",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check("recovered job succeeds", final.get("state") == "SUCCEEDED", final.get("state"))
        case.check("report readable", report["status"] == 200, report["status"])
        F03.assert_single_report(lab, case, scope, report)
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        return scope

    @staticmethod
    def worker_after_expiry(lab, client, business, case, override, image):
        scope = F03.prepare(lab, client, business, case, "f03-worker-after")
        acquired = F03.start_and_acquire(lab, client, business, case, scope, "before expiry")
        lab.kill("worker")
        time.sleep(8)
        rearmed = wait_for(
            "dispatcher re-arms the expired attempt",
            lambda: (
                execution_view(lab, scope["job_id"])
                if execution_view(lab, scope["job_id"]).get("fence") > acquired["fence"]
                or execution_view(lab, scope["job_id"]).get("state") in {"RETRY", "READY"}
                else None
            ),
            timeout=120,
            interval=0.3,
        )
        case.note(
            "worker stopped past the lease",
            "execution re-armed with a higher fence while no worker runs",
            {
                "state": rearmed.get("state"),
                "fence": rearmed.get("fence"),
                "attempt": rearmed.get("attempt"),
            },
        )
        case.check("execution was re-armed after expiry", rearmed["fence"] > acquired["fence"])
        case.check(
            "old owner revoked before restart",
            str(rearmed.get("owner") or "") != str(acquired["owner"]),
        )
        lab.start("worker")
        final = business.wait_terminal(scope, timeout=240)
        report = business.report(scope)
        final_execution = execution_view(lab, scope["job_id"])
        case.note(
            "terminal state after delayed restart",
            "SUCCEEDED, attempt 2, single report",
            {
                "state": final.get("state"),
                "attempt": final_execution.get("attempt"),
                "fence": final_execution.get("fence"),
                "report_status": report["status"],
            },
        )
        case.check(
            "job succeeds after delayed restart",
            final.get("state") == "SUCCEEDED",
            final.get("state"),
        )
        case.check(
            "attempt count advanced",
            int(final_execution.get("attempt") or 0) >= 2,
            final_execution.get("attempt"),
        )
        F03.assert_single_report(lab, case, scope, report)
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        return scope

    @staticmethod
    def runner_interrupted(lab, client, business, case, override, image):
        scope = F03.prepare(lab, client, business, case, "f03-runner")
        started = business.start(scope)
        case.check("start accepted", started["status"] == 200 and bool(scope["job_id"]))
        acquired = business.wait_execution(scope["job_id"], {"RUNNING"}, timeout=120)
        scanner = wait_for(
            "real scanner container",
            lambda: lab.scanner_containers() or None,
            timeout=120,
            interval=0.1,
        )
        identifier = scanner[0]
        inspected = lab.inspect_scanner(identifier)
        case.note(
            "Runner accepted the scan",
            "owned scan container exists with isolated policy",
            {"scanner": inspected, "fence": acquired["fence"], "attempt": acquired["attempt"]},
        )
        case.check("scan container is isolated", F03.isolated_policy(inspected), inspected)
        case.check("scan container has no docker socket", inspected["has_docker_socket"] is False)
        old_fence = acquired["fence"]
        lab.stop("runner")
        case.note(
            "Runner stopped during scan",
            "worker sees a bounded runner failure",
            {"state": lab.running_roles().get("runner")},
        )
        retried = wait_for(
            "worker retry after runner loss",
            lambda: (
                execution_view(lab, scope["job_id"])
                if execution_view(lab, scope["job_id"]).get("state") in {"RETRY", "READY"}
                or execution_view(lab, scope["job_id"]).get("fence") > old_fence
                else None
            ),
            timeout=120,
            interval=0.3,
        )
        case.note(
            "execution retried",
            "same job re-armed, fence advanced",
            {
                "state": retried.get("state"),
                "fence": retried.get("fence"),
                "attempt": retried.get("attempt"),
            },
        )
        case.check(
            "same job was retried not failed",
            retried.get("state") in {"RETRY", "READY"} or retried.get("fence") > old_fence,
            retried.get("state"),
        )
        lab.start("runner")
        wait_for(
            "orphan scanner reaped on Runner restart",
            lambda: not lab.scanner_containers(),
            timeout=90,
            interval=0.3,
        )
        case.note(
            "Runner restarted",
            "orphan scan container removed",
            {"scanner_containers": lab.scanner_containers()},
        )
        case.check("no orphan scanner remains", lab.scanner_containers() == [])
        case.check(
            "runner workspace reaped",
            F03.runner_operations(lab) == [],
            F03.runner_operations(lab),
        )
        final = business.wait_terminal(scope, timeout=300)
        report = business.report(scope)
        final_execution = execution_view(lab, scope["job_id"])
        case.note(
            "terminal state after Runner restart",
            "SUCCEEDED under a new fence",
            {
                "state": final.get("state"),
                "fence": final_execution.get("fence"),
                "attempt": final_execution.get("attempt"),
                "report_status": report["status"],
            },
        )
        case.check(
            "job succeeds after Runner restart",
            final.get("state") == "SUCCEEDED",
            final.get("state"),
        )
        case.check(
            "new fence is higher",
            int(final_execution.get("fence") or 0) > old_fence,
            final_execution.get("fence"),
        )
        F03.assert_single_report(lab, case, scope, report)
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        return scope

    @staticmethod
    def stale_token(lab, client, business, case, override, image):
        scope = F03.prepare(lab, client, business, case, "f03-stale-token")
        started = business.start(scope)
        case.check("start accepted", started["status"] == 200 and bool(scope["job_id"]))
        acquired = business.wait_execution(scope["job_id"], {"RUNNING"}, timeout=120)
        old_owner = str(acquired["owner"])
        old_worker = lab.role_id("worker")
        case.note(
            "old execution acquired",
            "RUNNING fence=1 attempt=1",
            {
                "fence": acquired["fence"],
                "attempt": acquired["attempt"],
                "owner_alias": old_owner[:8],
            },
        )
        lab.docker("pause", old_worker)
        rearmed = wait_for(
            "lease expiry re-arms the event",
            lambda: (
                execution_view(lab, scope["job_id"])
                if execution_view(lab, scope["job_id"]).get("fence") > acquired["fence"]
                else None
            ),
            timeout=120,
            interval=0.3,
        )
        case.note(
            "old execution frozen past its lease",
            "event re-armed while the old owner is frozen",
            {
                "state": rearmed.get("state"),
                "fence": rearmed.get("fence"),
                "attempt": rearmed.get("attempt"),
                "last_error_code": rearmed.get("last_error_code"),
            },
        )
        case.check(
            "lease expiry is visible as LEASE_EXPIRED in the execution row",
            rearmed.get("last_error_code") == "LEASE_EXPIRED",
            rearmed.get("last_error_code"),
        )
        audit_actions = [item["action"] for item in lab.audit(scope["job_id"])]
        case.check(
            "re-arm is recorded in the audit ledger",
            "EXECUTION_RETRY" in audit_actions,
            audit_actions,
        )
        second = lab.run_second_worker()
        wait_for("second worker running", lambda: lab.second_worker_running(second), timeout=90)
        final = business.wait_terminal(scope, timeout=300)
        report = business.report(scope)
        new_execution = execution_view(lab, scope["job_id"])
        case.note(
            "new attempt completed while the old owner is frozen",
            "SUCCEEDED by the second worker",
            {
                "state": final.get("state"),
                "fence": new_execution.get("fence"),
                "attempt": new_execution.get("attempt"),
                "report_status": report["status"],
            },
        )
        case.check(
            "new attempt commits the only success",
            final.get("state") == "SUCCEEDED",
            final.get("state"),
        )
        case.check(
            "fence advanced beyond the old owner",
            int(new_execution.get("fence") or 0) > acquired["fence"],
        )
        report_sha = sha256_bytes(report["body"])
        lab.docker("unpause", old_worker)
        time.sleep(18)
        after = business.report(scope)
        final_execution = execution_view(lab, scope["job_id"])
        logs = lab.docker("logs", "--tail", "6000", old_worker, check=False)
        raw = (logs.stdout or "") + (logs.stderr or "")
        codes = sorted(set(re.findall(r"privacytrace\.worker\.([A-Z_]+)", raw)))
        case.note(
            "old owner released after the new attempt finished",
            "old fenced commit rejected; report unchanged",
            {
                "report_status": after["status"],
                "report_sha_unchanged": after["status"] == 200
                and sha256_bytes(after["body"]) == report_sha,
                "executions": lab.executions(scope["job_id"]),
                "diagnostics": codes,
            },
        )
        case.check(
            "old owner cannot commit a second result",
            after["status"] == 200 and sha256_bytes(after["body"]) == report_sha,
        )
        # The product has no persistent "lease lost" event: the loss is proven
        # by the RETRY/LEASE_EXPIRED re-arm and by the stale commit being
        # rejected. Keep the diagnostic-code probe as a non-blocking extra.
        case.probe(
            "worker logged an explicit lease-lost diagnostic",
            "LEASE_LOST" in codes or "RUNNER_UNAVAILABLE" in codes,
            codes,
        )
        case.check("no second execution row", len(lab.executions(scope["job_id"])) == 1)
        case.check("final state remains SUCCEEDED", final_execution.get("state") == "SUCCEEDED")
        case.artifact("report_sha256", report_sha)
        lab.remove_second_worker(second)
        return scope

    @staticmethod
    def job_state(lab, scope):
        rows = lab.db(
            "SELECT json_build_object('state', record->'job'->>'state') "
            "FROM privacytrace.jobs "
            f"WHERE instance_id='{lab.instance}' AND job_id='{scope['job_id']}'"
        )
        return rows[0]["state"] if rows else "UNKNOWN"

    @staticmethod
    def runner_operations(lab):
        root = lab.root / "runner" / "operations"
        return sorted(item.name for item in root.iterdir()) if root.exists() else []

    @staticmethod
    def isolated_policy(inspected):
        return (
            inspected["network_mode"] == "none"
            and inspected["read_only"] is True
            and inspected["privileged"] is False
            and "ALL" in [item.upper() for item in inspected["cap_drop"]]
            and not inspected["cap_add"]
            and inspected["user"] == "65534:65534"
            and inspected["pids_limit"] == 32
            and inspected["memory"] == 1024 * 1024 * 1024
            and all(item["read_only"] for item in inspected["mounts"])
            and [item["destination"] for item in inspected["mounts"]] == ["/input/sample.apk"]
        )

    @staticmethod
    def assert_single_report(lab, case, scope, report):
        executions = lab.executions(scope["job_id"])
        jobs = [job for job in lab.jobs() if job["job_id"] == scope["job_id"]]
        case.check("exactly one execution row", len(executions) == 1, len(executions))
        case.check(
            "job has exactly one bundle", len(jobs) == 1 and jobs[0]["has_bundle"] is True, jobs
        )
        case.check(
            "successful execution records the report digest",
            bool(executions[0].get("result_sha256")),
            executions[0].get("result_sha256"),
        )

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
    raise SystemExit(main_guard(F03))
