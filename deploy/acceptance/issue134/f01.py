"""F01: durable intake survives an API stop and an unconfirmed start response.

Variants (each uses a fresh draft and the real HTTPS entry):

* ``A``  -- confirmed start, then stop API, observe the client cannot read, start
  the API by the handed-over command and read the *same* job again; the intake
  point and the event trail before/after the stop are preserved.
* ``B``  -- the start request is fully sent and the response is deliberately not
  read (unconfirmed receipt); the same request id is retried and must return the
  same job with exactly one outbox event and one execution row.
* ``C``  -- confirmed start, then a maintenance stop of API + dispatcher + worker;
  after restart the same job resumes and completes with its event trail.

Every variant runs against the laboratory's own Compose project only.
"""

from __future__ import annotations

import json
import time

from .f134_common import (
    CA_FILE,
    Business,
    Case,
    Client,
    Lab,
    client_unconfirmed_post,
    guard_env,
    main_guard,
    sha256_bytes,
    utc,
)


class F01:
    case = "F01"
    purposes = {
        "A": "confirmed durable receipt survives an API stop; same task is read again",
        "B": "unconfirmed start response can be retried idempotently without a second job",
        "C": "same job resumes after a controlled maintenance stop of API/queue roles",
    }
    variants = ("A", "B", "C")

    @staticmethod
    def run(variant, case: Case, keep=False):
        lab = guard_env(Lab())
        client = Client(lab)
        business = Business(lab, client)
        business.fixtures()
        scope = None
        try:
            if variant == "A":
                scope = F01.confirmed_then_api_stop(lab, client, business, case)
            elif variant == "B":
                scope = F01.unconfirmed_retry(lab, client, business, case)
            elif variant == "C":
                scope = F01.maintenance_window(lab, client, business, case, keep=keep)
            else:
                raise ValueError(f"unknown variant {variant}")
        finally:
            lab.compose_run("start", "api", check=False)
            try:
                lab.ready(timeout=90)
            except TimeoutError:
                pass
            if scope is not None:
                F01.finish_scope(lab, client, business, case, scope)

    @staticmethod
    def prepare(lab, client, business, case, name):
        scope = business.create(name)
        uploaded = business.upload(scope)
        case.note(
            "prepare",
            "draft created and synthetic APK accepted",
            {"draft_alias": scope["id"][:8], "upload_status": uploaded["status"]},
        )
        case.check("synthetic APK accepted", uploaded["status"] == 200, uploaded["status"])
        return scope

    @staticmethod
    def intake_point(lab, scope, case, label):
        events = lab.draft_events(scope["id"])
        row = next((item for item in events if item["job_id"] == scope["job_id"]), None)
        state = lab.state()
        job = next((item for item in state["jobs"] if item["job_id"] == scope["job_id"]), None)
        outbox = [item for item in state["outbox"] if item["job_id"] == scope["job_id"]]
        [item for item in state["jobs"] if item["job_id"] == scope["job_id"]]
        point = {
            "label": label,
            "at_utc": utc(),
            "draft_event_states": [event["state"] for event in (row or {}).get("events", [])],
            "job_state": (job or {}).get("state"),
            "has_report": (job or {}).get("has_report"),
            "outbox": [{"state": item["state"], "attempts": item["attempts"]} for item in outbox],
            "job_rows": len(state["jobs"]),
        }
        case.note(f"intake point ({label})", "durable row exists", point)
        case.check(
            f"intake point {label}: outbox row exists",
            len(outbox) == 1,
            len(outbox),
        )
        case.check(
            f"intake point {label}: job row exists",
            job is not None,
            (job or {}).get("state"),
        )
        return {"events": events, "state": state, "point": point}

    @staticmethod
    def confirmed_then_api_stop(lab, client, business, case):
        scope = F01.prepare(lab, client, business, case, "f01-confirmed")
        started = business.start(scope)
        case.note(
            "start (confirmed)",
            "HTTP 200 with a durable job id",
            {"status": started["status"], "job_alias": (scope.get("job_id") or "")[:8]},
        )
        case.check("start accepted", started["status"] == 200 and bool(scope["job_id"]))
        before = F01.intake_point(lab, scope, case, "before API stop")
        case.check("event trail contains QUEUED", "QUEUED" in before["point"]["draft_event_states"])

        lab.stop("api")
        case.note(
            "stop API", "api container not running", {"running": lab.running_roles().get("api")}
        )
        unread = client.request(f"/api/v1/jobs/{scope['job_id']}", token=scope["token"], timeout=10)
        case.note(
            "client read while API stopped",
            "no successful job read",
            {"status": unread["status"], "error": unread.get("error", "")},
        )
        case.check(
            "client cannot read while API is stopped", unread["status"] != 200, unread["status"]
        )
        during = lab.state()
        during_job = next(
            (item for item in during["jobs"] if item["job_id"] == scope["job_id"]), None
        )
        case.check(
            "durable job row survives API stop",
            during_job is not None,
            (during_job or {}).get("state"),
        )

        lab.start("api")
        lab.ready()
        case.note("start API", "health 200", {"health": lab.health()})
        case.check("API is healthy after restart", lab.health())
        resumed = client.request(f"/api/v1/jobs/{scope['job_id']}", token=scope["token"])
        resumed_job = resumed["json"] if isinstance(resumed["json"], dict) else {}
        case.note(
            "client reads same task after restart",
            "HTTP 200 for the same job id",
            {
                "status": resumed["status"],
                "state": resumed_job.get("state"),
                "job_alias": str(resumed_job.get("id", ""))[:8],
            },
        )
        case.check("same job id readable after restart", resumed["status"] == 200)
        after = F01.intake_point(lab, scope, case, "after API restart")
        before_states = before["point"]["draft_event_states"]
        after_states = after["point"]["draft_event_states"]
        case.check(
            "event trail before restart is a prefix of the trail after restart",
            after_states[: len(before_states)] == before_states,
            {"before": before_states, "after": after_states},
        )
        final = business.wait_terminal(scope, timeout=180)
        report = business.report(scope)
        case.note(
            "terminal state and report",
            "SUCCEEDED with a readable report",
            {
                "state": final.get("state"),
                "report_status": report["status"],
                "report_bytes": report["bytes"],
            },
        )
        case.check(
            "job succeeds after API restart", final.get("state") == "SUCCEEDED", final.get("state")
        )
        case.check("report is readable", report["status"] == 200, report["status"])
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        final_state = lab.state()
        final_outbox = [item for item in final_state["outbox"] if item["job_id"] == scope["job_id"]]
        case.check(
            "single outbox event reached DELIVERED",
            len(final_outbox) == 1 and final_outbox[0]["state"] == "DELIVERED",
            [item["state"] for item in final_outbox],
        )
        return scope

    @staticmethod
    def unconfirmed_retry(lab, client, business, case):
        scope = F01.prepare(lab, client, business, case, "f01-unconfirmed")
        from uuid import uuid4

        request_id = uuid4().hex
        body = json.dumps({"revision": scope["revision"], "request_id": request_id}).encode()
        case.note(
            "unconfirmed start",
            "request fully sent, response deliberately dropped",
            client_unconfirmed_post(
                lab.port, f"/api/v1/web/drafts/{scope['id']}/start", body, scope["token"], CA_FILE
            ),
        )
        time.sleep(0.5)
        persisted = F01.find_scope_job(lab, scope)
        case.note(
            "intake after dropped response",
            "server persisted at most one job for this draft",
            {"persisted_job": persisted, "job_alias": (persisted or "")[:8]},
        )
        scope["request_id"] = request_id
        retry = business.start(scope, request_id=request_id)
        case.note(
            "idempotent retry with the same request id",
            "HTTP 200",
            {"status": retry["status"], "job_alias": (scope.get("job_id") or "")[:8]},
        )
        case.check("retry accepted", retry["status"] == 200)
        if persisted:
            case.check(
                "retry returns the job persisted before the lost response",
                scope["job_id"] == persisted,
                {"persisted": persisted[:8], "retry": (scope.get("job_id") or "")[:8]},
            )
        else:
            case.note(
                "dropped response arrived before persistence",
                "the retry created the only job",
                {"note": "first request did not reach the durable commit"},
            )
        second = business.start(scope, request_id=request_id)
        case.note(
            "second idempotent replay",
            "HTTP 200 with the same job id",
            {"status": second["status"], "job_alias": (scope.get("job_id") or "")[:8]},
        )
        case.check("second replay returns the same job", second["status"] == 200)
        events = lab.draft_events(scope["id"])
        run = next((item for item in events if item["job_id"] == scope["job_id"]), None)
        case.note(
            "draft run ledger",
            "exactly one run entry for this request id",
            {
                "runs": len(events),
                "events": [event["state"] for event in (run or {}).get("events", [])],
            },
        )
        case.check("draft has exactly one run", len(events) == 1, len(events))
        current = lab.state()
        outbox = [item for item in current["outbox"] if item["job_id"] == scope["job_id"]]
        execution = [item for item in current["jobs"] if item["job_id"] == scope["job_id"]]
        case.check("exactly one outbox row", len(outbox) == 1, len(outbox))
        case.check("exactly one execution row", len(execution) == 1, len(execution))
        final = business.wait_terminal(scope, timeout=180)
        report = business.report(scope)
        case.note(
            "terminal state",
            "SUCCEEDED",
            {"state": final.get("state"), "report_status": report["status"]},
        )
        case.check("single job reaches SUCCEEDED", final.get("state") == "SUCCEEDED")
        case.artifact("report_sha256", sha256_bytes(report["body"]))
        case.artifact("request_id_alias", request_id[:12])
        return scope

    @staticmethod
    def maintenance_window(lab, client, business, case, keep=False):
        scope = F01.prepare(lab, client, business, case, "f01-window")
        override = lab.override().env("worker", "PRIVACYTRACE_LEASE_SECONDS", "5")
        try:
            override.apply("worker")
            started = business.start(scope)
            case.note("start", "accepted", {"status": started["status"]})
            case.check("start accepted", started["status"] == 200 and bool(scope["job_id"]))
            before = F01.intake_point(lab, scope, case, "before maintenance stop")
            lab.stop("worker", "dispatcher", "api")
            time.sleep(3)
            unread = client.request(
                f"/api/v1/jobs/{scope['job_id']}", token=scope["token"], timeout=10
            )
            case.note(
                "client read while stopped",
                "no successful read",
                {"status": unread["status"], "error": unread.get("error", "")},
            )
            case.check("client cannot read during maintenance", unread["status"] != 200)
            lab.start("api", "worker", "dispatcher")
            lab.ready()
            resumed = client.request(f"/api/v1/jobs/{scope['job_id']}", token=scope["token"])
            case.note(
                "same task readable after maintenance",
                "HTTP 200",
                {"status": resumed["status"], "state": (resumed["json"] or {}).get("state")},
            )
            case.check("same task readable", resumed["status"] == 200)
            final = business.wait_terminal(scope, timeout=240)
            after_states = [
                event["state"]
                for event in next(
                    item
                    for item in lab.draft_events(scope["id"])
                    if item["job_id"] == scope["job_id"]
                )["events"]
            ]
            case.note(
                "resume event trail",
                "SUCCEEDED and preserved prefix",
                {"state": final.get("state"), "events": after_states},
            )
            case.check(
                "event prefix preserved",
                after_states[: len(before["point"]["draft_event_states"])]
                == before["point"]["draft_event_states"],
            )
            case.check(
                "recovered job succeeds", final.get("state") == "SUCCEEDED", final.get("state")
            )
            report = business.report(scope)
            case.check("report readable", report["status"] == 200, report["status"])
            case.artifact("report_sha256", sha256_bytes(report["body"]))
        finally:
            override.restore("worker")
        return scope

    @staticmethod
    def find_scope_job(lab, scope):
        source = (
            "import json,os;from pathlib import Path;"
            "from privacytrace.storage_factory import create_store;"
            "from privacytrace.postgres_intake import PostgresWebIntake;"
            "store=create_store(Path(os.environ['PRIVACYTRACE_STORE_ROOT']));"
            "intake=PostgresWebIntake(store);"
            f"draft=intake._get({scope['id']!r});"
            "intake.close();store.close();"
            "print(json.dumps([r['job_id'] for r in draft['jobs']]))"
        )
        rows = json.loads(lab.python(source))
        return rows[0] if rows else ""

    @staticmethod
    def finish_scope(lab, client, business, case, scope):
        report_before = None
        try:
            report_before = client.request(
                f"/api/v1/jobs/{scope['job_id']}/report", token=scope["token"]
            )
        except Exception:  # noqa: BLE001 - best-effort observation
            report_before = None
        status = business.cleanup_scope(scope)
        case.note(
            "scope cleanup",
            "draft deleted through its own capability",
            {"delete_status": status},
        )
        case.check("scope cleanup accepted", status in {200, 204, 404}, status)
        if report_before is not None and report_before["status"] == 200:
            case.artifact("report_sha256_before_delete", sha256_bytes(report_before["body"]))


if __name__ == "__main__":
    raise SystemExit(main_guard(F01))
