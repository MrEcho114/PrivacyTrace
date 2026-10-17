"""Private single-host JSON job storage with validate-before-atomic-replace writes."""

import json
import os
import re
import stat
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .consistency import evaluate
from .models import AnalysisJob, DeliveryMode, EvaluationInput, SourceOrigin
from .runtime_models import (
    Report,
    ReviewEvent,
    ReviewRequest,
    SampleMetadata,
    ScanCoverage,
    StoredJob,
)


def migrate_record(payload: dict) -> dict:
    """Bring a stored record forward to the current schema, in memory only.

    Records written before ``AnalysisJob.source_origin`` existed carry no
    provenance at all. That origin cannot be recovered from the stored bytes,
    so it is recorded as UNKNOWN rather than guessed -- labelling such a record
    REAL_SCAN would assert a real user scan that was never recorded.

    The job is embedded twice (top level and inside ``bundle``), and the record
    validator requires the two copies to agree, so both are patched together.
    ``bundle`` is only read when it really is a JSON object: a record that is
    valid JSON but structurally wrong (``"bundle": "corrupted"``, an array, or a
    number) must fall through to normal schema validation and be rejected as a
    bad record, not raise ``AttributeError`` here -- that would escape the store
    listing's per-record handling and turn one bad file into a 500.

    The caller keeps the original file untouched, so the exact bytes written by
    the previous version remain available for audit and are never rewritten by
    a read.
    """
    bundle = payload.get("bundle")
    nested_job = bundle.get("job") if isinstance(bundle, dict) else None
    for job in (payload.get("job"), nested_job):
        if isinstance(job, dict) and "source_origin" not in job:
            job["source_origin"] = SourceOrigin.UNKNOWN.value
    return payload


