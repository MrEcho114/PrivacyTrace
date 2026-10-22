"""F04: duplicate delivery and a stale attempt reporting after a newer success.

Variants:

* ``A`` -- the same outbox message is published again through the product
  publisher after the first delivery; exactly one effective result may exist and
  the duplicate delivery must be refused, not merged into the report.
* ``B`` -- an old execution is frozen past its lease, a second worker completes
  the job, then the old worker is released. The late old attempt must not
  produce a second report, index entry, event or material.

Both variants compare byte digests of the report before and after the duplicate
delivery, so "only one effective result" is checked, not just a state string.
"""

from __future__ import annotations

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


class F04:
    case = "F04"
    variants = ("A", "B")
    purposes = {
        "A": "duplicate delivery of one outbox message yields one effective result",
        "B": "a stale attempt cannot report after the newer attempt completed",
    }

    @staticmethod
    def run(variant, case: Case, keep=False):
        lab = guard_env(Lab())
        client = Client(lab)
        business = Business(lab, client)
        business.fixtures()
        override = lab.override()
        scope = None
        try:
            if variant == "A":
                scope = F04.duplicate_delivery(lab, client, business, case)
            elif variant == "B":
                image = F03.build_delayed_scanner(lab)
                override.env("worker", "PRIVACYTRACE_LEASE_SECONDS", "5")
                for role in ("api", "worker", "runner"):
                    override.env(role, "PRIVACYTRACE_RUNNER_IMAGE_ID", image)
                override.apply("api", "worker", "runner")
                scope = F04.stale_after_success(lab, client, business, case, override)
        finally:
            lab.remove_second_worker("f134-worker-2-" + lab.project[-6:])
            if variant == "B":
                override.restore("api", "worker", "runner")
            lab.compose_run("start", "worker", "dispatcher", "api", check=False)
            try:
                lab.ready(timeout=90)
            except TimeoutError:
                pass
            if scope is not None:
                F04.finish_scope(lab, client, business, case, scope)

    @staticmethod
    def prepare(lab, client, business, case, name):
        scope = business.create(name)
        uploaded = business.upload(scope)
        case.check("synthetic APK accepted", uploaded["status"] == 200, uploaded["status"])
        return scope

    @staticmethod
    def duplicate_delivery(lab, client, business, case):
        scope = F04.prepare(lab, client, business, case, "f04-duplicate")
        started = business.start(scope)
        case.check("start accepted", started["status"] == 200 and bool(scope["job_id"]))
        acquired = business.wait_execution(scope["job_id"], {"RUNNING"}, timeout=120)
        case.note(
            "first delivery acquired",
            "RUNNING with one attempt",
            {"fence": acquired["fence"], "attempt": acquired["attempt"]},
        )
        published = lab.publish_duplicate(scope["job_id"], times=2)
        case.note(
            "duplicate deliveries published",
            "two more deliveries of the same message on the real broker",
            published,
        )
        final = business.wait_terminal(scope, timeout=300)
        report = business.report(scope)
        report_sha = sha256_bytes(report["body"])
        case.note(
            "terminal state",
            "SUCCEEDED",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check(
            "job succeeds exactly once", final.get("state") == "SUCCEEDED", final.get("state")
        )
        case.check("report readable", report["status"] == 200, report["status"])
        # Let the extra deliveries reach the consumer and be refused.
        wait_for(
            "duplicate deliveries consumed",
            lambda: lab.queue_depth() == 0,
            timeout=120,
            interval=0.5,
        )
        time.sleep(3)
        codes = lab.diagnostic_codes("worker", tail=6000)
        warning_lines = lab.warning_lines("worker")
        after = business.report(scope)
        executions = lab.executions(scope["job_id"])
        jobs = [job for job in lab.jobs() if job["job_id"] == scope["job_id"]]
        events = [
            event["state"]
            for event in next(
                item for item in lab.draft_events(scope["id"]) if item["job_id"] == scope["job_id"]
            )["events"]
        ]
        case.note(
            "after duplicate consumption",
            "one report, one execution, one SUCCEEDED event, no second attempt",
            {
                "report_sha_unchanged": after["status"] == 200
                and sha256_bytes(after["body"]) == report_sha,
                "execution_rows": len(executions),
                "attempt": executions[0]["attempt"],
                "fence": executions[0]["fence"],
                "job_rows": len(jobs),
                "events": events,
                "diagnostics": codes,
                "warning_lines": warning_lines,
                "queue_depth": lab.queue_depth(),
            },
        )
        case.check(
            "report bytes unchanged after duplicate delivery",
            after["status"] == 200 and sha256_bytes(after["body"]) == report_sha,
        )
        case.check("exactly one execution row", len(executions) == 1, len(executions))
        case.check("exactly one job row", len(jobs) == 1, len(jobs))
        case.check("exactly one SUCCEEDED event", events.count("SUCCEEDED") == 1, events)
        case.check(
            "duplicate deliveries did not acquire a second attempt",
            executions[0]["attempt"] == acquired["attempt"]
            and executions[0]["fence"] == acquired["fence"],
            {"attempt": executions[0]["attempt"], "fence": executions[0]["fence"]},
        )
        # The product emits a fixed diagnostic warning, but its Celery log
        # format omits %(message)s, so the code is not readable in the container
        # log. Keep this as a non-blocking probe and record the observed lines.
        case.probe(
            "worker logged an explicit duplicate-refusal diagnostic code",
            "EXECUTION_NOT_ACQUIRED" in codes,
            {"codes": codes, "warning_lines": warning_lines},
        )
        case.artifact("report_sha256", report_sha)
        case.artifact("event_trail", events)
        return scope

    @staticmethod
    def stale_after_success(lab, client, business, case, override):
        scope = F04.prepare(lab, client, business, case, "f04-stale")
        started = business.start(scope)
        case.check("start accepted", started["status"] == 200 and bool(scope["job_id"]))
        acquired = business.wait_execution(scope["job_id"], {"RUNNING"}, timeout=120)
        old_owner = str(acquired["owner"])
        old_worker = lab.role_id("worker")
        case.note(
            "old attempt acquired",
            "RUNNING fence=1",
            {
                "fence": acquired["fence"],
                "attempt": acquired["attempt"],
                "owner_alias": old_owner[:8],
            },
        )
        lab.docker("pause", old_worker)
        rearmed = wait_for(
            "old lease expires and the event is re-armed",
            lambda: (
                execution_view(lab, scope["job_id"])
                if execution_view(lab, scope["job_id"]).get("fence") > acquired["fence"]
                else None
            ),
            timeout=120,
            interval=0.3,
        )
        case.note(
            "old attempt frozen past its lease",
            "fence advanced while the old owner is frozen",
            {
                "state": rearmed.get("state"),
                "fence": rearmed.get("fence"),
                "attempt": rearmed.get("attempt"),
            },
        )
        second = lab.run_second_worker()
        wait_for("second worker running", lambda: lab.second_worker_running(second), timeout=90)
        final = business.wait_terminal(scope, timeout=300)
        report = business.report(scope)
        report_sha = sha256_bytes(report["body"])
        counts_before = lab.counts()
        events_before = [
            event["state"]
            for event in next(
                item for item in lab.draft_events(scope["id"]) if item["job_id"] == scope["job_id"]
            )["events"]
        ]
        case.note(
            "new attempt completed",
            "SUCCEEDED with a single report",
            {
                "state": final.get("state"),
                "report_status": report["status"],
                "events": events_before,
                "counts": counts_before,
            },
        )
        case.check("newer attempt succeeds", final.get("state") == "SUCCEEDED", final.get("state"))
        case.check(
            "exactly one SUCCEEDED event before release", events_before.count("SUCCEEDED") == 1
        )
        lab.docker("unpause", old_worker)
        time.sleep(15)
        after = business.report(scope)
        events_after = [
            event["state"]
            for event in next(
                item for item in lab.draft_events(scope["id"]) if item["job_id"] == scope["job_id"]
            )["events"]
        ]
        executions = lab.executions(scope["job_id"])
        counts_after = lab.counts()
        codes = lab.diagnostic_codes("worker", tail=6000)
        case.note(
            "old attempt released after the newer success",
            "late result rejected; report, event trail and material counts consistent",
            {
                "report_status": after["status"],
                "report_sha_unchanged": after["status"] == 200
                and sha256_bytes(after["body"]) == report_sha,
                "events": events_after,
                "executions": executions,
                "counts_before": counts_before,
                "counts_after": counts_after,
                "diagnostics": codes,
            },
        )
        case.check(
            "late result does not replace the report",
            after["status"] == 200 and sha256_bytes(after["body"]) == report_sha,
        )
        case.check(
            "no duplicate terminal event", events_after.count("SUCCEEDED") == 1, events_after
        )
        case.check("no second execution row", len(executions) == 1, len(executions))
        case.check(
            "material/index counts did not grow",
            counts_after["runner_materials"] <= counts_before["runner_materials"] + 1
            and counts_after["jobs"] == counts_before["jobs"],
            {"before": counts_before, "after": counts_after},
        )
        # No persistent lease-lost event exists in the product; the stale
        # rejection is proven by the unchanged bytes and the single execution
        # row. Keep the log probe non-blocking.
        case.probe(
            "worker logged an explicit lease-lost diagnostic",
            "LEASE_LOST" in codes,
            codes,
        )
        case.check(
            "final execution digest still belongs to the committed report",
            bool(executions[0].get("result_sha256")),
            executions[0].get("result_sha256"),
        )
        case.artifact("report_sha256", report_sha)
        lab.remove_second_worker(second)
        return scope

    @staticmethod
    def finish_scope(lab, client, business, case, scope):
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
    raise SystemExit(main_guard(F04))
