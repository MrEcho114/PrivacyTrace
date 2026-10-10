"""Local runtime report contracts. Review events are not authenticated signatures."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .coverage_scope import behavior_limitations
from .models import (
    AnalysisJob,
    EvaluationInput,
    EvaluationResult,
    Evidence,
    Model,
    PolicyClaim,
    PolicyDocument,
    PrivacyBehavior,
)


class SampleMetadata(Model):
    name: str = Field(min_length=1, max_length=200)
    package_name: str = Field(min_length=1, max_length=200)
    version_name: str | None = Field(default=None, max_length=1024)
    version_code: int = Field(ge=0, strict=True)
    apk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    permissions: list[str] = Field(max_length=2000)
    dex_entries: list[str] = Field(max_length=1000)


class ScanCoverage(Model):
    """COMPLETE applies to DEX enumeration/processing, never all privacy behavior."""

    status: Literal["COMPLETE", "PARTIAL"]
    scope: Literal["DEX_ENTRIES"] = "DEX_ENTRIES"
    behavior_detection: Literal["LIMITED_RULE_BASED_STATIC"] = "LIMITED_RULE_BASED_STATIC"
    behavior_limitations: list[str] = Field(default_factory=behavior_limitations, max_length=1000)
    sdk_attribution_limitations: list[str] = Field(default_factory=list, max_length=1000)
    limitations: list[str] = Field(max_length=1000)
    scanned_dex: list[str] = Field(max_length=1000)
    failed_dex: list[str] = Field(max_length=1000)


class ReviewRequest(Model):
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    note: str = Field(max_length=10000)
    claim: PolicyClaim | None = None


class ReviewEvent(Model):
    actor: str
    reason: str
    note: str
    timestamp: datetime
    old_claim: PolicyClaim | None = None
    new_claim: PolicyClaim | None = None
    old_result: EvaluationResult
    new_result: EvaluationResult
    authority: Literal["UNAUTHENTICATED_LOCAL_EVENT"] = "UNAUTHENTICATED_LOCAL_EVENT"


class Report(Model):
    demo: Literal[False] = False
    sample: SampleMetadata
    job: AnalysisJob
    result: EvaluationResult
    evidence: list[Evidence]
    behaviors: list[PrivacyBehavior]
    policy_documents: list[PolicyDocument]
    policy_claims: list[PolicyClaim]
    coverage: ScanCoverage
    tools: dict[str, str]
    reviews: list[ReviewEvent] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_real_mode(self):
        if self.job.input_mode != "APK":
            raise ValueError("Non-demo reports require an APK job")
        return self


class JobsResponse(Model):
    jobs: list[AnalysisJob]


class StoredJob(Model):
    job: AnalysisJob
    bundle: EvaluationInput | None = None
    sample: SampleMetadata | None = None
    coverage: ScanCoverage | None = None
    tools: dict[str, str] = Field(default_factory=dict)
    reviews: list[ReviewEvent] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_record(self):
        if self.job.input_mode != "APK":
            raise ValueError("Local persisted jobs require APK input mode")
        if self.job.created_at.tzinfo is None:
            raise ValueError("Job created_at requires a timezone")
        if self.bundle:
            if self.bundle.job != self.job or not self.sample or not self.coverage:
                raise ValueError("Stored bundle metadata missing or mismatched")
            if (
                self.job.package_name != self.sample.package_name
                or self.job.version_code != self.sample.version_code
            ):
                raise ValueError("Sample metadata does not match job scope")
            scanned = set(self.coverage.scanned_dex)
            failed = set(self.coverage.failed_dex)
            entries = set(self.sample.dex_entries)
            if scanned & failed or scanned | failed != entries:
                raise ValueError("DEX coverage does not account for every entry")
            if self.coverage.status == "COMPLETE" and failed:
                raise ValueError("Failed DEX entries cannot be COMPLETE")
        return self
