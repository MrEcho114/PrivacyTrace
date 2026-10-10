import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_jobs_api import controlled_bundle, seed

from privacytrace.main import create_app
from privacytrace.models import EvaluationResult
from privacytrace.runtime_models import ReviewEvent

# ==============================================================================
# 1. Optional note edge cases
# ==============================================================================


def test_review_note_omitted_key_defaults_to_empty_and_succeeds(tmp_path):
    """Verify that omitting the 'note' key in ReviewRequest defaults to empty string."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    response = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "challenger-agent", "reason": "test omitted note"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["reviews"]) == 1
    assert data["reviews"][0]["actor"] == "challenger-agent"
    assert data["reviews"][0]["reason"] == "test omitted note"
    assert data["reviews"][0]["note"] == ""

    # Verify persisted report
    persisted = client.get(f"/api/v1/jobs/{report.job.id}/report").json()
    assert persisted["reviews"][0]["note"] == ""


def test_review_note_empty_string_succeeds(tmp_path):
    """Verify that explicit note="" succeeds and persists."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    response = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "challenger-agent", "reason": "test empty string note", "note": ""},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reviews"][0]["note"] == ""


def test_review_note_whitespace_only_succeeds_and_preserves_content(tmp_path):
    """Verify whitespace-only notes (spaces, tabs, newlines) succeed without truncation."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    whitespace_note = "   \t\n  \r\n   "
    response = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "actor": "challenger-agent",
            "reason": "test whitespace note",
            "note": whitespace_note,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reviews"][0]["note"] == whitespace_note

    # Also test unicode and special characters in note
    unicode_note = "🛡️ 隐私核验备注 <script>alert('xss')</script> & special chars: \u202e\u200b"
    response2 = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "challenger-agent", "reason": "test unicode note", "note": unicode_note},
    )
    assert response2.status_code == 200
    assert response2.json()["reviews"][1]["note"] == unicode_note


def test_review_note_max_length_10000_succeeds(tmp_path):
    """Verify that a note of exactly 10,000 characters succeeds and persists accurately."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    long_note = "X" * 10000
    response = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "challenger-agent", "reason": "test 10k note", "note": long_note},
    )
    assert response.status_code == 200
    assert len(response.json()["reviews"][0]["note"]) == 10000
    assert response.json()["reviews"][0]["note"] == long_note

    persisted = client.get(f"/api/v1/jobs/{report.job.id}/report").json()
    assert len(persisted["reviews"][0]["note"]) == 10000


def test_review_note_10001_chars_cleanly_rejected_with_422(tmp_path):
    """Verify that a note of 10,001 characters is rejected with 422 and does not modify storage."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    too_long_note = "X" * 10001
    response = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "actor": "challenger-agent",
            "reason": "test 10001 chars note",
            "note": too_long_note,
        },
    )
    assert response.status_code == 422
    err_detail = response.json()["detail"]
    assert any("note" in str(err) for err in err_detail)

    # Storage must remain untouched
    persisted = client.get(f"/api/v1/jobs/{report.job.id}/report").json()
    assert len(persisted["reviews"]) == 0


# ==============================================================================
# 2. Review security & authority
# ==============================================================================


def test_review_authority_cannot_be_forged_by_client_payload(tmp_path):
    """Verify that client cannot forge ReviewEvent.authority in the request payload."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    forged_authorities = [
        "AUTHENTICATED_LOCAL_EVENT",
        "AUTHENTICATED_OPERATOR_SIGNATURE",
        "ROOT_AUTHORITY",
        "REVIEWED",
        # Even passing the exact string must be rejected due to extra='forbid'
        "UNAUTHENTICATED_LOCAL_EVENT",
    ]

    for spoofed in forged_authorities:
        response = client.post(
            f"/api/v1/jobs/{report.job.id}/reviews",
            headers={"X-PrivacyTrace-Local": "1"},
            json={
                "actor": "attacker",
                "reason": "privilege escalation attempt",
                "note": "spoof authority",
                "authority": spoofed,
            },
        )
        assert response.status_code == 422, (
            f"Expected 422 for authority='{spoofed}', got {response.status_code}"
        )
        assert "extra_forbidden" in response.text or "extra" in response.text

    # Verify that a legitimate review ALWAYS produces UNAUTHENTICATED_LOCAL_EVENT
    legit_res = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "operator", "reason": "legit audit", "note": "regular note"},
    )
    assert legit_res.status_code == 200
    event = legit_res.json()["reviews"][0]
    assert event["authority"] == "UNAUTHENTICATED_LOCAL_EVENT"

    persisted = client.get(f"/api/v1/jobs/{report.job.id}/report").json()
    assert persisted["reviews"][0]["authority"] == "UNAUTHENTICATED_LOCAL_EVENT"


