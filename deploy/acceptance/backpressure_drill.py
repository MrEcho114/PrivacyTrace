"""Hold the actual consumer, measure queueing/refusal, then drain at concurrency 1."""

from .metrics import Sampler
from .r2_business_loop import Fixtures, create_scope, poll_job, start_job, upload_apk
from .topology import request


def drill(lab, topology):
    fixture = Fixtures.build()
    scopes = []
    # The real per-IP retained-draft budget is three. This is not raised by the test.
    for index in range(3):
        scope = create_scope(topology, "queued-canary-" + str(index), "Synthetic queue policy.")
        assert upload_apk(topology, scope, fixture.single_apk).status == 200
        scopes.append(scope)
    refused = request(
        topology,
        "/api/v1/web/drafts",
        method="POST",
        json_body={
            "name": "over-capacity",
            "sources": [{"id": "policy", "title": "Synthetic policy"}],
        },
    )
    assert refused.status in {409, 429, 503}
    lab.run("stop", "worker")
    try:
        for scope in scopes:
            assert start_job(topology, scope).status == 200 and scope.job_id
        states = [
            request(topology, f"/api/v1/jobs/{s.job_id}", token=s.token).json["state"]
            for s in scopes
        ]
        assert states == ["QUEUED"] * 3
        with Sampler(lab) as sampler:
            lab.run("start", "worker")
            completed = [
                poll_job(topology, scope, budget_s=180, interval_s=0.2)["state"] for scope in scopes
            ]
    finally:
        lab.run("start", "worker")
    assert completed == ["SUCCEEDED"] * 3
    metrics = sampler.result()
    assert metrics["scanner_sampled_peak_concurrency"] == 1
    return {
        "accepted_queue_depth": 3,
        "refusal_boundary": "per-IP retained-draft quota; queue saturation was not tested",
        "fourth_scope_refusal": refused.status,
        "terminal_states": completed,
        **metrics,
    }
