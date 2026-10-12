"""Independent processes must never reserve the same analysis job twice."""

import errno
import multiprocessing
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest

from privacytrace import job_store as job_store_module
from privacytrace.job_store import JobStore
from privacytrace.models import AnalysisJob
from privacytrace.resources import taxonomy


def job(sample):
    return AnalysisJob(
        id="same-id", sample_id=sample, input_mode="APK", source_origin="REAL_SCAN", state="QUEUED",
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


def touch_lock(root, ready, outcomes):
    """Acquire the transaction lock and report the outcome of the attempt.

    ``ok`` means the lock was acquired *and* the transaction exited cleanly;
    ``oserror`` is a bare open/lock/release failure; ``contended`` is the
    bounded ``ValueError`` raised when the shared deadline expires.

    Success is reported from the ``else`` branch, not from inside the ``with``
    body. Reporting inside the body would publish ``ok`` before ``__exit__``
    runs, so a failure while releasing the lock would post ``ok`` *and*
    ``oserror`` from the same process -- the parent reads one result per child
    and would silently drop the error.
    """
    store = JobStore(root)
    ready.wait(timeout=20)
    try:
        with store._transaction():
            pass
    except OSError as exc:
        outcomes.put(("oserror", type(exc).__name__, str(exc)))
    except ValueError as exc:
        outcomes.put(("contended", type(exc).__name__, str(exc)))
    else:
        outcomes.put(("ok", "", ""))


@pytest.mark.parametrize("rounds", [12])
def test_concurrent_first_lock_creation_never_fails_to_open(tmp_path, rounds):
    """Opening the lock file is itself contended; it must be retried.

    Concurrent ``os.open(O_CREAT|O_RDWR)`` of the same path raises a transient
    sharing violation on Windows. The lock *acquisition* has a retry budget, so
    the *open* needs one too, or first-touch contention surfaces as a bare
    ``PermissionError`` instead of a bounded wait.

    Every process must actually *acquire* the lock. Reporting the open failure
    only as "not a bare OSError" would pass even when all four processes are
    turned away, which is why failures are asserted per outcome below.
    """
    roots = [tmp_path / f"root-{i}" for i in range(rounds)]
    for root in roots:
        root.mkdir(parents=True)
    ctx = multiprocessing.get_context("spawn")
    unacquired = []
    leaked = []
    for attempt, root in enumerate(roots):
        ready, outcomes = ctx.Barrier(4), ctx.Queue()
        processes = [ctx.Process(target=touch_lock, args=(root, ready, outcomes)) for _ in range(4)]
        try:
            for process in processes:
                process.start()
            results = [outcomes.get(timeout=30) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                # A child that dies before reporting would otherwise shrink the
                # result set without anyone noticing.
                assert process.exitcode == 0
            # The lock must be *acquired* by every process. A bare OSError means
            # the open was never retried; ValueError means the shared budget
            # expired without anyone getting in. Either way the retry did not do
            # its job, so both are failures.
            rejected = [result for result in results if result[0] != "ok"]
            if rejected:
                unacquired.append((attempt, rejected))
            # Exactly one outcome per child. A child that reports twice (e.g.
            # "ok" before __exit__ then "oserror" while releasing) would leave a
            # surplus entry the parent never reads, hiding the failure.
            extra = []
            while not outcomes.empty():
                extra.append(outcomes.get_nowait())
            if extra:
                leaked.append((attempt, extra))
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                if process.pid is not None:
                    process.join(timeout=10)
            outcomes.close()
    assert not unacquired, (
        "lock was not acquired by all processes under contention: "
        f"{unacquired[:3]}"
    )
    assert not leaked, (
        "a child reported more than one outcome; the parent reads one per child "
        f"and would drop the surplus: {leaked[:3]}"
    )


def test_lock_open_is_retried_until_the_contention_clears(tmp_path, monkeypatch):
    """Two transient open refusals must be absorbed, not surfaced to callers.

    The multi-process test above only produces contention on platforms that
    actually raise for concurrent ``CreateFile``; on Linux it can pass without
    ever exercising the retry. Injecting ``EACCES`` twice pins the retry down
    deterministically regardless of platform.
    """
    store = JobStore(tmp_path)
    real_open = os.open
    refused = []
    lock_open_depths = []

    def flaky_open(path, flags, mode=0o777):
        if str(path).endswith(".lock"):
            # Nested re-entry would mean the transaction opened the lock twice;
            # the retry must replace the failed attempt, not stack on top of it.
            lock_open_depths.append(len(lock_open_depths))
            if len(refused) < 2:
                refused.append(path)
                raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr(job_store_module.os, "open", flaky_open)
    with store._transaction():
        pass
    assert len(refused) == 2, "the injected refusals were not both consumed"
    assert lock_open_depths == [0, 1, 2], f"unexpected open sequence: {lock_open_depths}"


def test_lock_open_retry_gives_up_at_the_shared_deadline(tmp_path, monkeypatch):
    """Persistent refusals must stay bounded and fold into the lock contract.

    The open retry shares one deadline with acquisition, so a lock that can
    never be opened has to raise the same ``ValueError`` callers already handle
    rather than a bare ``PermissionError`` -- and it must do so within the
    budget instead of retrying forever.
    """
    store = JobStore(tmp_path)
    real_open = os.open
    attempts = []

    def never_open(path, flags, mode=0o777):
        if str(path).endswith(".lock"):
            attempts.append(time.monotonic())
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr(job_store_module.os, "open", never_open)
    # Shrink the shared budget so the loop stays fast; the behaviour under test
    # is the bound, not the particular 5s value.
    budget = 0.3
    monkeypatch.setattr(JobStore, "LOCK_TIMEOUT_SECONDS", budget)
    started = time.monotonic()
    with pytest.raises(ValueError, match="lock unavailable"):
        with store._transaction():
            pass
    elapsed = time.monotonic() - started
    assert len(attempts) > 1, "persistent refusals were not retried at all"
    assert elapsed < budget + 1.0, f"retry overshot budget: {elapsed:.2f}s"


def test_lock_open_failure_keeps_the_original_error_as_its_cause(tmp_path, monkeypatch):
    """The bounded ``ValueError`` must not swallow why the open failed.

    A permanent denial and transient contention are indistinguishable at the
    catch site -- both arrive as ``PermissionError`` with ``errno 13``, and the
    platform offers no further discriminator. Since the retry cannot tell them
    apart, the original error has to stay reachable through ``__cause__`` so a
    permanent denial is still diagnosable from the outside.
    """
    store = JobStore(tmp_path)
    real_open = os.open

    def deny(path, flags, mode=0o777):
        if str(path).endswith(".lock"):
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return real_open(path, flags, mode)

    monkeypatch.setattr(job_store_module.os, "open", deny)
    monkeypatch.setattr(JobStore, "LOCK_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(ValueError, match="lock unavailable") as raised:
        with store._transaction():
            pass
    assert isinstance(raised.value.__cause__, PermissionError)
    assert raised.value.__cause__.errno == errno.EACCES, (
        "the original errno was flattened away; a permanent denial would be "
        "indistinguishable from contention"
    )


def test_lock_release_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    """Releasing the lock can fail *after* the body ran; that must not read as ok.

    Success is only real once the whole transaction -- release included -- has
    exited. Reporting from inside the ``with`` body would publish ``ok`` first
    and then ``oserror``, and the parent reads exactly one result per child, so
    the error would be dropped on the floor.
    """
    if os.name == "nt":
        import msvcrt

        real_locking = msvcrt.locking

        def flaky_locking(fd, mode, nbytes):
            if mode == msvcrt.LK_UNLCK:
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_locking(fd, mode, nbytes)

        monkeypatch.setattr(msvcrt, "locking", flaky_locking)
    else:
        import fcntl

        real_flock = fcntl.flock

        def flaky_flock(fd, operation):
            if operation == fcntl.LOCK_UN:
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_flock(fd, operation)

        monkeypatch.setattr(fcntl, "flock", flaky_flock)

    class _Ready:
        def wait(self, timeout=None):
            return True

    outcomes = []

    class _Sink:
        def put(self, item):
            outcomes.append(item)

    touch_lock(tmp_path, _Ready(), _Sink())
    kinds = [item[0] for item in outcomes]
    assert kinds == ["oserror"], (
        f"a failed lock release was reported as {kinds}; it must not also "
        "publish an earlier success"
    )


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


def test_missing_lock_directory_still_fails_fast(tmp_path):
    """Only transient contention is retried; a broken root stays a fast error."""
    store = JobStore(tmp_path)
    store.root.rmdir()  # storage root disappears after construction
    started = time.monotonic()
    with pytest.raises((FileNotFoundError, ValueError)):
        with store._transaction():
            pass
    # Retrying every error would burn the full lock budget here.
    assert time.monotonic() - started < JobStore.LOCK_TIMEOUT_SECONDS


def test_lock_file_is_reused_across_transactions(tmp_path):
    """A pre-existing lock file must not trip the contention path."""
    store = JobStore(tmp_path)
    for _ in range(3):
        with store._transaction():
            pass
    assert (tmp_path / ".lock").is_file()
    store.create_if_absent(job("reused"))
    assert store.get_job("same-id").sample_id == "reused"


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
