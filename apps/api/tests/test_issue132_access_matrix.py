"""Guard regressions with controlled stored reports, never Android/scan evidence."""

import hashlib
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_capability_tokens import seed_job

# isort: split
# Keep application imports separate across editable-install layouts on Windows/Linux.
from privacytrace.auth import generate_capability_token
from privacytrace.config import ServerConfig
from privacytrace.main import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from deploy.acceptance.issue132.access_matrix import endpoints, run_matrix  # noqa: E402


@pytest.fixture
def isolated(tmp_path):
    def build(name):
        app = create_app(
            tmp_path / name, config=ServerConfig(mode="remote", rate_limit_per_minute=10000)
        )
        client = TestClient(app)
        draft = client.post("/api/v1/web/drafts", json={
            "name": "Controlled N05 target",
            "sources": [{"id": "policy", "title": "Private policy", "text": "We access location."}],
        }).json()
        token = draft["token"]
        report = seed_job(
            app.state.job_store, token_digest=hashlib.sha256(token.encode()).hexdigest()
        )
        target = {
            "draft_id": draft["id"], "job_id": report.job.id, "token": token,
            "source_id": "policy", "attempt_id": "a" * 32, "revision": draft["revision"],
            "evidence_id": report.evidence[0].id,
        }
        return app, client, target
    one, two = build("I"), build("J")
    yield one, two
    for app, client, _ in (one, two):
        client.close()
        app.state.web_intake.close()


def files(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_all_19_endpoints_reject_five_credential_variants_without_mutating_target(isolated):
    app, client, target = isolated[0]
    attacker = client.post("/api/v1/web/drafts", json={
        "name": "Independent A", "sources": [{"id": "a", "title": "A"}],
    }).json()["token"]
    before = files(app.state.job_store.root)
    results = run_matrix(client, target, attacker)
    assert len(results) == 95
    assert all(row["status"] == "PASSED" for row in results)
    assert files(app.state.job_store.root) == before
    assert target["token"] not in str(results) and attacker not in str(results)


def test_other_instance_capability_fails_even_when_job_id_collides(isolated):
    # seed_job intentionally gives both stores the SAME known job ID. A 404
    # from a random, absent ID would not prove capability isolation.
    (_, _, first), (app, client, target) = isolated
    assert first["job_id"] == target["job_id"]
    assert first["token"] != target["token"]
    before = files(app.state.job_store.root)
    results = run_matrix(client, target, first["token"])
    assert len(results) == 95 and all(row["status"] == "PASSED" for row in results)
    assert files(app.state.job_store.root) == before


def test_original_instance_ids_are_not_accepted_by_the_other_store(isolated):
    for source, destination in (isolated, tuple(reversed(isolated))):
        _, _, first = source
        app, client, target = destination
        before = files(app.state.job_store.root)
        for endpoint in endpoints(first):
            response = client.request(
                endpoint.method, endpoint.path,
                headers={"Authorization": "Bearer " + first["token"]},
                **({"json": endpoint.body} if endpoint.body is not None else {}),
            )
            assert response.status_code == (404 if "/web/drafts/" in endpoint.path else 403)
            assert first["token"] not in response.text and target["token"] not in response.text
        assert files(app.state.job_store.root) == before


def test_remote_management_settings_and_job_listing_are_forbidden(isolated):
    _, client, target = isolated[0]
    for headers in ({}, {"Authorization": "Bearer " + target["token"]}):
        for method, path in (
            ("GET", "/api/v1/web/settings"), ("POST", "/api/v1/web/settings"),
            ("GET", "/api/v1/jobs"),
        ):
            response = client.request(method, path, headers=headers, json={})
            assert response.status_code == 403
            assert target["token"] not in response.text


def test_route_inventory_cannot_silently_miss_a_new_task_endpoint(isolated):
    app, _, target = isolated[0]
    actual = {(method, route.path.format(
        draft_id=target["draft_id"], job_id=target["job_id"], source_id=target["source_id"],
        attempt_id=target["attempt_id"], evidence_id=target["evidence_id"],
    )) for route in app.routes for method in getattr(route, "methods", set())
        if "{draft_id}" in route.path or "{job_id}" in route.path}
    matrix = {(row.method, row.path) for row in endpoints(target)}
    # DELETE draft is installed only by DurableWebIntake; this in-process
    # fixture tests its pre-routing guard, not that handler or resource cleanup.
    conditional = {("DELETE", "/api/v1/web/drafts/" + target["draft_id"])}
    assert matrix - actual == conditional
    assert actual - matrix == set()


@pytest.mark.parametrize("failure", ["wrong_code", "leaked_body", "mutation", "transport"])
def test_collector_fails_closed_and_stops_after_first_bad_observation(isolated, failure):
    _, client, target = isolated[0]
    attacker, _ = generate_capability_token()

    class BrokenBoundary:
        writes = 0
        changed = False

        def get(self, *args, **kwargs):
            if self.changed and failure == "transport":
                raise httpx.ConnectError("Private transport diagnostics must stay private")
            response = client.get(*args, **kwargs)
            if self.changed and failure == "mutation":
                return httpx.Response(200, json={"unexpected": "changed target"})
            return response

        def request(self, *args, **kwargs):
            self.writes += 1
            self.changed = True
            if failure == "wrong_code":
                return httpx.Response(200, json={"detail": "Draft capability token required"})
            if failure == "leaked_body":
                return httpx.Response(401, json={"detail": "Draft capability token required",
                                                "private": target["token"]})
            return client.request(*args, **kwargs)

    boundary = BrokenBoundary()
    results = run_matrix(boundary, target, attacker)
    assert len(results) == boundary.writes == 1
    assert results[0]["status"] == "FAILED"
    assert target["token"] not in str(results)


def test_bad_owner_precondition_is_never_counted_as_a_rejection_pass(isolated):
    _, client, target = isolated[0]
    attacker, _ = generate_capability_token()
    with pytest.raises(ValueError, match="Owner read precondition"):
        run_matrix(client, {**target, "evidence_id": "absent"}, attacker)


def test_probe_transport_failure_is_recorded_without_private_diagnostics(isolated):
    _, client, target = isolated[0]
    attacker, _ = generate_capability_token()

    class BrokenTransport:
        get = client.get

        def request(self, *args, **kwargs):
            raise httpx.ConnectError("PRIVATE diagnostics " + target["token"])

    results = run_matrix(BrokenTransport(), target, attacker)
    assert len(results) == 1 and results[0]["status"] == "FAILED"
    assert results[0]["actual_http"] is None
    assert "PRIVATE" not in str(results) and target["token"] not in str(results)
