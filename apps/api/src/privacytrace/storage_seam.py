"""Storage seam protocol and interfaces for decoupling storage implementations."""

from typing import Protocol, runtime_checkable

from .models import AnalysisJob, EvaluationInput
from .runtime_models import Report, ReviewRequest


@runtime_checkable
class JobStorageProtocol(Protocol):
    def create_if_absent(
        self, job: AnalysisJob, token_digest: str | None = None
    ) -> AnalysisJob: ...

    def save_job(self, job: AnalysisJob) -> AnalysisJob: ...

    def save(
        self,
        bundle: EvaluationInput,
        metadata: dict,
        coverage: dict,
        tools: dict,
        token_digest: str | None = None,
    ) -> Report: ...

    def get(self, job_id: str) -> AnalysisJob: ...

    def get_job(self, job_id: str) -> AnalysisJob: ...

    def report(self, job_id: str) -> Report: ...

    def list(self) -> list[AnalysisJob]: ...

    def review(self, job_id: str, request: ReviewRequest) -> Report: ...

    def cancel(self, job_id: str) -> AnalysisJob: ...

    def delete(self, job_id: str) -> bool: ...

    def get_token_digest(self, job_id: str) -> str | None: ...

    def set_token_digest(self, job_id: str, token_digest: str) -> None: ...

    def is_tombstoned(self, job_id: str) -> bool: ...
