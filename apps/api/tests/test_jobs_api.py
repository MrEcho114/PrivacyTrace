from fastapi.testclient import TestClient

from privacytrace.models import EvaluationInput
from privacytrace.resources import read_json, taxonomy


def controlled_bundle():
    """Controlled contract facts only, not proof of scanning an actual APK.

    Tests supply trusted local fixtures because HTTP intentionally has no job-upload
    endpoint. Remove every synthetic-only mapping before selecting the APK contract.
    Actual binary scanner coverage lives at the agreed CLI acceptance seam.
    """
    data = read_json("samples/demo/evaluation-input.json")
    synthetic_rules = {r["rule_id"] for r in taxonomy()["api_mappings"] if r.get("synthetic_only")}
    removed = {
        e["id"] for e in data["evidence"] if e.get("api_call", {}).get("rule_id") in synthetic_rules
    }
    data["evidence"] = [e for e in data["evidence"] if e["id"] not in removed]
    data["behaviors"] = [
        b for b in data["behaviors"] if not removed.intersection(b["evidence_ids"])
    ]
    data["job"]["input_mode"] = "APK"
    data["job"]["source_origin"] = "CONTROLLED"
    return EvaluationInput.model_validate(data)


def seed(store):
    bundle = controlled_bundle()
    return store.save(
        bundle,
        dict(
            name="controlled APK contract fixture only",
            package_name="org.privacytrace.demo",
            version_name="1",
            version_code=1,
            apk_sha256="a" * 64,
            permissions=[],
            dex_entries=["classes.dex"],
        ),
        dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[]),
        {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"},
    )


