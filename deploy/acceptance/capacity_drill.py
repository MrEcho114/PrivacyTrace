"""Exhaust the admission, queue and disk budgets as three separate experiments.

Each budget is enforced by a different seam of the product, and a single client
cannot reach all of them: the per-client retained-draft quota stops it first. The
drill therefore drives several real client containers, one identity each, on the
laboratory network. Forwarding headers are not forged; the request guard rejects
them from untrusted peers, and the gateway would rewrite them anyway.

Capability tokens are returned to this process only so it can poll and clean up.
They never enter evidence dictionaries, receipts, or logs.
"""

import json
import os
import time
import uuid

from .metrics import Sampler
from .operations_drills import disk_full
from .provision import ROOT, execute
from .r2_business_loop import Fixtures
from .topology import request

PROBE = ROOT / "deploy/acceptance/client_probe.py"
# Declared budgets: apps/api/src/privacytrace/web_intake.py MAX_DRAFTS_PER_IP and
# MAX_DRAFTS, apps/api/src/privacytrace/durable_intake.py MAX_ACTIVE_JOBS.
MAX_CLIENT_DRAFTS = 3
MAX_DRAFTS = 12
MAX_ACTIVE_JOBS = 4

_FIXTURE = None


def _fixture():
    global _FIXTURE
    if _FIXTURE is None:
        _FIXTURE = Fixtures.build().single_apk
    return _FIXTURE


def _prepare(lab):
    """Stage the probe script and one real fixture APK for the client containers."""
    directory = lab.root / "probe"
    directory.mkdir(exist_ok=True)
    os.chmod(directory, 0o755)
    (directory / "client_probe.py").write_bytes(PROBE.read_bytes())
    (directory / "fixture.apk").write_bytes(_fixture())
    for entry in directory.iterdir():
        os.chmod(entry, 0o644)
    return directory


def _docker(lab, argv, *, what, timeout=600):
    """Run a docker command, keeping its own diagnostic when it refuses."""
    try:
        return execute(argv, timeout=timeout)
    except RuntimeError as error:
        # stderr stays out of receipts; only the last line reaches the collector log, with
        # the private laboratory path normalized away, so a refusal is diagnosable.
        stderr = getattr(error, "stderr", "") or ""
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        detail = " ".join(lines[-1].split()) if lines else str(error)
        detail = detail.replace(str(lab.root), "<lab-state>")
        print(f"capacity drill: {what} refused: {detail}", flush=True)
        raise RuntimeError(f"{what} refused: {detail}") from None


def _api_network(lab):
    """Resolve the laboratory's api network from its compose label, not from its name."""
    identifiers = _docker(
        lab,
        [
            "docker",
            "network",
            "ls",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={lab.project}",
        ],
        what="network discovery",
    ).split()
    networks = (
        json.loads(
            _docker(lab, ["docker", "network", "inspect", *identifiers], what="network inspect")
        )
        if identifiers
        else []
    )
    for network in networks:
        if str(network.get("Name", "")).endswith("_api"):
            return network
    names = sorted(str(network.get("Name", "")) for network in networks)
    raise RuntimeError(f"laboratory {lab.project} has no api network: {names}")


