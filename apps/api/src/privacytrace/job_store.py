"""Private single-host JSON job storage with validate-before-atomic-replace writes."""

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
from .models import AnalysisJob, EvaluationInput
from .runtime_models import (
    Report,
    ReviewEvent,
    ReviewRequest,
    SampleMetadata,
    ScanCoverage,
    StoredJob,
)


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
            fd = os.open(path, flags, 0o600)
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
                deadline = time.monotonic() + self.LOCK_TIMEOUT_SECONDS
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

    def _load(self, job_id: str):
        path = self._path(job_id)
        if not path.exists():
            raise KeyError(job_id)
        if path.stat().st_size > self.MAX_FILE_BYTES:
            raise ValueError("Job record exceeds storage size limit")
        record = StoredJob.model_validate_json(path.read_bytes())
        if record.job.id != job_id or (record.bundle and record.bundle.job != record.job):
            raise ValueError("Stored job identity mismatch")
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

    def _report(self, record):
        if record.bundle is None or record.sample is None or record.coverage is None:
            raise ValueError("Job report is not available")
        bundle = record.bundle
        return Report(
            sample=record.sample,
            job=record.job,
            result=evaluate(bundle),
            evidence=bundle.evidence,
            behaviors=bundle.behaviors,
            policy_documents=bundle.policy_documents,
            policy_claims=bundle.policy_claims,
            coverage=record.coverage,
            tools=record.tools,
            reviews=record.reviews,
        )

    def save(self, bundle: EvaluationInput, metadata: dict, coverage: dict, tools: dict) -> Report:
        with self._transaction():
            bundle = EvaluationInput.model_validate(bundle.model_dump())
            try:
                existing = self._load(bundle.job.id)
                if existing.job.state == "CANCELLED":
                    raise ValueError("Cancelled job cannot be overwritten")
                if existing.bundle is not None:
                    raise ValueError("Published job cannot be overwritten; create a new job")
            except KeyError:
                pass
            record = StoredJob(
                job=bundle.job,
                bundle=bundle,
                sample=SampleMetadata.model_validate(metadata),
                coverage=ScanCoverage.model_validate(coverage),
                tools=tools,
            )
            report = self._report(record)
            self._write(record)
            return report

    def save_job(self, job: AnalysisJob) -> AnalysisJob:
        with self._transaction():
            try:
                existing = self._load(job.id)
                if existing.job.state == "CANCELLED" or existing.bundle is not None:
                    return existing.job
            except KeyError:
                pass
            self._write(StoredJob(job=job))
            return job

    def get(self, job_id: str) -> AnalysisJob:
        with self._transaction():
            return self._load(job_id).job

    def get_job(self, job_id: str) -> AnalysisJob:
        return self.get(job_id)

    def report(self, job_id: str) -> Report:
        with self._transaction():
            return self._report(self._load(job_id))

    def list(self) -> list[AnalysisJob]:
        with self._transaction():
            self._safe_root()
            paths = list(self.root.glob("*.json"))
            if len(paths) > self.MAX_RECORDS:
                raise ValueError("Local job record limit exceeded")
            return sorted(
                (self._load(p.stem).job for p in paths), key=lambda j: j.created_at, reverse=True
            )

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
            report = self._report(record)
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