def test_saved_job_report_survives_app_restart(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(create_app(store_root=tmp_path))
    assert client.get("/api/v1/jobs").json()["jobs"][0]["id"] == report.job.id
    response = client.get(f"/api/v1/jobs/{report.job.id}/report")
    assert response.status_code == 200
    assert response.json()["demo"] is False
    assert response.json()["sample"]["apk_sha256"] == "a" * 64
    assert response.json()["result"]["issues"][0]["status"] == "CATEGORY_MATCH"


def test_review_recomputes_and_invalid_edit_does_not_replace_report(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)
    url = f"/api/v1/jobs/{report.job.id}/reviews"
    claim = report.policy_claims[0].model_dump(mode="json")
    claim["polarity"] = "NEGATIVE"
    response = client.post(
        url,
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "actor": "operator",
            "reason": "quote check",
            "note": "not a signed review",
            "claim": claim,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["issues"][0]["status"] == "AMBIGUOUS_DISCLOSURE"
    assert data["reviews"][0]["old_result"]["issues"][0]["status"] == "CATEGORY_MATCH"
    assert data["reviews"][0]["new_claim"]["polarity"] == "NEGATIVE"
    assert data["policy_documents"][0]["review_status"] == "UNREVIEWED"
    assert data["policy_documents"][0]["extraction_status"] == "PARTIAL"
    claim["evidence_ids"] = ["invented"]
    rejected = client.post(
        url,
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "operator", "reason": "bad", "note": "", "claim": claim},
    )
    assert rejected.status_code == 409
    assert client.get(f"/api/v1/jobs/{report.job.id}/report").json() == data


def test_http_write_requires_local_header_origin_and_cannot_create_jobs(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)
    url = f"/api/v1/jobs/{report.job.id}/reviews"
    body = {"actor": "operator", "reason": "note only", "note": "check later"}
    assert client.post(url, json=body).status_code == 403
    assert (
        client.post(
            url, json=body, headers={"X-PrivacyTrace-Local": "1", "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            url, json=body, headers={"X-PrivacyTrace-Local": "1", "Host": "public.example"}
        ).status_code
        == 400  # TrustedHost rejects DNS-rebinding requests before the write route.
    )
    assert client.post("/api/v1/jobs", json={"input_mode": "APK"}).status_code == 405
    response = client.post(
        url, json=body, headers={"X-PrivacyTrace-Local": "1", "Origin": "http://localhost:5173"}
    )
    assert response.status_code == 200
    assert (
        response.json()["reviews"][0]["old_result"] == response.json()["reviews"][0]["new_result"]
    )


def test_failed_and_cancelled_jobs_are_queryable_and_never_overwritten(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    failed = report.job.model_copy(
        update={"id": "failed-job", "state": "FAILED", "error": "DEX parse failed"}
    )
    app.state.job_store.save_job(failed)
    queued = report.job.model_copy(update={"id": "queued-job", "state": "QUEUED"})
    app.state.job_store.save_job(queued)
    client = TestClient(app)
    assert client.get("/api/v1/jobs/failed-job").json()["error"] == "DEX parse failed"
    assert client.get("/api/v1/jobs/failed-job/report").status_code == 409
    assert (
        client.post("/api/v1/jobs/queued-job/cancel", headers={"X-PrivacyTrace-Local": "1"}).json()[
            "state"
        ]
        == "CANCELLED"
    )
    app.state.job_store.save_job(queued.model_copy(update={"state": "SUCCEEDED"}))
    assert client.get("/api/v1/jobs/queued-job").json()["state"] == "CANCELLED"
    assert client.get("/api/v1/jobs/%2E%2E%5Csecret").status_code == 409


def test_corrupt_and_oversized_storage_rejects_without_exposing_payload(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)
    path = tmp_path / f"{report.job.id}.json"
    path.write_text('{"secret":"not validated"}', encoding="utf-8")
    response = client.get(f"/api/v1/jobs/{report.job.id}/report")
    assert response.status_code == 409
    assert "secret" not in response.text
    path.write_bytes(b"x" * (33 * 1024 * 1024))
    assert client.get(f"/api/v1/jobs/{report.job.id}").status_code == 409


def test_storage_record_limit_and_cancelled_scan_cannot_publish(tmp_path):
    import pytest

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    queued = report.job.model_copy(update={"id": "cancelled-scan", "state": "QUEUED"})
    app.state.job_store.save_job(queued)
    client = TestClient(app)
    client.post("/api/v1/jobs/cancelled-scan/cancel", headers={"X-PrivacyTrace-Local": "1"})
    bundle = controlled_bundle()
    bundle.job.id = "cancelled-scan"
    with pytest.raises(ValueError, match="Cancelled"):
        app.state.job_store.save(
            bundle, report.sample.model_dump(), report.coverage.model_dump(), report.tools
        )
    assert client.get("/api/v1/jobs/cancelled-scan").json()["state"] == "CANCELLED"


def test_malicious_record_identity_is_not_returned_as_requested_job(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    seed(app.state.job_store)
    data = (tmp_path / "demo-job-001.json").read_text(encoding="utf-8")
    (tmp_path / "different-job.json").write_text(data, encoding="utf-8")
    assert TestClient(app).get("/api/v1/jobs/different-job").status_code == 409


def test_review_rejects_oversized_request_before_loading_record(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)
    response = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        content=b"x" * (512 * 1024 + 1),
    )
    assert response.status_code == 413


def test_report_rejects_metadata_mismatch_and_impossible_complete_coverage(tmp_path):
    import pytest

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    bundle = controlled_bundle()
    metadata = dict(
        name="controlled APK contract fixture only",
        package_name="wrong.app",
        version_name="1",
        version_code=1,
        apk_sha256="a" * 64,
        permissions=[],
        dex_entries=["classes.dex"],
    )
    coverage = dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[])
    with pytest.raises(ValueError):
        app.state.job_store.save(
            bundle, metadata, coverage, {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"}
        )
    metadata["package_name"] = bundle.job.package_name
    coverage["failed_dex"] = ["classes.dex"]
    with pytest.raises(ValueError):
        app.state.job_store.save(
            bundle, metadata, coverage, {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"}
        )
    assert TestClient(app).get("/api/v1/jobs").json() == {"jobs": []}


def test_review_history_cannot_be_reset_by_republishing_scan(tmp_path):
    import pytest

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)
    client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "operator", "reason": "check", "note": "keep this"},
    )
    with pytest.raises(ValueError):
        seed(app.state.job_store)
    app.state.job_store.save_job(report.job.model_copy(update={"state": "STATIC_ANALYSIS"}))
    data = client.get(f"/api/v1/jobs/{report.job.id}/report").json()
    assert data["reviews"][0]["note"] == "keep this"
    assert data["job"]["state"] == "SUCCEEDED"


def _append_reviews_in_process(root, barrier, results, count):
    from pathlib import Path

    from privacytrace.main import create_app

    client = TestClient(create_app(store_root=Path(root)))
    barrier.wait(timeout=20)
    codes = []
    for index in range(count):
        codes.append(
            client.post(
                "/api/v1/jobs/demo-job-001/reviews",
                headers={"X-PrivacyTrace-Local": "1"},
                json={
                    "actor": str(__import__("os").getpid()),
                    "reason": "process concurrency",
                    "note": str(index),
                },
            ).status_code
        )
    results.put(codes)


def test_independent_http_processes_preserve_all_review_events(tmp_path):
    import multiprocessing

    from privacytrace.main import create_app

    seed(create_app(store_root=tmp_path).state.job_store)
    ctx = multiprocessing.get_context("spawn")
    barrier, results = ctx.Barrier(4), ctx.Queue()
    processes = [
        ctx.Process(target=_append_reviews_in_process, args=(str(tmp_path), barrier, results, 8))
        for _ in range(4)
    ]
    for process in processes:
        process.start()
    try:
        responses = [results.get(timeout=40) for _ in processes]
        assert all(code == 200 for codes in responses for code in codes)
    finally:
        for process in processes:
            process.join(timeout=15)
            if process.is_alive():
                process.terminate()
                process.join()
    client = TestClient(create_app(store_root=tmp_path))
    report = client.get("/api/v1/jobs/demo-job-001/report").json()
    assert len(report["reviews"]) == 32
    assert len({(event["actor"], event["note"]) for event in report["reviews"]}) == 32


def test_tampered_synthetic_job_cannot_be_served_as_non_demo_report(tmp_path):
    import json

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    seed(app.state.job_store)
    path = tmp_path / "demo-job-001.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["job"]["input_mode"] = "SYNTHETIC"
    data["bundle"]["job"]["input_mode"] = "SYNTHETIC"
    path.write_text(json.dumps(data), encoding="utf-8")
    client = TestClient(create_app(store_root=tmp_path))
    assert client.get("/api/v1/jobs/demo-job-001/report").status_code == 409
    assert client.get("/api/v1/jobs/demo-job-001").status_code == 409


def _cancel_jobs_in_process(root, barrier, results, count):
    from pathlib import Path

    from privacytrace.main import create_app

    client = TestClient(create_app(store_root=Path(root)))
    barrier.wait(timeout=20)
    results.put(
        (
            "cancel",
            [
                client.post(
                    f"/api/v1/jobs/race-{i}/cancel", headers={"X-PrivacyTrace-Local": "1"}
                ).status_code
                for i in range(count)
            ],
        )
    )


def _publish_controlled_jobs_in_process(root, barrier, results, count):
    from pathlib import Path

    from privacytrace.job_store import JobStore

    store = JobStore(Path(root))
    barrier.wait(timeout=20)
    states = []
    for index in range(count):
        bundle = controlled_bundle()
        bundle.job.id = f"race-{index}"
        try:
            store.save(
                bundle,
                dict(
                    name="controlled concurrency fixture",
                    package_name=bundle.job.package_name,
                    version_name="1",
                    version_code=bundle.job.version_code,
                    apk_sha256="a" * 64,
                    permissions=[],
                    dex_entries=["classes.dex"],
                ),
                dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[]),
                {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"},
            )
            states.append("SUCCEEDED")
        except ValueError:
            states.append("CANCELLED")
    results.put(("publish", states))


def test_http_cancel_racing_trusted_publication_never_erases_report(tmp_path):
    import multiprocessing

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    count = 12
    for index in range(count):
        job = controlled_bundle().job.model_copy(update={"id": f"race-{index}", "state": "QUEUED"})
        app.state.job_store.save_job(job)
    ctx = multiprocessing.get_context("spawn")
    barrier, results = ctx.Barrier(2), ctx.Queue()
    processes = [
        ctx.Process(target=target, args=(str(tmp_path), barrier, results, count))
        for target in (_cancel_jobs_in_process, _publish_controlled_jobs_in_process)
    ]
    for process in processes:
        process.start()
    try:
        outcomes = dict(results.get(timeout=40) for _ in processes)
    finally:
        for process in processes:
            process.join(timeout=15)
            if process.is_alive():
                process.terminate()
                process.join()
    client = TestClient(create_app(store_root=tmp_path))
    for index in range(count):
        state = client.get(f"/api/v1/jobs/race-{index}").json()["state"]
        report = client.get(f"/api/v1/jobs/race-{index}/report")
        if state == "SUCCEEDED":
            assert report.status_code == 200
            assert outcomes["cancel"][index] == 409
            assert outcomes["publish"][index] == "SUCCEEDED"
        else:
            assert state == "CANCELLED"
            assert report.status_code == 409
            assert outcomes["publish"][index] == "CANCELLED"


def test_linked_storage_lock_is_rejected_at_http_boundary(tmp_path):
    import os

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    seed(app.state.job_store)
    lock = tmp_path / ".lock"
    lock.unlink()
    other = tmp_path / "linked-target"
    other.write_text("0", encoding="utf-8")
    os.link(other, lock)
    assert TestClient(app).get("/api/v1/jobs").status_code == 409


def _hold_external_advisory_lock(path, ready, release):
    import os

    with open(path, "r+b", buffering=0) as handle:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        ready.set()
        release.wait(timeout=15)
        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_external_process_lock_timeout_returns_conflict_and_then_recovers(tmp_path):
    import multiprocessing

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    seed(app.state.job_store)
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    process = ctx.Process(
        target=_hold_external_advisory_lock, args=(str(tmp_path / ".lock"), ready, release)
    )
    process.start()
    try:
        assert ready.wait(timeout=15)
        response = TestClient(app).get("/api/v1/jobs")
        assert response.status_code == 409
        assert "timed out" not in response.text  # Do not expose local implementation paths.
    finally:
        release.set()
        process.join(timeout=15)
        if process.is_alive():
            process.terminate()
            process.join()
    assert TestClient(app).get("/api/v1/jobs").status_code == 200


def test_concurrent_job_creation_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone

    from privacytrace.job_store import JobStore
    from privacytrace.models import AnalysisJob

    store = JobStore(tmp_path)
    job_id = "concurrent-job-target"

    def attempt_create(idx):
        job = AnalysisJob(
            id=job_id,
            sample_id=f"sample-{idx}",
            input_mode="APK",
            source_origin="REAL_SCAN",
            state="QUEUED",
            ruleset_version="0.3",
            created_at=datetime.now(timezone.utc),
        )
        try:
            store.create_if_absent(job)
            return "SUCCESS"
        except ValueError as exc:
            if "Job already exists" in str(exc):
                return "ALREADY_EXISTS"
            raise

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt_create, range(16)))

    assert results.count("SUCCESS") == 1
    assert results.count("ALREADY_EXISTS") == 15
    loaded = store.get(job_id)
    assert loaded.id == job_id
    assert loaded.state == "QUEUED"