def test_review_event_model_authority_type_constraint():
    """Verify that ReviewEvent model strictly enforces authority Literal."""
    dummy_result = EvaluationResult(job_id="j1", ruleset_version="0.3", issues=[])

    # Valid construction
    ev = ReviewEvent(
        actor="op",
        reason="check",
        note="",
        timestamp=datetime.now(timezone.utc),
        old_result=dummy_result,
        new_result=dummy_result,
        authority="UNAUTHENTICATED_LOCAL_EVENT",
    )
    assert ev.authority == "UNAUTHENTICATED_LOCAL_EVENT"

    # Construction with default
    ev_default = ReviewEvent(
        actor="op",
        reason="check",
        note="",
        timestamp=datetime.now(timezone.utc),
        old_result=dummy_result,
        new_result=dummy_result,
    )
    assert ev_default.authority == "UNAUTHENTICATED_LOCAL_EVENT"

    # Invalid authority must raise ValidationError
    with pytest.raises(ValidationError):
        ReviewEvent(
            actor="op",
            reason="check",
            note="",
            timestamp=datetime.now(timezone.utc),
            old_result=dummy_result,
            new_result=dummy_result,
            authority="AUTHENTICATED_SIGNATURE",
        )


def test_review_does_not_alter_policy_document_status_to_reviewed(tmp_path):
    """Verify that reviewing never alters policy document review_status to REVIEWED.

    1. If a document starts as UNREVIEWED, reviewing never promotes it to REVIEWED.
    2. If a document starts as REVIEWED (e.g. from upstream/import), claim review demotes
       it to UNREVIEWED and PARTIAL (local unauthenticated review cannot certify a document).
    3. Direct client injection of document status in payload is rejected with 422.
    """
    app = create_app(store_root=tmp_path)
    bundle = controlled_bundle()
    # Set all documents to UNREVIEWED initially
    for doc in bundle.policy_documents:
        doc.review_status = "UNREVIEWED"
        doc.extraction_status = "PARTIAL"
    report = app.state.job_store.save(
        bundle,
        dict(
            name="controlled APK contract fixture",
            package_name=bundle.job.package_name,
            version_name="1",
            version_code=1,
            apk_sha256="a" * 64,
            permissions=[],
            dex_entries=["classes.dex"],
        ),
        dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[]),
        {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"},
    )
    client = TestClient(app)

    # Check baseline status
    doc = report.policy_documents[0]
    assert doc.review_status == "UNREVIEWED"
    assert doc.extraction_status == "PARTIAL"

    # 1. Note-only review on UNREVIEWED doc: stays UNREVIEWED
    res_note = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "operator", "reason": "note review", "note": "document check"},
    )
    assert res_note.status_code == 200
    docs_after_note = res_note.json()["policy_documents"]
    for d in docs_after_note:
        assert d["review_status"] == "UNREVIEWED"
        assert d["review_status"] != "REVIEWED"

    # 2. Claim update review: affected doc explicitly stays/becomes UNREVIEWED and PARTIAL
    claim = report.policy_claims[0].model_dump(mode="json")
    claim["polarity"] = "NEGATIVE"
    res_claim = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "actor": "operator",
            "reason": "claim review",
            "note": "update polarity",
            "claim": claim,
        },
    )
    assert res_claim.status_code == 200
    docs_after_claim = res_claim.json()["policy_documents"]
    for d in docs_after_claim:
        assert d["review_status"] == "UNREVIEWED"
        assert d["review_status"] != "REVIEWED"
        assert d["extraction_status"] == "PARTIAL"
        assert d["extraction_status"] != "SUCCEEDED"

    # 3. Test that if a document had REVIEWED, review demotes it to UNREVIEWED
    app_reviewed = create_app(store_root=tmp_path / "reviewed_sub")
    report_reviewed = seed(app_reviewed.state.job_store)
    client_reviewed = TestClient(app_reviewed)
    assert report_reviewed.policy_documents[0].review_status == "REVIEWED"
    claim_rev = report_reviewed.policy_claims[0].model_dump(mode="json")
    claim_rev["polarity"] = "NEGATIVE"
    res_demote = client_reviewed.post(
        f"/api/v1/jobs/{report_reviewed.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "actor": "operator",
            "reason": "demote review",
            "note": "edit claim",
            "claim": claim_rev,
        },
    )
    assert res_demote.status_code == 200
    assert res_demote.json()["policy_documents"][0]["review_status"] == "UNREVIEWED"
    assert res_demote.json()["policy_documents"][0]["extraction_status"] == "PARTIAL"

    # 4. Client injection of documents field rejected
    res_inject = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={
            "actor": "operator",
            "reason": "forgery attempt",
            "note": "try injecting documents",
            "policy_documents": [{"id": doc.id, "review_status": "REVIEWED"}],
        },
    )
    assert res_inject.status_code == 422