def _identity(lab, topology, directory, steps, *, network=None, address=None):
    """Run one client identity in its own container and return its step results."""
    plan = {
        "base_url": "http://api:8000",
        "host": topology.host,
        "apk": "/probe/fixture.apk",
        "steps": steps,
    }
    options = [f"--network={network or f'{lab.project}_api'}"]
    if address:
        # The API keys admission on the peer address, so each identity claims its own
        # address. `compose run` cannot express a fixed address, hence plain docker.
        options.append(f"--ip={address}")
    output = _docker(
        lab,
        [
            "docker",
            "run",
            "--rm",
            *options,
            "--entrypoint",
            "/opt/venv/bin/python",
            "--volume",
            f"{directory}:/probe:ro",
            lab.state["images"]["api"],
            "/probe/client_probe.py",
            json.dumps(plan),
        ],
        what="client container",
    )
    for line in reversed(str(output).strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    raise RuntimeError("client probe returned no result")


def _addresses(network, count):
    """Reserve distinct free addresses on the laboratory bridge for client identities."""
    raw = network
    subnet = raw["IPAM"]["Config"][0]["Subnet"]
    base = subnet.rsplit(".", 1)[0]
    taken = {entry.get("IPv4Address", "").split("/")[0] for entry in raw["Containers"].values()}
    start = _CLIENT_FIRST + int(uuid.uuid4().hex[:4], 16) % (_CLIENT_LAST - _CLIENT_FIRST)
    chosen = []
    for offset in range(_CLIENT_LAST - _CLIENT_FIRST):
        host = _CLIENT_FIRST + (start - _CLIENT_FIRST + offset) % (_CLIENT_LAST - _CLIENT_FIRST)
        address = f"{base}.{host}"
        if address in taken:
            continue
        chosen.append(address)
        if len(chosen) == count:
            return chosen
    raise RuntimeError("no free client address on the laboratory bridge")


# Addresses well above the compose-assigned ones, below the bridge's upper range.
_CLIENT_FIRST = 40
_CLIENT_LAST = 240


def _step(result, operation, index=None):
    matches = [item for item in result["steps"] if item["op"] == operation]
    return matches[-1] if index is None else matches[index]


def _scopes(result):
    """Collect the drafts one identity created, keyed by the name in the plan."""
    found = {}
    for item in result["steps"]:
        if item["op"] == "draft" and item.get("draft_id"):
            found[item["draft"]] = {
                "draft_id": item["draft_id"],
                "token": item.get("token", ""),
                "job_id": "",
            }
        elif item["op"] == "start" and item.get("job_id"):
            target = found.get(item["draft"])
            if target is not None:
                target["job_id"] = item["job_id"]
    return found


def _wait(topology, job_id, token, budget_s=240):
    deadline = time.monotonic() + budget_s
    state = ""
    while time.monotonic() < deadline:
        reply = request(topology, f"/api/v1/jobs/{job_id}", token=token)
        if reply.status == 200 and isinstance(reply.json, dict):
            state = str(reply.json.get("state"))
            if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                return state
        time.sleep(0.5)
    return state or "UNKNOWN"


def _drop(topology, scope):
    if scope["token"]:
        request(
            topology, f"/api/v1/web/drafts/{scope['draft_id']}", method="DELETE",
            token=scope["token"],
        )


def admission(lab, topology):
    """Per-client and whole-laboratory retained-draft admission budgets."""
    directory = _prepare(lab)
    started = time.monotonic()
    api = _api_network(lab)
    addresses = iter(_addresses(api, MAX_DRAFTS // MAX_CLIENT_DRAFTS + 2))
    names = [f"cap-client-{index}" for index in range(MAX_CLIENT_DRAFTS + 1)]
    first = _identity(
        lab,
        topology,
        directory,
        [{"op": "draft", "draft": name, "name": name} for name in names],
        network=api["Name"],
        address=next(addresses),
    )
    accepted = [_step(first, "draft", index) for index in range(MAX_CLIENT_DRAFTS)]
    refused = _step(first, "draft", MAX_CLIENT_DRAFTS)
    assert [item["status"] for item in accepted] == [200] * MAX_CLIENT_DRAFTS
    assert refused["status"] == 429 and refused["code"] == "CLIENT_DRAFT_QUOTA_REACHED"
    kept = list(_scopes(first).values())
    whole = None
    while whole is None:
        # Drafts created before this drill count against the laboratory budget, so
        # the observation records where the boundary was hit instead of assuming it.
        names = [f"cap-fill-{len(kept)}-{index}" for index in range(MAX_CLIENT_DRAFTS)]
        identity = _identity(
            lab,
            topology,
            directory,
            [{"op": "draft", "draft": name, "name": name} for name in names],
            network=api["Name"],
            address=next(addresses),
        )
        for index, name in enumerate(names):
            step = _step(identity, "draft", index)
            if step["status"] != 200:
                whole = step
                break
            kept.append(_scopes(identity)[name])
    try:
        assert whole["code"] == "DRAFT_QUOTA_REACHED", whole
        assert 0 <= MAX_DRAFTS - len(kept) < MAX_DRAFTS, len(kept)
    finally:
        for scope in kept:
            _drop(topology, scope)
    return {
        "client_draft_budget": MAX_CLIENT_DRAFTS,
        "client_refusal": {"status": refused["status"], "code": refused["code"]},
        "laboratory_draft_budget": MAX_DRAFTS,
        "admitted_drafts_before_refusal": len(kept),
        # Drafts already in the laboratory are not visible through the API; a clean
        # laboratory yields 0 here, and the evidence receipt records a clean run.
        "implied_existing_drafts": MAX_DRAFTS - len(kept),
        "laboratory_refusal": {
            "status": whole["status"],
            "code": whole["code"],
            "retry_after": whole.get("retry_after"),
        },
        "elapsed_s": round(time.monotonic() - started, 2),
    }


def queue(lab, topology):
    """Queue budget: hold the consumer, admit one job per identity, refuse the rest."""
    directory = _prepare(lab)
    started = time.monotonic()
    held = []
    refusal = None
    api = _api_network(lab)
    addresses = iter(_addresses(api, MAX_ACTIVE_JOBS + 1))
    lab.run("stop", "worker")
    try:
        for index in range(MAX_ACTIVE_JOBS + 1):
            name = f"cap-queue-{index}"
            result = _identity(
                lab,
                topology,
                directory,
                [
                    {"op": "draft", "draft": name, "name": name},
                    {"op": "upload", "draft": name},
                    {"op": "start", "draft": name},
                    {"op": "state", "draft": name},
                ],
                network=api["Name"],
                address=next(addresses),
            )
            observed = [_step(result, op)["status"] for op in ("draft", "upload")]
            assert observed == [200, 200], f"identity {index}: draft/upload returned {observed}"
            started_step = _step(result, "start")
            if started_step["status"] != 200:
                # Only the capacity boundary may end the loop: a malformed start (an
                # invalid idempotency key, a stale revision) also returns non-200 and
                # must never be mistaken for an exhausted budget.
                assert started_step["status"] == 429 and started_step["code"] == (
                    "ADMISSION_CAPACITY_REACHED"
                ), started_step
                # The budget was already partly spent (a previous drill may still hold
                # slots); the boundary itself is what this drill has to observe.
                refusal = started_step
                break
            scope = _scopes(result)[name]
            scope["state"] = _step(result, "state").get("state")
            held.append(scope)
        queued = [scope["state"] for scope in held]
        with Sampler(lab) as sampler:
            lab.run("start", "worker")
            completed = [_wait(topology, scope["job_id"], scope["token"]) for scope in held]
        metrics = sampler.result()
    finally:
        lab.run("start", "worker")
        for scope in held:
            _drop(topology, scope)
    assert held, "the admission budget refused the very first job"
    assert refusal is not None, "every start was admitted; the queue budget was not reached"
    assert refusal["status"] == 429 and refusal["code"] == "ADMISSION_CAPACITY_REACHED", refusal
    assert completed == ["SUCCEEDED"] * len(held)
    assert metrics["scanner_sampled_peak_concurrency"] == 1
    return {
        "active_job_budget": MAX_ACTIVE_JOBS,
        "accepted_queue_depth": len(held),
        # Slots already held before the drill are invisible through the API; a clean
        # laboratory yields 0 here.
        "implied_existing_active_jobs": MAX_ACTIVE_JOBS - len(held),
        "queued_states": queued,
        "refusal": {
            "status": refusal["status"],
            "code": refusal["code"],
            "retry_after": refusal.get("retry_after"),
        },
        "terminal_states": completed,
        "elapsed_s": round(time.monotonic() - started, 2),
        **metrics,
    }


def disk(lab, topology):
    """Test-disk budget: a size-limited materials volume refuses the next upload."""
    return disk_full(lab, topology)
