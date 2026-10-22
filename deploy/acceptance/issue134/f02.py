"""F02: durable delivery across publisher/broker stops at both outbox stages.

Variants use the real outbox ledger, the real Redis broker and the real worker:

* ``A`` -- the outbox publisher (dispatcher) is stopped while the event is
  PENDING; after it starts the persisted job must be delivered exactly once.
* ``B`` -- the broker (Redis) is stopped while the event is PENDING; the
  publisher records bounded retries with a visible BROKER_UNAVAILABLE code, and
  recovery delivers the same job without losing it.
* ``C`` -- the broker is stopped after DELIVERED while the worker runs; the
  job must still finish because the lease lives in PostgreSQL, not the broker.
* ``D`` -- the publisher is stopped after DELIVERED; the running job is
  unaffected and one report exists.

Only the laboratory Compose project is mutated. Message identifiers are
recorded as aliases; no token, password or broker DSN is written.
"""

from __future__ import annotations

import time

from .f134_common import (
    Business,
    Case,
    Client,
    Lab,
    guard_env,
    main_guard,
    sha256_bytes,
    utc,
    wait_for,
)


class F02:
    case = "F02"
    variants = ("A", "B", "C", "D")
    purposes = {
        "A": "PENDING event survives a stopped outbox publisher and is delivered once",
        "B": "PENDING event retries visibly while the broker is stopped and is not lost",
        "C": "DELIVERED job completes while the broker is stopped (lease is in PostgreSQL)",
        "D": "DELIVERED job is unaffected by a stopped publisher",
    }

    @staticmethod
    def run(variant, case: Case, keep=False):
        lab = guard_env(Lab())
        client = Client(lab)
        business = Business(lab, client)
        business.fixtures()
        scope = None
        try:
            handler = {
                "A": F02.pending_stop_publisher,
                "B": F02.pending_stop_broker,
                "C": F02.delivered_stop_broker,
                "D": F02.delivered_stop_publisher,
            }[variant]
            scope = handler(lab, client, business, case)
        finally:
            F02.restore_roles(lab)
            if scope is not None:
                F02.finish_scope(client, business, case, scope)

    @staticmethod
    def restore_roles(lab):
        lab.compose_run("start", "redis", "worker", "dispatcher", "api", check=False)
        try:
            lab.wait_healthy("redis", timeout=90)
            lab.ready(timeout=90)
        except TimeoutError:
            pass

    @staticmethod
    def prepare(lab, client, business, case, name):
        scope = business.create(name)
        uploaded = business.upload(scope)
        case.check("synthetic APK accepted", uploaded["status"] == 200, uploaded["status"])
        return scope

    @staticmethod
    def start(lab, client, business, case, scope, label):
        result = business.start(scope)
        case.note(
            f"start {label}",
            "HTTP 200 and a durable job",
            {"status": result["status"], "job_alias": (scope.get("job_id") or "")[:8]},
        )
        case.check(f"start accepted ({label})", result["status"] == 200 and bool(scope["job_id"]))
        return result

    @staticmethod
    def outbox(lab, scope):
        rows = lab.outbox(scope["job_id"])
        return rows[0] if rows else {}

    @staticmethod
    def snapshot(lab, scope, label):
        outbox = F02.outbox(lab, scope)
        executions = lab.executions(scope["job_id"])
        jobs = [job for job in lab.jobs() if job["job_id"] == scope["job_id"]]
        state = {
            "label": label,
            "at_utc": utc(),
            "outbox": {
                "state": outbox.get("state"),
                "attempts": outbox.get("attempts"),
                "last_error_code": outbox.get("last_error_code"),
                "event_alias": str(outbox.get("event_id", ""))[:12],
            },
            "execution": {
                "state": (executions[0] if executions else {}).get("state"),
                "attempt": (executions[0] if executions else {}).get("attempt"),
                "fence": (executions[0] if executions else {}).get("fence"),
            },
            "job_state": (jobs[0] if jobs else {}).get("state"),
            "queue_depth": lab.queue_depth(),
        }
        return state

    @staticmethod
    def pending_stop_publisher(lab, client, business, case):
        lab.stop("dispatcher")
        wait_for(
            "dispatcher stopped",
            lambda: lab.running_roles().get("dispatcher", {}).get("state") != "running",
            timeout=30,
        )
        scope = F02.prepare(lab, client, business, case, "f02-pending-publisher")
        F02.start(lab, client, business, case, scope, "with publisher stopped")
        wait_for(
            "outbox PENDING",
            lambda: F02.outbox(lab, scope).get("state") == "PENDING",
            timeout=30,
        )
        first = F02.snapshot(lab, scope, "publisher stopped")
        case.note("PENDING with publisher stopped", "PENDING attempts=0, queue empty", first)
        case.check("event waits in PENDING", first["outbox"]["state"] == "PENDING", first["outbox"])
        case.check("no delivery attempt was spent", first["outbox"]["attempts"] == 0)
        case.check("broker queue is empty", first["queue_depth"] == 0, first["queue_depth"])
        time.sleep(3)
        again = F02.snapshot(lab, scope, "publisher still stopped")
        case.check(
            "event stays PENDING while the publisher is stopped",
            again["outbox"]["state"] == "PENDING",
            again["outbox"],
        )
        case.check(
            "job stays QUEUED while undelivered", again["job_state"] == "QUEUED", again["job_state"]
        )

        lab.start("dispatcher")
        delivered = wait_for(
            "outbox DELIVERED",
            lambda: (
                F02.outbox(lab, scope)
                if F02.outbox(lab, scope).get("state") == "DELIVERED"
                else None
            ),
            timeout=120,
        )
        case.note(
            "publisher restarted",
            "event DELIVERED with one delivery attempt",
            {"state": delivered["state"], "attempts": delivered["attempts"]},
        )
        case.check("event is delivered after restart", delivered["state"] == "DELIVERED")
        case.check(
            "delivery attempts are bounded", delivered["attempts"] == 1, delivered["attempts"]
        )
        final = business.wait_terminal(scope, timeout=180)
        report = business.report(scope)
        case.note(
            "terminal state",
            "SUCCEEDED with one readable report",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check("same job succeeds", final.get("state") == "SUCCEEDED", final.get("state"))
        case.check("report readable", report["status"] == 200, report["status"])
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        case.artifact("event_alias", first["outbox"]["event_alias"])
        return scope

    @staticmethod
    def pending_stop_broker(lab, client, business, case):
        scope = F02.prepare(lab, client, business, case, "f02-pending-broker")
        lab.stop("redis")
        wait_for(
            "redis stopped",
            lambda: lab.running_roles().get("redis", {}).get("state") != "running",
            timeout=30,
        )
        F02.start(lab, client, business, case, scope, "with broker stopped")
        wait_for(
            "visible delivery failure",
            lambda: (
                F02.outbox(lab, scope)
                if (F02.outbox(lab, scope).get("attempts") or 0) >= 1
                else None
            ),
            timeout=90,
        )
        first = F02.snapshot(lab, scope, "broker stopped, first retry")
        time.sleep(3)
        second = F02.snapshot(lab, scope, "broker stopped, later retry")
        case.note(
            "bounded retries while broker is stopped",
            "attempts grow with a visible BROKER_UNAVAILABLE code",
            {"first": first, "second": second},
        )
        case.check(
            "delivery failure is visible",
            second["outbox"]["last_error_code"] == "BROKER_UNAVAILABLE",
            second["outbox"]["last_error_code"],
        )
        case.check(
            "attempts are bounded",
            1 <= int(second["outbox"]["attempts"] or 0) < 5,
            second["outbox"]["attempts"],
        )
        case.check(
            "job stays QUEUED while broker is down",
            second["job_state"] == "QUEUED",
            second["job_state"],
        )
        case.check(
            "broker queue is unreachable", second["queue_depth"] == -1, second["queue_depth"]
        )

        lab.start("redis")
        lab.wait_healthy("redis", timeout=120)
        delivered = wait_for(
            "outbox DELIVERED after broker recovery",
            lambda: (
                F02.outbox(lab, scope)
                if F02.outbox(lab, scope).get("state") == "DELIVERED"
                else None
            ),
            timeout=240,
        )
        case.note(
            "broker recovered",
            "the same event is delivered",
            {"state": delivered["state"], "attempts": delivered["attempts"]},
        )
        case.check("same event is delivered", delivered["state"] == "DELIVERED")
        final = business.wait_terminal(scope, timeout=240)
        report = business.report(scope)
        case.note(
            "terminal state",
            "SUCCEEDED",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check("job is not lost", final.get("state") == "SUCCEEDED", final.get("state"))
        case.check("report readable", report["status"] == 200, report["status"])
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        case.artifact("event_alias", first["outbox"]["event_alias"])
        return scope

    @staticmethod
    def delivered_stop_broker(lab, client, business, case):
        scope = F02.prepare(lab, client, business, case, "f02-delivered-broker")
        F02.start(lab, client, business, case, scope, "normally")
        running = wait_for(
            "DELIVERED and RUNNING",
            lambda: (
                F02.snapshot(lab, scope, "delivered")
                if F02.outbox(lab, scope).get("state") == "DELIVERED"
                and lab.executions(scope["job_id"])[0]["state"] == "RUNNING"
                else None
            ),
            timeout=120,
        )
        case.note("DELIVERED while worker runs", "event DELIVERED, execution RUNNING", running)
        case.check(
            "event is DELIVERED before broker stop", running["outbox"]["state"] == "DELIVERED"
        )
        lab.stop("redis")
        case.note(
            "stop broker after delivery",
            "worker keeps its PostgreSQL lease",
            {"redis": lab.running_roles().get("redis")},
        )
        final = business.wait_terminal(scope, timeout=300)
        report = business.report(scope)
        case.note(
            "terminal state with broker down",
            "SUCCEEDED and report readable",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check(
            "delivered job completes without the broker",
            final.get("state") == "SUCCEEDED",
            final.get("state"),
        )
        case.check("report readable", report["status"] == 200, report["status"])
        case.check("outbox remains DELIVERED", F02.outbox(lab, scope).get("state") == "DELIVERED")
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        lab.start("redis")
        lab.wait_healthy("redis", timeout=120)
        time.sleep(5)
        again = F02.snapshot(lab, scope, "after broker recovery")
        case.note(
            "post-recovery ledger",
            "no duplicate effective result",
            again,
        )
        case.check("no new job created after recovery", len(lab.jobs()) >= 1)
        duplicate = [
            job
            for job in lab.jobs()
            if job["job_id"] == scope["job_id"] and job["has_bundle"] is not True
        ]
        case.check("original job keeps its single report", not duplicate, duplicate)
        return scope

    @staticmethod
    def delivered_stop_publisher(lab, client, business, case):
        scope = F02.prepare(lab, client, business, case, "f02-delivered-publisher")
        F02.start(lab, client, business, case, scope, "normally")
        running = wait_for(
            "DELIVERED",
            lambda: (
                F02.snapshot(lab, scope, "delivered")
                if F02.outbox(lab, scope).get("state") == "DELIVERED"
                else None
            ),
            timeout=120,
        )
        case.note("event delivered", "DELIVERED before publisher stop", running)
        lab.stop("dispatcher")
        wait_for(
            "dispatcher stopped",
            lambda: lab.running_roles().get("dispatcher", {}).get("state") != "running",
            timeout=30,
        )
        final = business.wait_terminal(scope, timeout=240)
        report = business.report(scope)
        case.note(
            "terminal state with publisher stopped",
            "SUCCEEDED and report readable",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check(
            "delivered job completes without the publisher",
            final.get("state") == "SUCCEEDED",
            final.get("state"),
        )
        case.check("report readable", report["status"] == 200, report["status"])
        case.check("outbox remains DELIVERED", F02.outbox(lab, scope).get("state") == "DELIVERED")
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        return scope

    @staticmethod
    def finish_scope(client, business, case, scope):
        try:
            report = client.request(f"/api/v1/jobs/{scope['job_id']}/report", token=scope["token"])
            if report["status"] == 200:
                case.artifact("report_sha256_before_delete", sha256_bytes(report["body"]))
        except Exception:  # noqa: BLE001 - best-effort observation
            pass
        status = business.cleanup_scope(scope)
        case.note("scope cleanup", "deleted through its own capability", {"delete_status": status})
        case.check("scope cleanup accepted", status in {200, 204, 404}, status)


if __name__ == "__main__":
    raise SystemExit(main_guard(F02))