def test_review_on_non_succeeded_job_rejected(tmp_path):
    """Verify that jobs not in SUCCEEDED state cannot be reviewed."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    # 1. Create a QUEUED job and cancel it
    queued = report.job.model_copy(update={"id": "job-to-cancel", "state": "QUEUED"})
    app.state.job_store.save_job(queued)
    cancel_res = client.post(
        "/api/v1/jobs/job-to-cancel/cancel", headers={"X-PrivacyTrace-Local": "1"}
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["state"] == "CANCELLED"

    # Attempt to review cancelled job
    res_cancelled = client.post(
        "/api/v1/jobs/job-to-cancel/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "operator", "reason": "review cancelled job"},
    )
    assert res_cancelled.status_code == 409

    # 2. Test FAILED job
    failed = report.job.model_copy(
        update={"id": "job-failed", "state": "FAILED", "error": "analysis crash"}
    )
    app.state.job_store.save_job(failed)
    res_failed = client.post(
        "/api/v1/jobs/job-failed/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "operator", "reason": "review failed job"},
    )
    assert res_failed.status_code == 409


# ==============================================================================
# 3. Atomic persistence & concurrency
# ==============================================================================


def test_concurrent_reviews_in_threadpool(tmp_path):
    """Verify concurrent thread reviews on the same job preserve all events."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)
    job_id = report.job.id

    worker_count = 10
    reviews_per_worker = 3
    total_reviews = worker_count * reviews_per_worker

    def worker_task(worker_id):
        results = []
        for i in range(reviews_per_worker):
            res = client.post(
                f"/api/v1/jobs/{job_id}/reviews",
                headers={"X-PrivacyTrace-Local": "1"},
                json={
                    "actor": f"thread-{worker_id}",
                    "reason": f"concurrency test w{worker_id} r{i}",
                    "note": f"payload-{worker_id}-{i}",
                },
            )
            results.append(res.status_code)
        return results

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        all_results = list(executor.map(worker_task, range(worker_count)))

    flattened = [code for r in all_results for code in r]
    assert all(code == 200 for code in flattened), (
        f"Failed status codes: {[c for c in flattened if c != 200]}"
    )

    persisted = client.get(f"/api/v1/jobs/{job_id}/report").json()
    assert len(persisted["reviews"]) == total_reviews

    persisted_notes = {r["note"] for r in persisted["reviews"]}
    expected_notes = {
        f"payload-{w}-{i}" for w in range(worker_count) for i in range(reviews_per_worker)
    }
    assert persisted_notes == expected_notes


def _worker_process_review(root_str, job_id, worker_id, count, barrier, queue):
    from fastapi.testclient import TestClient

    from privacytrace.main import create_app

    client = TestClient(create_app(store_root=Path(root_str)))
    barrier.wait(timeout=20)
    codes = []
    for i in range(count):
        res = client.post(
            f"/api/v1/jobs/{job_id}/reviews",
            headers={"X-PrivacyTrace-Local": "1"},
            json={
                "actor": f"proc-{worker_id}",
                "reason": "multiprocess review",
                "note": f"proc-note-{worker_id}-{i}",
            },
        )
        codes.append(res.status_code)
    queue.put((worker_id, codes))