def test_real_job_named_demo_accessible_and_distinct_from_synthetic_demo(tmp_path):
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    bundle = controlled_bundle()
    bundle.job.id = "demo"
    bundle.job.package_name = "org.privacytrace.real"
    bundle.job.version_code = 1
    app.state.job_store.save(
        bundle,
        dict(
            name="real job named demo",
            package_name="org.privacytrace.real",
            version_name="1.0",
            version_code=1,
            apk_sha256="b" * 64,
            permissions=[],
            dex_entries=["classes.dex"],
        ),
        dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[]),
        {"scanner": "CONTROLLED"},
    )

    client = TestClient(app)
    # 1. Real job API responds
    res_job = client.get("/api/v1/jobs/demo")
    assert res_job.status_code == 200
    assert res_job.json()["id"] == "demo"

    # 2. Real job report responds with demo: false
    res_report = client.get("/api/v1/jobs/demo/report")
    assert res_report.status_code == 200
    assert res_report.json()["demo"] is False
    assert res_report.json()["sample"]["package_name"] == "org.privacytrace.real"

    # 3. Synthetic demo endpoint still serves synthetic fixture with demo: true
    res_demo = client.get("/api/v1/demo/report")
    assert res_demo.status_code == 200
    assert res_demo.json()["demo"] is True
    assert res_demo.json()["sample"]["package_name"] == "org.privacytrace.demo"


