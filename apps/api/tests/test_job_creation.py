"""Independent processes must never reserve the same analysis job twice."""

import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest

from privacytrace.job_store import JobStore
from privacytrace.models import AnalysisJob
from privacytrace.resources import taxonomy


def job(sample):
    return AnalysisJob(
        id="same-id", sample_id=sample, input_mode="APK", state="QUEUED",
        ruleset_version=taxonomy()["version"], created_at=datetime.now(timezone.utc),
    )


def reserve(root, sample, ready, outcomes):
    store = JobStore(root)
    ready.wait(timeout=20)
    try:
        store.create_if_absent(job(sample))
    except ValueError as exc:
        outcomes.put(("rejected", sample, str(exc)))
    else:
        outcomes.put(("created", sample, ""))


def test_one_reservation_wins_across_processes_and_survives_restart(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    ready, outcomes = ctx.Barrier(4), ctx.Queue()
    processes = [ctx.Process(target=reserve, args=(tmp_path, f"sample-{i}", ready, outcomes))
                 for i in range(4)]
    try:
        for process in processes:
            process.start()
        results = [outcomes.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        winners = [sample for status, sample, _ in results if status == "created"]
        assert len(winners) == 1
        assert all("already exists" in message for status, _, message in results
                   if status == "rejected")
        assert JobStore(tmp_path).get_job("same-id").sample_id == winners[0]
        assert len(JobStore(tmp_path).list()) == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                process.join(timeout=10)
        outcomes.close()


@pytest.mark.parametrize("state", ["QUEUED", "STATIC_ANALYSIS", "CANCELLED", "FAILED"])
def test_pipeline_duplicate_is_rejected_before_any_input_or_scan(tmp_path, monkeypatch, state):
    from privacytrace import pipeline

    original = job("original.apk")
    original.state = state
    store = JobStore(tmp_path)
    store.create_if_absent(original)
    before = (tmp_path / "same-id.json").read_bytes()

    def unexpected(*args, **kwargs):
        pytest.fail("Duplicate job reached intake or scanning")

    monkeypatch.setattr(pipeline, "validate_input", unexpected)
    monkeypatch.setattr(pipeline, "load_policy", unexpected)
    monkeypatch.setattr(pipeline, "scan_isolated", unexpected)
    with pytest.raises(ValueError, match="already exists"):
        pipeline.run(tmp_path / "other.apk", tmp_path / "policy.json", "other",
                     job_id="same-id", store_dir=tmp_path)
    assert (tmp_path / "same-id.json").read_bytes() == before


def test_corrupt_existing_record_is_never_replaced(tmp_path):
    path = tmp_path / "same-id.json"
    path.write_bytes(b"incomplete record")
    with pytest.raises(ValueError, match="already exists"):
        JobStore(tmp_path).create_if_absent(job("replacement"))
    assert path.read_bytes() == b"incomplete record"


def test_concurrent_pipeline_never_scans_both_inputs_for_one_id(tmp_path, monkeypatch):
    from privacytrace import pipeline
    from privacytrace.isolated_scan import ScanError

    # Force both callers past the old check-before-create gap if it returns.
    # Atomic creation never exposes a missing record to this initial read.
    missing_reads = Barrier(2)
    scanned = []

    class ScheduledStore(JobStore):
        def __init__(self, root):
            super().__init__(root)
            self.first_read = True

        def get_job(self, job_id):
            first, self.first_read = self.first_read, False
            try:
                return super().get_job(job_id)
            except KeyError:
                if first:
                    missing_reads.wait(timeout=10)
                raise

    def controlled_scan(apk, **kwargs):
        scanned.append(apk)
        raise ScanError("CONTROLLED_STOP", "Fixture stops at the scanner boundary")

    def run(name):
        try:
            return pipeline.run(tmp_path / name, tmp_path / "policy.json", name,
                                job_id="same-id", store_dir=tmp_path)["status"]
        except ValueError as exc:
            assert "already exists" in str(exc)
            return "DUPLICATE"

    monkeypatch.setattr(pipeline, "JobStore", ScheduledStore)
    monkeypatch.setattr(pipeline, "validate_input", lambda path: None)
    monkeypatch.setattr(pipeline, "load_policy", lambda path: {})
    monkeypatch.setattr(pipeline, "scan_isolated", controlled_scan)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(run, ["first.apk", "second.apk"]))
    assert sorted(statuses) == ["DUPLICATE", "FAILED"]
    assert len(scanned) == 1
    assert JobStore(tmp_path).get_job("same-id").sample_id == scanned[0].name