def test_concurrent_reviews_in_multiprocess(tmp_path):
    """Verify that multiple processes submitting reviews simultaneously all commit atomically."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    job_id = report.job.id

    num_processes = 4
    reviews_per_proc = 5
    total_reviews = num_processes * reviews_per_proc

    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(num_processes)
    queue = ctx.Queue()

    procs = [
        ctx.Process(
            target=_worker_process_review,
            args=(str(tmp_path), job_id, p_id, reviews_per_proc, barrier, queue),
        )
        for p_id in range(num_processes)
    ]

    for p in procs:
        p.start()

    try:
        results = [queue.get(timeout=30) for _ in procs]
        for worker_id, codes in results:
            assert all(code == 200 for code in codes), f"Worker {worker_id} got non-200: {codes}"
    finally:
        for p in procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()
                p.join()

    client = TestClient(create_app(store_root=tmp_path))
    persisted = client.get(f"/api/v1/jobs/{job_id}/report").json()
    assert len(persisted["reviews"]) == total_reviews
    notes = {r["note"] for r in persisted["reviews"]}
    expected = {f"proc-note-{w}-{i}" for w in range(num_processes) for i in range(reviews_per_proc)}
    assert notes == expected


def _hold_external_advisory_lock(path_str, ready_evt, release_evt):

    with open(path_str, "r+b", buffering=0) as handle:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        ready_evt.set()
        release_evt.wait(timeout=15)
        handle.seek(0)
        if os.name == "nt":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_review_transaction_under_external_process_lock_conflict_and_recovery(tmp_path):
    """Verify that when an external process holds file lock, reviews fail with 409 and recover."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)
    lock_file = tmp_path / ".lock"

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()

    proc = ctx.Process(target=_hold_external_advisory_lock, args=(str(lock_file), ready, release))
    proc.start()

    try:
        assert ready.wait(timeout=10), "External lock was not acquired in time"

        # During lock holding, review should fail with 409
        conflict_res = client.post(
            f"/api/v1/jobs/{report.job.id}/reviews",
            headers={"X-PrivacyTrace-Local": "1"},
            json={"actor": "op", "reason": "locked attempt", "note": "fail expected"},
        )
        assert conflict_res.status_code == 409
        # Ensure sensitive path or internal timeout details are not leaked
        assert "timed out" not in conflict_res.text

    finally:
        release.set()
        proc.join(timeout=10)
        if proc.is_alive():
            proc.terminate()
            proc.join()

    # After lock is released, review must succeed immediately
    recovered_res = client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "op", "reason": "post-lock recovery", "note": "success after lock"},
    )
    assert recovered_res.status_code == 200
    assert recovered_res.json()["reviews"][0]["note"] == "success after lock"


def test_review_atomic_temp_file_cleaned_up_after_failure(tmp_path):
    """Verify that failed reviews do not leave dangling temporary files in store root."""
    app = create_app(store_root=tmp_path)
    report = seed(app.state.job_store)
    client = TestClient(app)

    # Initial file check
    tmp_files_before = list(tmp_path.glob(".*.tmp"))
    assert len(tmp_files_before) == 0

    # Rejected review (422)
    client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "op", "reason": "bad", "note": "x" * 10001},
    )
    tmp_files_after_422 = list(tmp_path.glob(".*.tmp"))
    assert len(tmp_files_after_422) == 0

    # Rejected review (409 from bad claim)
    bad_claim = report.policy_claims[0].model_dump(mode="json")
    bad_claim["evidence_ids"] = ["nonexistent_id"]
    client.post(
        f"/api/v1/jobs/{report.job.id}/reviews",
        headers={"X-PrivacyTrace-Local": "1"},
        json={"actor": "op", "reason": "bad", "claim": bad_claim},
    )
    tmp_files_after_409 = list(tmp_path.glob(".*.tmp"))
    assert len(tmp_files_after_409) == 0