def test_sample_metadata_version_name_none_and_long_persist(tmp_path):
    from privacytrace.job_store import JobStore

    store = JobStore(tmp_path)
    bundle_1 = controlled_bundle()
    bundle_1.job.id = "job-version-none"
    bundle_1.job.package_name = "org.privacytrace.nonever"
    bundle_1.job.version_code = 1
    report_1 = store.save(
        bundle_1,
        dict(
            name="None version test",
            package_name="org.privacytrace.nonever",
            version_name=None,
            version_code=1,
            apk_sha256="c" * 64,
            permissions=[],
            dex_entries=["classes.dex"],
        ),
        dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[]),
        {"scanner": "CONTROLLED"},
    )
    assert report_1.sample.version_name is None
    loaded_1 = store.report("job-version-none")
    assert loaded_1.sample.version_name is None

    long_ver = "v" * 500
    bundle_2 = controlled_bundle()
    bundle_2.job.id = "job-version-long"
    bundle_2.job.package_name = "org.privacytrace.longver"
    bundle_2.job.version_code = 2
    report_2 = store.save(
        bundle_2,
        dict(
            name="Long version test",
            package_name="org.privacytrace.longver",
            version_name=long_ver,
            version_code=2,
            apk_sha256="d" * 64,
            permissions=[],
            dex_entries=["classes.dex"],
        ),
        dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[]),
        {"scanner": "CONTROLLED"},
    )
    assert report_2.sample.version_name == long_ver
    loaded_2 = store.report("job-version-long")
    assert loaded_2.sample.version_name == long_ver


