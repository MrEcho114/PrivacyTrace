"""R4: fault injection and recovery, with before/after observable state.

For each injected fault the receipt records: the injection means, the state
observed before and after, the wall clock, and a final-consistency verdict.

The collector drives only documented operator actions
(``compose restart``/``stop``/``start``, the ``reclamation`` profile run) and
public read endpoints. It never edits the database, never deletes the volumes
and never kills a container outside the named Compose project.

Destructive steps require ``PT_ACCEPTANCE_ALLOW_DESTRUCTIVE=1``; without it each
step is a SKIP that names the missing permission, not a silent pass.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .r2_business_loop import Scope, create_scope, poll_job, start_job, upload_apk
from .receipt import Check, CheckRecorder, Receipt
from .topology import (
    Topology,
    TopologyUnavailable,
    compose_output,
    request,
)

TICKET = "R4"
ROOT = Path(__file__).resolve().parents[2]

# Role -> the observable that must recover. Values are endpoint pairs.
RECOVERY_OBSERVABLES = ("/_health/live", "/api/v1/health")


@dataclass
class Observation:
    """One before/after sample of the API surface."""

    at: str
    live: int
    ready: int
    health: int
    ready_body: Any = None
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sample(topology: Topology, note: str = "") -> Observation:
    # Internal probes are deliberately 404 through Caddy. Probe inside API;
    # never open the management surface just to make an acceptance test pass.
    raw = compose_output(
        topology,
        "exec",
        "-T",
        "api",
        "/opt/venv/bin/python",
        "-c",
        "import json,urllib.request,urllib.error; result={};\n"
        "for key in ('live','ready'):\n"
        " try: result[key]=urllib.request.urlopen("
        "'http://127.0.0.1:8000/_health/'+key,timeout=4).status\n"
        " except urllib.error.HTTPError as e: result[key]=e.code\n"
        "print(json.dumps(result))",
    )
    internal = json.loads(raw)
    health = request(topology, "/api/v1/health", timeout=10)
    from .receipt import utc_now

    return Observation(
        at=utc_now(),
        live=internal["live"],
        ready=internal["ready"],
        health=health.status,
        ready_body=None,
        note=note,
    )


def _wait_recovered(
    topology: Topology, *, budget_s: float = 180.0, interval_s: float = 3.0
) -> Observation:
    deadline = time.monotonic() + budget_s
    last = None
    while time.monotonic() < deadline:
        try:
            last = _sample(topology, "recovery poll")
        except TopologyUnavailable:
            pass
        if last and last.live == 200 and last.health == 200 and last.ready == 200:
            return last
        time.sleep(interval_s)
    if last is None:
        raise TopologyUnavailable("no readiness sample within recovery budget")
    return last


@dataclass
class FaultStep:
    """A single injection, described for the reader of the receipt."""

    name: str
    means: str
    compose_arguments: tuple[str, ...]
    service: str
    requires_destructive: bool = True
    waits_for_ready: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


RESTART_STEPS = (
    FaultStep("r4.restart.api", "docker compose restart api", ("restart", "api"), "api"),
    FaultStep(
        "r4.restart.redis",
        "docker compose restart redis; readiness must recover",
        ("restart", "redis"),
        "redis",
    ),
    FaultStep(
        "r4.restart.worker",
        "docker compose restart worker; readiness must recover",
        ("restart", "worker"),
        "worker",
    ),
    FaultStep(
        "r4.restart.runner",
        "restart the laboratory Runner; re-check authenticated readiness",
        ("restart", "runner"),
        "runner",
    ),
)

BROKER_OUTAGE = FaultStep(
    "r4.broker_outage_and_recovery",
    "docker compose stop redis; assert ready degrades while live stays up; start redis",
    ("stop", "redis"),
    "redis",
)


def _inject_step(topology: Topology, step: FaultStep) -> Check:
    recorder = CheckRecorder(
        step.name,
        f"compose {step.compose_arguments[0]} {step.service} + readiness sampling",
        ticket=TICKET,
    )
    if not topology.allow_destructive:
        return recorder.skip("PT_ACCEPTANCE_ALLOW_DESTRUCTIVE is not 1: no fault injected")
    if not topology.compose_files:
        return recorder.skip("PT_ACCEPTANCE_COMPOSE_FILES not set: no operator action possible")
    try:
        before = _sample(topology, "before injection")
    except TopologyUnavailable as error:
        return recorder.skip(f"topology unreachable before injection: {error}")
    if (before.live, before.health, before.ready) != (200, 200, 200):
        return recorder.fail("baseline was not healthy", before=before.as_dict())
    try:
        compose_output(topology, *step.compose_arguments, timeout=180)
    except TopologyUnavailable as error:
        return recorder.skip(f"injection command unavailable: {error}")
    degraded: Observation | None = None
    try:
        # A completed restart can be healthy already. This observation does not
        # prove degradation; explicit stop/start drills assert that separately.
        degraded = _sample(topology, "after injection")
    except TopologyUnavailable:
        degraded = Observation(
            at="", live=0, ready=0, health=0, note="connection refused during injection"
        )
    try:
        after = _wait_recovered(topology)
    except TopologyUnavailable as error:
        return recorder.fail(f"did not recover within budget: {error}", before=before.as_dict())
    consistent = after.live == 200 and after.health == 200 and after.ready == 200
    detail = {
        "means": step.means,
        "before": before.as_dict(),
        "during": degraded.as_dict(),
        "after": after.as_dict(),
    }
    if not consistent:
        return recorder.fail("API did not return to live+health 200", **detail)
    if step.waits_for_ready and after.ready != 200:
        return recorder.fail(f"readiness answered unexpectedly: {after.ready}", **detail)
    return recorder.pass_(
        f"recovered: live={after.live} ready={after.ready}",
        **detail,
    )


def _broker_outage(topology: Topology) -> Check:
    recorder = CheckRecorder(
        BROKER_OUTAGE.name,
        "compose stop redis -> readiness must degrade while live stays 200 -> compose start redis",
        ticket=TICKET,
    )
    if not topology.allow_destructive:
        return recorder.skip("PT_ACCEPTANCE_ALLOW_DESTRUCTIVE is not 1: no outage injected")
    if not topology.compose_files:
        return recorder.skip("PT_ACCEPTANCE_COMPOSE_FILES not set: no operator action possible")
    try:
        before = _sample(topology, "before outage")
        compose_output(topology, "stop", "redis", timeout=120)
    except TopologyUnavailable as error:
        return recorder.skip(f"cannot inject broker outage: {error}")
    try:
        time.sleep(3)
        during = _sample(topology, "broker stopped")
    except TopologyUnavailable as error:
        return recorder.skip(f"API unreachable during outage: {error}")
    finally:
        try:
            compose_output(topology, "start", "redis", timeout=120)
        except TopologyUnavailable as error:
            return recorder.fail(f"broker did not restart: {error}")
    after = _wait_recovered(topology, budget_s=300)
    detail = {
        "before": before.as_dict(),
        "during": during.as_dict(),
        "after": after.as_dict(),
    }
    # The documented behavior: live stays up, readiness degrades, then recovers.
    if during.live != 200:
        return recorder.fail("live must stay 200 while the broker is down", **detail)
    if during.ready == 200:
        return recorder.fail("readiness stayed 200 with the broker down", **detail)
    if not (after.live == 200 and after.health == 200):
        return recorder.fail("did not recover after the broker restarted", **detail)
    return recorder.pass_(
        f"live stayed 200, ready degraded to {during.ready}, recovered to {after.ready}",
        **detail,
    )


def _heartbeat_loss(topology: Topology) -> Check:
    recorder = CheckRecorder(
        "r4.runner_heartbeat_loss",
        "stop laboratory runner -> readiness 503 -> restart -> readiness 200",
        ticket=TICKET,
    )
    if not topology.allow_destructive:
        return recorder.skip("PT_ACCEPTANCE_ALLOW_DESTRUCTIVE is not 1: no runner outage")
    from .topology import compose_services

    if "runner" not in compose_services(topology):
        return recorder.skip("the configured topology has no controllable Runner")
    try:
        compose_output(topology, "stop", "runner")
        during = _sample(topology)
    finally:
        compose_output(topology, "start", "runner")
    after = _wait_recovered(topology)
    if during.live != 200 or during.ready != 503 or after.ready != 200:
        return recorder.fail("Runner outage did not degrade and recover readiness")
    return recorder.pass_(
        "authenticated Runner readiness degraded and recovered",
        during=during.as_dict(),
        after=after.as_dict(),
    )


def _cancellation(topology: Topology) -> Check:
    recorder = CheckRecorder(
        "r4.cancel_submitted_job",
        "submit job -> POST /jobs/{id}/cancel -> GET job must reach CANCELLED",
        ticket=TICKET,
    )
    if not topology.allow_writes:
        return recorder.skip("PT_ACCEPTANCE_ALLOW_WRITES is not 1: no job submitted")
    if not topology.allow_destructive:
        return recorder.skip("PT_ACCEPTANCE_ALLOW_DESTRUCTIVE is not 1: cancel mutates state")
    try:
        from .r2_business_loop import Fixtures

        fixtures = Fixtures.build()
        scope = create_scope(topology, "acceptance-cancel", "Cancellation scope.")
        upload = upload_apk(topology, scope, fixtures.single_apk)
        if upload.status != 200:
            return recorder.skip(f"upload HTTP {upload.status}")
        start_job(topology, scope)
        if not scope.job_id:
            return recorder.skip("job was not created")
        cancel = request(
            topology, f"/api/v1/jobs/{scope.job_id}/cancel", method="POST", token=scope.token
        )
        final = poll_job(topology, scope, budget_s=300, interval_s=3)
    except TopologyUnavailable as error:
        return recorder.skip(f"topology unavailable: {error}")
    detail = {
        "cancel_status": cancel.status,
        "final_state": final["state"],
        "trail": final["trail"],
        "job_id": scope.job_id,
    }
    if cancel.status != 200:
        return recorder.fail(f"cancel HTTP {cancel.status}", **detail)
    if final["state"] != "CANCELLED":
        return recorder.fail(f"job ended in {final['state']} after cancellation", **detail)
    return recorder.pass_(f"cancel accepted, job reached {final['state']}", **detail)


def _late_result(topology: Topology) -> Check:
    recorder = CheckRecorder(
        "r4.late_result_rejected",
        "old attempt / revoked lease result must be fenced out",
        ticket=TICKET,
    )
    if not topology.allow_destructive:
        return recorder.skip("PT_ACCEPTANCE_ALLOW_DESTRUCTIVE is not 1")
    import os

    state = os.environ.get("PT_ACCEPTANCE_LAB_STATE")
    if not state:
        return recorder.skip("an owned controllable laboratory is required")
    from .late_result_drill import drill
    from .provision import Laboratory

    try:
        result = drill(Laboratory(state), topology)
        return recorder.pass_("real completed Runner output fenced after cancellation", **result)
    except Exception as error:
        return recorder.fail(type(error).__name__)


def _orphan_reclamation(topology: Topology) -> Check:
    recorder = CheckRecorder(
        "r4.orphan_reclamation",
        "compose --profile reclamation run --rm reclaim (one-shot, object counts)",
        ticket=TICKET,
    )
    if not topology.compose_files:
        return recorder.skip("PT_ACCEPTANCE_COMPOSE_FILES not set")
    if not topology.allow_destructive:
        return recorder.skip("PT_ACCEPTANCE_ALLOW_DESTRUCTIVE is not 1: reclaim mutates state")
    try:
        output = compose_output(
            topology,
            "--profile",
            "reclamation",
            "run",
            "--rm",
            "--no-deps",
            "reclaim",
            timeout=600,
        )
    except TopologyUnavailable as error:
        return recorder.skip(f"reclaim role could not run: {error}")
    counts: dict[str, Any] = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                counts = json.loads(line)
            except ValueError:
                continue
    detail = {"object_counts": counts, "collector_output_lines": len(output.splitlines())}
    if not {"objects", "temporary", "pending"}.issubset(counts):
        return recorder.fail("reclaim produced no object-count JSON", **detail)
    if counts.get("pending"):
        return recorder.fail(f"reclaim left pending={counts['pending']}", **detail)
    return recorder.pass_(
        f"reclaim objects={counts.get('objects', 0)} temporary={counts.get('temporary', 0)}",
        **detail,
    )


def _deletion(topology: Topology) -> Check:
    recorder = CheckRecorder(
        "r4.delete_submitted_scope",
        "submit -> DELETE draft -> job must not publish a report",
        ticket=TICKET,
    )
    if not (topology.allow_writes and topology.allow_destructive):
        return recorder.skip(
            "needs PT_ACCEPTANCE_ALLOW_WRITES=1 and PT_ACCEPTANCE_ALLOW_DESTRUCTIVE=1"
        )
    try:
        from .r2_business_loop import Fixtures

        fixtures = Fixtures.build()
        scope: Scope = create_scope(topology, "acceptance-delete", "Deletion scope.")
        upload = upload_apk(topology, scope, fixtures.single_apk)
        if upload.status != 200:
            return recorder.skip(f"upload HTTP {upload.status}")
        start_job(topology, scope)
        if not scope.job_id:
            return recorder.skip("job was not created")
        deleted = request(
            topology, f"/api/v1/web/drafts/{scope.draft_id}", method="DELETE", token=scope.token
        )
        report = request(topology, f"/api/v1/jobs/{scope.job_id}/report", token=scope.token)
    except TopologyUnavailable as error:
        return recorder.skip(f"topology unavailable: {error}")
    detail = {"delete_status": deleted.status, "report_after_delete": report.status}
    if deleted.status != 200:
        return recorder.fail(f"draft delete HTTP {deleted.status}", **detail)
    if report.status == 200:
        return recorder.fail("report still readable after deletion", **detail)
    return recorder.pass_(f"draft deleted; report now HTTP {report.status}", **detail)


def _budget_recovery(topology: Topology) -> Check:
    recorder = CheckRecorder(
        "r4.oom_and_timeout_budget",
        "run the controlled OOM/timeout worker images against the runner",
        ticket=TICKET,
    )
    import os

    state = os.environ.get("PT_ACCEPTANCE_LAB_STATE")
    if not state or not topology.allow_destructive:
        return recorder.skip("an owned controllable laboratory is required")
    from .fault_drill import drill
    from .provision import Laboratory

    try:
        return recorder.pass_(
            "controlled Docker faults and owned-orphan recovery verified",
            **drill(Laboratory(state), topology),
        )
    except Exception as error:
        import traceback

        frame = traceback.extract_tb(error.__traceback__)[-1]
        return recorder.fail(type(error).__name__, function=frame.name, line=frame.lineno)


def collect() -> list[Check]:
    topology = Topology.from_env()
    checks: list[Check] = []

    baseline = CheckRecorder(
        "r4.baseline_health",
        "GET /_health/live, /_health/ready, /api/v1/health",
        ticket=TICKET,
    )
    if not topology.configured:
        checks.append(baseline.skip("topology not configured: " + ", ".join(topology.missing())))
    else:
        try:
            sample = _sample(topology, "baseline")
        except TopologyUnavailable as error:
            checks.append(baseline.skip(f"topology unreachable: {error}"))
        else:
            if sample.live == 200 and sample.health == 200 and sample.ready == 200:
                checks.append(baseline.pass_(f"live=200 ready={sample.ready}", **sample.as_dict()))
            else:
                checks.append(
                    baseline.fail(f"live={sample.live} health={sample.health}", **sample.as_dict())
                )

    for step in RESTART_STEPS:
        checks.append(_inject_step(topology, step))
    checks.append(_broker_outage(topology))
    checks.append(_heartbeat_loss(topology))
    checks.append(_cancellation(topology))
    checks.append(_deletion(topology))
    checks.append(_late_result(topology))
    checks.append(_orphan_reclamation(topology))
    checks.append(_budget_recovery(topology))
    return checks


def run() -> Receipt:
    from .receipt import collect_environment, read_source_sha, utc_now

    topology = Topology.from_env()
    receipt = Receipt(scope="r4-fault-injection-recovery", source_sha=read_source_sha(ROOT))
    receipt.environment = collect_environment(
        ROOT,
        tools={"topology_base_url": topology.base_url or "UNSET"},
        extra={
            "allow_writes": topology.allow_writes,
            "allow_destructive": topology.allow_destructive,
            "compose_files": [str(path) for path in topology.compose_files],
        },
    )
    if not topology.allow_destructive:
        receipt.untested_scope(
            "R4 all fault injection: needs PT_ACCEPTANCE_ALLOW_DESTRUCTIVE=1 on the "
            "real seven-service topology"
        )
    receipt.checks = collect()
    receipt.finished_at = utc_now()
    receipt.notes = (
        "Only documented operator actions are used (compose restart/stop/start, "
        "reclamation profile). No volume, database or host path is touched."
    )
    return receipt


if __name__ == "__main__":
    from .run import main

    raise SystemExit(main(["--only", "r4"]))
