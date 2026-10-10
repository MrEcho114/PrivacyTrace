"""Facts, policy declarations, and contextual hints are separate typed records."""

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PolicySource(StrEnum):
    IN_APP_POLICY = "IN_APP_POLICY"
    STORE_POLICY = "STORE_POLICY"
    OFFICIAL_WEB_POLICY = "OFFICIAL_WEB_POLICY"
    SDK_POLICY = "SDK_POLICY"


class MatchStatus(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    CATEGORY_MATCH = "CATEGORY_MATCH"
    NOT_DECLARED = "NOT_DECLARED"
    POLICY_SOURCE_CONFLICT = "POLICY_SOURCE_CONFLICT"
    AMBIGUOUS_DISCLOSURE = "AMBIGUOUS_DISCLOSURE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PolicyArtifact(Model):
    """Canonical captured text, before any semantic extraction (UTF-8 hash)."""

    text: str = Field(min_length=1, max_length=200000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalization: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def validate_hash(self):
        if sha256(self.text.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("Policy snapshot hash does not match text")
        return self


class ApiCall(Model):
    target_descriptor: str = Field(min_length=1, max_length=1000)
    rule_id: str = Field(min_length=1, max_length=100)
    ruleset_version: str = Field(min_length=1, max_length=100)
    context: dict[str, str] = Field(default_factory=dict)


class Evidence(Model):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["MANIFEST", "API", "SDK", "POLICY_DOCUMENT", "POLICY_SENTENCE"]
    status: Literal["STATIC_POTENTIAL", "DECLARED"]
    source: str = Field(min_length=1, max_length=1000)
    locator: str = Field(min_length=1, max_length=1000)
    excerpt: str = Field(default="", max_length=10000)
    document_id: str | None = None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    start_offset: int | None = Field(default=None, ge=0, strict=True)
    end_offset: int | None = Field(default=None, ge=1, strict=True)
    api_call: ApiCall | None = None

    @model_validator(mode="after")
    def validate_kind_status(self):
        is_policy = self.kind in {"POLICY_DOCUMENT", "POLICY_SENTENCE"}
        if is_policy != (self.status == "DECLARED"):
            raise ValueError("Policy declarations and static evidence must remain separate")
        if is_policy and not self.document_id:
            raise ValueError("Policy evidence requires document_id")
        if not is_policy and self.document_id:
            raise ValueError("Static evidence must not reference a policy document")
        if self.kind != "POLICY_DOCUMENT" and not self.excerpt:
            raise ValueError("Non-snapshot evidence requires an excerpt")
        if self.kind == "POLICY_DOCUMENT" and not self.artifact_sha256:
            raise ValueError("Document evidence requires artifact_sha256")
        if self.kind == "POLICY_SENTENCE":
            if self.start_offset is None or self.end_offset is None:
                raise ValueError("Policy sentence requires character offsets")
            if self.end_offset <= self.start_offset:
                raise ValueError("Policy sentence span must be nonempty and ordered")
        elif self.start_offset is not None or self.end_offset is not None:
            raise ValueError("Only policy sentences have text offsets")
        if (self.kind == "API") != (self.api_call is not None):
            raise ValueError("API evidence requires structured api_call, not a kind label")
        if self.kind != "POLICY_DOCUMENT" and self.artifact_sha256 is not None:
            raise ValueError("Only document evidence references an artifact hash")
        return self


class ContextualHint(Model):
    value: str
    basis: Literal["CONTEXTUAL_PURPOSE_HINT"] = "CONTEXTUAL_PURPOSE_HINT"
    evidence_ids: list[str] = Field(min_length=1)


class PrivacyBehavior(Model):
    id: str
    data_type: str
    action: Literal["ACCESS", "CAPABILITY"] = "ACCESS"
    purpose: Literal["UNKNOWN"] = "UNKNOWN"
    recipient: Literal["UNKNOWN"] = "UNKNOWN"
    transfer: Literal["UNKNOWN"] = "UNKNOWN"
    temporal_scope: Literal["UNKNOWN"] = "UNKNOWN"
    evidence_ids: list[str] = Field(min_length=1)
    contextual_hints: list[ContextualHint] = Field(default_factory=list)


class PolicyDocument(Model):
    id: str
    source_type: PolicySource
    title: str
    version: str
    captured_at: datetime
    artifact: PolicyArtifact
    completeness: Literal["COMPLETE", "PARTIAL"]
    extraction_status: Literal["NOT_STARTED", "SUCCEEDED", "PARTIAL", "FAILED"] = "NOT_STARTED"
    review_status: Literal["UNREVIEWED", "REVIEWED"] = "UNREVIEWED"
    attachments_status: Literal["NOT_CHECKED", "COMPLETE", "MISSING"] = "NOT_CHECKED"
    applicability: "PolicyApplicability" = Field(default_factory=lambda: PolicyApplicability())
    evidence_id: str


class PolicyApplicability(Model):
    package_name: str | None = Field(default=None, min_length=1)
    version_codes: list[Annotated[int, Field(ge=0, strict=True)]] = Field(
        default_factory=list, max_length=1000
    )
    regions: list[str] = Field(default_factory=list, max_length=100)
    product_scope: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_versions(self):
        if any(isinstance(code, bool) or code < 0 for code in self.version_codes):
            raise ValueError("Version codes must be nonnegative integers")
        if any(not region.strip() for region in self.regions):
            raise ValueError("Regions must not be blank")
        return self


class PolicyClaim(Model):
    id: str
    document_id: str
    data_type: str
    action: Literal["ACCESS", "UNKNOWN"] = "ACCESS"
    polarity: Literal["AFFIRMATIVE", "NEGATIVE", "UNKNOWN"] = "UNKNOWN"
    condition: str | None = Field(default=None, min_length=1, max_length=10000)
    subject: Literal["HOST_APP", "THIRD_PARTY", "UNKNOWN"] = "UNKNOWN"
    declared_purpose: str | None = None
    declared_recipient: str | None = None
    basis: Literal["POLICY_DECLARATION"] = "POLICY_DECLARATION"
    ambiguity_flags: list[Literal["CATCH_ALL", "UNCLEAR_ACTION"]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class SourceOrigin(StrEnum):
    """Immutable provenance of the underlying data, recorded instead of inferred.

    This field answers "where did the data come from". It never changes once a
    job is created. It does NOT describe how a report is being served right now
    -- a job created by a real scan keeps REAL_SCAN even when its report is later
    replayed from persisted storage. Use `delivery_mode` for the loading path.

    CONTROLLED and SYNTHETIC never describe a real user application.
    """

    SYNTHETIC = "SYNTHETIC"
    CONTROLLED = "CONTROLLED"
    REAL_SCAN = "REAL_SCAN"


class DeliveryMode(StrEnum):
    """How a report reached the client in this response. Repeated per request.

    This field answers "how was it loaded", which is mutable: the same
    persisted job can be delivered as LIVE_GENERATED in the run that produced
    it and as PERSISTED_REPLAY on any later load. It is never persisted on the
    job, because it depends on the serving path rather than on the data.
    """

    LIVE_GENERATED = "LIVE_GENERATED"
    PERSISTED_REPLAY = "PERSISTED_REPLAY"


class AnalysisJob(Model):
    id: str
    sample_id: str
    input_mode: Literal["SYNTHETIC", "APK"]
    source_origin: SourceOrigin
    state: Literal[
        "QUEUED",
        "INTAKE",
        "STATIC_ANALYSIS",
        "POLICY_PARSING",
        "EVALUATING",
        "REPORTING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    ]
    ruleset_version: str
    created_at: datetime
    package_name: str | None = Field(default=None, min_length=1)
    version_code: int | None = Field(default=None, ge=0, strict=True)
    region: str | None = Field(default=None, min_length=1)
    product_scope: str | None = Field(default=None, min_length=1)
    error: str | None = None


class EvaluationInput(Model):
    job: AnalysisJob
    evidence: list[Evidence] = Field(max_length=2000)
    behaviors: list[PrivacyBehavior] = Field(max_length=500)
    policy_documents: list[PolicyDocument] = Field(max_length=50)
    policy_claims: list[PolicyClaim] = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_references(self):
        from .resources import taxonomy

        rules = taxonomy(self.job.ruleset_version)
        if self.job.ruleset_version != rules["version"]:
            raise ValueError("Unsupported ruleset version")
        types = {item["id"] for item in rules["data_types"]}
        for collection in [
            self.evidence,
            self.behaviors,
            self.policy_documents,
            self.policy_claims,
        ]:
            if len({item.id for item in collection}) != len(collection):
                raise ValueError("Duplicate IDs in a collection")
        evidence = {item.id: item for item in self.evidence}
        documents = {item.id: item for item in self.policy_documents}
        if any(item.document_id and item.document_id not in documents for item in self.evidence):
            raise ValueError("Policy evidence references an unknown document")
        api_rules = {item["rule_id"]: item for item in rules["api_mappings"]}
        for item in self.evidence:
            if item.api_call is not None:
                call = item.api_call
                rule = api_rules.get(call.rule_id)
                if (
                    not rule
                    or call.ruleset_version != rules["version"]
                    or call.target_descriptor != rule["target_descriptor"]
                    or call.context != rule["context"]
                    or (rule.get("synthetic_only") and self.job.input_mode != "SYNTHETIC")
                ):
                    raise ValueError(
                        "API descriptor, context or ruleset does not match a trusted rule"
                    )
        for doc in self.policy_documents:
            snapshot = evidence.get(doc.evidence_id)
            if not snapshot or snapshot.kind != "POLICY_DOCUMENT" or snapshot.document_id != doc.id:
                raise ValueError("A document requires its own snapshot evidence")
            if snapshot.artifact_sha256 != doc.artifact.sha256:
                raise ValueError("Document evidence must reference its artifact hash")
            if snapshot.excerpt and snapshot.excerpt not in doc.artifact.text:
                raise ValueError("Snapshot preview is not in the policy artifact")
        for sentence in self.evidence:
            if sentence.kind == "POLICY_SENTENCE":
                text = documents[sentence.document_id].artifact.text
                if sentence.end_offset > len(text):
                    raise ValueError("Policy sentence offsets exceed the artifact")
                if text[sentence.start_offset : sentence.end_offset] != sentence.excerpt:
                    raise ValueError("Policy sentence span does not match artifact text")
        for behavior in self.behaviors:
            if behavior.data_type not in types:
                raise ValueError("Unknown behavior data type")
            for ref in behavior.evidence_ids:
                if ref not in evidence or evidence[ref].status != "STATIC_POTENTIAL":
                    raise ValueError("A behavior requires existing static evidence")
                call = evidence[ref].api_call
                if call and api_rules[call.rule_id]["data_type"] != behavior.data_type:
                    raise ValueError("API rule does not map to the behavior data type")
            for hint in behavior.contextual_hints:
                if any(ref not in behavior.evidence_ids for ref in hint.evidence_ids):
                    raise ValueError("Hints must reference the behavior's evidence")
        for claim in self.policy_claims:
            if claim.document_id not in documents or claim.data_type not in types:
                raise ValueError("Unknown claim document or data type")
            for ref in claim.evidence_ids:
                sentence = evidence.get(ref)
                if (
                    not sentence
                    or sentence.kind != "POLICY_SENTENCE"
                    or sentence.document_id != claim.document_id
                ):
                    raise ValueError("Claims require sentence evidence from their own document")
        return self


class PrivacyIssue(Model):
    id: str
    behavior_id: str
    data_type: str
    status: MatchStatus
    evidence_status: Literal["STATIC_POTENTIAL"] = "STATIC_POTENTIAL"
    policy_document_ids: list[str]
    evidence_ids: list[str] = Field(min_length=1)
    explanation: str
    scope: Literal["DATA_TYPE_DISCLOSURE"] = "DATA_TYPE_DISCLOSURE"
    requires_review: bool = True


class EvaluationResult(Model):
    job_id: str
    ruleset_version: str
    issues: list[PrivacyIssue]