def test_old_report_gets_conservative_coverage_scope_without_rewriting_facts(tmp_path):
    import json

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    saved = seed(app.state.job_store)
    client = TestClient(app)
    before = client.get(f"/api/v1/jobs/{saved.job.id}/report").json()
    path = tmp_path / f"{saved.job.id}.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    for field in ("scope", "behavior_detection", "behavior_limitations"):
        legacy["coverage"].pop(field)
    path.write_text(json.dumps(legacy), encoding="utf-8")
    response = TestClient(create_app(store_root=tmp_path)).get(
        f"/api/v1/jobs/{saved.job.id}/report"
    )
    assert response.status_code == 200
    report = response.json()
    assert report["coverage"]["status"] == "COMPLETE"
    assert report["coverage"]["scope"] == "DEX_ENTRIES"
    assert report["coverage"]["behavior_detection"] == "LIMITED_RULE_BASED_STATIC"
    assert any("规则" in item for item in report["coverage"]["behavior_limitations"])
    for field in ("result", "evidence", "behaviors", "policy_documents", "policy_claims"):
        assert report[field] == before[field]


def test_historical_report_uses_its_rules_after_active_taxonomy_advances(tmp_path, monkeypatch):
    from copy import deepcopy

    from privacytrace import resources
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    original = seed(app.state.job_store).model_dump(mode="json")
    old_rules = taxonomy()
    newer = deepcopy(old_rules)
    newer["version"] = "0.4.0"
    newer["data_types"] = []
    newer["api_mappings"] = []
    original_read = resources.read_json

    def resource(path):
        return newer if path == "rules/taxonomy.v0.4.json" else original_read(path)

    monkeypatch.setattr(resources, "read_json", resource)
    monkeypatch.setattr(resources, "ACTIVE_RULESET_VERSION", "0.4.0")
    monkeypatch.setattr(resources, "TAXONOMY_FILES",
                        {"0.3.0": "rules/taxonomy.v0.3.json", "0.4.0": "rules/taxonomy.v0.4.json"})
    client = TestClient(create_app(store_root=tmp_path))
    assert client.get("/api/v1/taxonomy").json()["version"] == "0.4.0"
    assert client.get("/api/v1/jobs").status_code == 200
    url = f"/api/v1/jobs/{original['job']['id']}"
    assert client.get(url).status_code == 200
    response = client.get(url + "/report")
    assert response.status_code == 200
    reloaded = response.json()
    # save() returns a LIVE_GENERATED report; reloading it over HTTP is a
    # PERSISTED_REPLAY of the same data. The origin and every evaluated field
    # must be identical -- only the delivery path differs.
    assert original["delivery_mode"] == "LIVE_GENERATED"
    assert reloaded["delivery_mode"] == "PERSISTED_REPLAY"
    assert reloaded["job"] == original["job"]
    assert reloaded["result"] == original["result"]
    assert reloaded["job"]["source_origin"] == original["job"]["source_origin"]
    assert {
        k: v for k, v in reloaded.items() if k != "delivery_mode"
    } == {
        k: v for k, v in original.items() if k != "delivery_mode"
    }