class JobStore:
    MAX_FILE_BYTES = 32 * 1024 * 1024
    MAX_RECORDS = 1000
    LOCK_TIMEOUT_SECONDS = 5.0

    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        self.lock = RLock()
        self._safe_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_root(self):
        for part in (self.root, *self.root.parents):
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                raise ValueError("Symlink storage paths are not allowed")

    @contextmanager
    def _transaction(self):
        """One lock per private root, shared by CLI and API processes."""
        with self.lock:
            self._safe_root()
            path = self.root / ".lock"
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("Linked storage lock is not allowed")
            flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
            deadline = time.monotonic() + self.LOCK_TIMEOUT_SECONDS
            # Opening for create is itself contended: concurrent first-touch of
            # the same path raises a transient sharing violation (EACCES) on
            # Windows. Retry that on the same budget as acquisition, so contention
            # becomes a bounded wait instead of a bare PermissionError. Other
            # errors stay fatal -- a missing directory should fail fast, not
            # stall for the whole timeout.
            while True:
                try:
                    fd = os.open(path, flags, 0o600)
                    break
                except PermissionError as exc:
                    if time.monotonic() >= deadline:
                        raise ValueError("Local job transaction lock unavailable") from exc
                    time.sleep(0.02)
            acquired = False
            try:
                info = os.fstat(fd)
                current = path.stat(follow_symlinks=False)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
                ):
                    raise ValueError("Unsafe storage lock")
                while True:
                    try:
                        os.lseek(fd, 0, os.SEEK_SET)
                        if os.name == "nt":
                            import msvcrt

                            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                        break
                    except OSError as exc:
                        if time.monotonic() >= deadline:
                            raise ValueError("Local job transaction lock timed out") from exc
                        time.sleep(0.02)
                if os.fstat(fd).st_size == 0:
                    os.lseek(fd, 0, os.SEEK_SET)
                    os.write(fd, b"0")
                self._safe_root()
                current = path.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError("Storage lock changed during acquisition")
                yield
            finally:
                try:
                    if acquired:
                        os.lseek(fd, 0, os.SEEK_SET)
                        if os.name == "nt":
                            import msvcrt

                            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)

    def _path(self, job_id: str):
        self._safe_root()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", job_id):
            raise ValueError("Invalid job ID")
        path = self.root / f"{job_id}.json"
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise ValueError("Symlink job files are not allowed")
        return path

    def _load(self, job_id: str, allow_tombstone: bool = False):
        path = self._path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        if path.stat().st_size > self.MAX_FILE_BYTES:
            raise ValueError("Job record exceeds storage size limit")
        try:
            payload = json.loads(path.read_bytes())
        except json.JSONDecodeError as exc:
            raise ValueError("Job record is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Job record must be a JSON object")
        # Read-time migration only; the file on disk keeps its original bytes.
        record = StoredJob.model_validate(migrate_record(payload))
        if record.job.id != job_id or (record.bundle and record.bundle.job != record.job):
            raise ValueError("Stored job identity mismatch")
        if record.tombstone and not allow_tombstone:
            raise KeyError(f"Job {job_id} has been deleted")
        return record

    def _write(self, record: StoredJob):
        record = StoredJob.model_validate(record.model_dump())
        path = self._path(record.job.id)
        if not path.exists() and len(list(self.root.glob("*.json"))) >= self.MAX_RECORDS:
            raise ValueError("Local job record limit reached")
        data = record.model_dump_json(indent=2).encode("utf-8")
        if len(data) > self.MAX_FILE_BYTES:
            raise ValueError("Job record exceeds storage size limit")
        temp = self.root / f".{uuid4().hex}.tmp"
        try:
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def _report(self, record, delivery_mode: DeliveryMode = DeliveryMode.PERSISTED_REPLAY):
        if record.bundle is None or record.sample is None or record.coverage is None:
            raise ValueError("Job report is not available")
        bundle = record.bundle
        return Report(
            sample=record.sample,
            job=record.job,
            delivery_mode=delivery_mode,
            result=evaluate(bundle),
            evidence=bundle.evidence,
            behaviors=bundle.behaviors,
            policy_documents=bundle.policy_documents,
            policy_claims=bundle.policy_claims,
            coverage=record.coverage,
            tools=record.tools,
            reviews=record.reviews,
        )

    def save(
        self,
        bundle: EvaluationInput,
        metadata: dict,
        coverage: dict,
        tools: dict,
        token_digest: str | None = None,
    ) -> Report:
        with self._transaction():
            bundle = EvaluationInput.model_validate(bundle.model_dump())
            try:
                existing = self._load(bundle.job.id, allow_tombstone=True)
                if existing.tombstone:
                    raise ValueError("Deleted job cannot be overwritten")
                if existing.job.state == "CANCELLED":
                    raise ValueError("Cancelled job cannot be overwritten")
                if existing.bundle is not None:
                    raise ValueError("Published job cannot be overwritten; create a new job")
                if token_digest is None:
                    token_digest = existing.token_digest
            except KeyError:
                pass
            record = StoredJob(
                job=bundle.job,
                bundle=bundle,
                sample=SampleMetadata.model_validate(metadata),
                coverage=ScanCoverage.model_validate(coverage),
                tools=tools,
                token_digest=token_digest,
            )
            report = self._report(record, DeliveryMode.LIVE_GENERATED)
            self._write(record)
            return report

    def create_if_absent(
        self, job: AnalysisJob, token_digest: str | None = None
    ) -> AnalysisJob:
        with self._transaction():
            path = self._path(job.id)
            if path.exists():
                raise ValueError("Job already exists; choose a new job ID")
            self._write(StoredJob(job=job, token_digest=token_digest))
            return job

    def save_job(self, job: AnalysisJob) -> AnalysisJob:
        with self._transaction():
            existing = None
            try:
                existing = self._load(job.id, allow_tombstone=True)
                if existing.tombstone:
                    return existing.job
                if existing.job.state == "CANCELLED" or existing.bundle is not None:
                    return existing.job
            except KeyError:
                pass
            record = existing.model_copy(deep=True) if existing is not None else StoredJob(job=job)
            record.job = job
            self._write(record)
            return job

    def get_token_digest(self, job_id: str) -> str | None:
        with self._transaction():
            record = self._load(job_id, allow_tombstone=True)
            if record.tombstone:
                raise KeyError(f"Job {job_id} is deleted")
            return record.token_digest

    def set_token_digest(self, job_id: str, token_digest: str) -> None:
        with self._transaction():
            record = self._load(job_id, allow_tombstone=True)
            record.token_digest = token_digest
            self._write(record)

    def is_tombstoned(self, job_id: str) -> bool:
        try:
            path = self._path(job_id)
            if not path.exists():
                return False
            payload = json.loads(path.read_bytes())
            return bool(payload.get("tombstone", False))
        except Exception:
            return False

    def delete(self, job_id: str) -> bool:
        with self._transaction():
            record = self._load(job_id, allow_tombstone=True)
            record.tombstone = True
            record.token_digest = None
            self._write(record)
            return True

    def get(self, job_id: str) -> AnalysisJob:
        with self._transaction():
            return self._load(job_id).job

    def get_job(self, job_id: str) -> AnalysisJob:
        return self.get(job_id)

    def report(self, job_id: str) -> Report:
        with self._transaction():
            return self._report(self._load(job_id))

    def list(self) -> list[AnalysisJob]:
        """List every readable job, newest first.

        One unreadable record must not take down the whole listing: an old or
        damaged file would otherwise break every client that calls
        ``/api/v1/jobs``. Such records are skipped rather than reported here --
        callers that need the reason fetch the job by id, which still raises.
        """
        with self._transaction():
            self._safe_root()
            paths = list(self.root.glob("*.json"))
            if len(paths) > self.MAX_RECORDS:
                raise ValueError("Local job record limit exceeded")
            jobs = []
            for path in paths:
                try:
                    jobs.append(self._load(path.stem).job)
                except (ValueError, KeyError, OSError):
                    continue
            return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def review(self, job_id: str, request: ReviewRequest) -> Report:
        with self._transaction():
            record = self._load(job_id)
            old = self._report(record)
            if record.job.state != "SUCCEEDED":
                raise ValueError("Only succeeded jobs can be reviewed")
            bundle = record.bundle.model_copy(deep=True)
            old_claim = None
            if request.claim:
                for index, claim in enumerate(bundle.policy_claims):
                    if claim.id == request.claim.id:
                        old_claim = claim
                        bundle.policy_claims[index] = request.claim
                        break
                else:
                    bundle.policy_claims.append(request.claim)
                affected = {request.claim.document_id}
                if old_claim:
                    affected.add(old_claim.document_id)
                for doc in bundle.policy_documents:
                    if doc.id in affected:
                        doc.review_status = "UNREVIEWED"
                        doc.extraction_status = "PARTIAL"
            bundle = EvaluationInput.model_validate(bundle.model_dump())
            event = ReviewEvent(
                actor=request.actor,
                reason=request.reason,
                note=request.note,
                timestamp=datetime.now(timezone.utc),
                old_claim=old_claim,
                new_claim=request.claim,
                old_result=old.result,
                new_result=evaluate(bundle),
            )
            record.bundle = bundle
            record.reviews.append(event)
            # A review re-evaluates a report loaded from storage; it is not a
            # freshly produced scan, so it is delivered as a persisted replay.
            report = self._report(record, DeliveryMode.PERSISTED_REPLAY)
            self._write(record)
            return report

    def cancel(self, job_id: str) -> AnalysisJob:
        with self._transaction():
            record = self._load(job_id)
            if record.job.state in ("SUCCEEDED", "FAILED"):
                raise ValueError("Terminal job cannot be cancelled")
            record.job.state = "CANCELLED"
            if record.bundle:
                record.bundle.job = record.job
            self._write(record)
            return record.job

    def retry(self, job_id: str) -> AnalysisJob:
        with self._transaction():
            record = self._load(job_id)
            if record.job.state not in ("FAILED", "CANCELLED", "TIMEOUT"):
                msg = f"Job {job_id} is in state {record.job.state} and cannot be retried"
                raise ValueError(msg)
            new_id = str(uuid4())
            new_job = record.job.model_copy(deep=True)
            new_job.id = new_id
            new_job.retry_of = job_id
            new_job.state = "QUEUED"
            new_job.error = None
            new_job.created_at = datetime.now(timezone.utc)
            new_bundle = record.bundle.model_copy(deep=True) if record.bundle else None
            if new_bundle:
                new_bundle.job = new_job
            new_record = StoredJob(
                job=new_job,
                bundle=new_bundle,
                sample=record.sample,
                coverage=record.coverage,
                tools=record.tools,
                token_digest=record.token_digest,
            )
            self._write(new_record)
            return new_job