def test_reloaded_real_scan_keeps_origin_but_becomes_persisted_replay(tmp_path):
    """A stored job keeps its origin across reloads; only its delivery mode changes.

    This is the distinction the review asked for: `source_origin` is immutable
    data provenance, while `delivery_mode` reports how the report was loaded
    this time. Without it, a report reloaded after a restart would still claim
    to be a freshly produced on-device scan.
    """
    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    fresh = seed(app.state.job_store)
    original_origin = fresh.job.source_origin
    assert fresh.delivery_mode == "LIVE_GENERATED"

    # A brand-new client over the same store models a process restart.
    client = TestClient(create_app(store_root=tmp_path))
    reloaded = client.get(f"/api/v1/jobs/{fresh.job.id}/report").json()
    assert reloaded["job"]["source_origin"] == original_origin, "Origin must not change on reload"
    assert reloaded["delivery_mode"] == "PERSISTED_REPLAY", "A reloaded report is not a live generation"

    # Reviewing a stored report is also a replay, not a fresh generation.
    reviewed = client.post(
        f"/api/v1/jobs/{fresh.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "local", "reason": "spot check"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["delivery_mode"] == "PERSISTED_REPLAY"
    assert reviewed.json()["job"]["source_origin"] == original_origin


def test_demo_report_is_a_live_generation():
    """The demo envelope is assembled per response, never replayed from storage."""
    from privacytrace.main import create_app

    client = TestClient(create_app())
    body = client.get("/api/v1/demo/report").json()
    assert body["delivery_mode"] == "LIVE_GENERATED"
    assert body["job"]["source_origin"] == "SYNTHETIC"


def test_historical_report_rejects_unknown_ruleset_without_fallback(tmp_path):
    import json

    from privacytrace.main import create_app

    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    path = tmp_path / (report.job.id + ".json")
    record = json.loads(path.read_bytes())
    record["job"]["ruleset_version"] = "999.0.0"
    record["bundle"]["job"]["ruleset_version"] = "999.0.0"
    path.write_text(json.dumps(record), encoding="utf-8")
    client = TestClient(create_app(store_root=tmp_path))
    assert client.get(f"/api/v1/jobs/{report.job.id}/report").status_code == 409
