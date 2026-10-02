"""Facts, policy declarations, and contextual hints are separate typed records."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

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


class Evidence(Model):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["MANIFEST", "API", "SDK", "POLICY_DOCUMENT", "POLICY_SENTENCE"]
    status: Literal["STATIC_POTENTIAL", "DECLARED"]
    source: str = Field(min_length=1, max_length=1000)
    locator: str = Field(min_length=1, max_length=1000)
    excerpt: str = Field(min_length=1, max_length=10000)
    document_id: str | None = None

    @model_validator(mode="after")
    def validate_kind_status(self):
        is_policy = self.kind in {"POLICY_DOCUMENT", "POLICY_SENTENCE"}
        if is_policy != (self.status == "DECLARED"):
            raise ValueError("Policy declarations and static evidence must remain separate")
        if is_policy and not self.document_id:
            raise ValueError("Policy evidence requires document_id")
        if not is_policy and self.document_id:
            raise ValueError("Static evidence must not reference a policy document")
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
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text: str = Field(min_length=1, max_length=200000)
    completeness: Literal["COMPLETE", "PARTIAL"]
    evidence_id: str


class PolicyClaim(Model):
    id: str
    document_id: str
    data_type: str
    action: Literal["ACCESS", "UNKNOWN"] = "ACCESS"
    declared_purpose: str | None = None
    declared_recipient: str | None = None
    basis: Literal["POLICY_DECLARATION"] = "POLICY_DECLARATION"
    ambiguity_flags: list[Literal["CATCH_ALL", "UNCLEAR_ACTION"]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)


class AnalysisJob(Model):
    id: str
    sample_id: str
    input_mode: Literal["SYNTHETIC", "APK"]
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
    error: str | None = None


class EvaluationInput(Model):
    job: AnalysisJob
    evidence: list[Evidence] = Field(max_length=2000)
    behaviors: list[PrivacyBehavior] = Field(max_length=500)
    policy_documents: list[PolicyDocument] = Field(max_length=50)
    policy_claims: list[PolicyClaim] = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_references(self):
        from hashlib import sha256

        from .resources import taxonomy

        rules = taxonomy()
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
        for doc in self.policy_documents:
            snapshot = evidence.get(doc.evidence_id)
            if not snapshot or snapshot.kind != "POLICY_DOCUMENT" or snapshot.document_id != doc.id:
                raise ValueError("A document requires its own snapshot evidence")
            if snapshot.excerpt != doc.text:
                raise ValueError("Document evidence must contain the policy snapshot text")
            if sha256(doc.text.encode("utf-8")).hexdigest() != doc.sha256:
                raise ValueError("Policy snapshot hash does not match text")
        for behavior in self.behaviors:
            if behavior.data_type not in types:
                raise ValueError("Unknown behavior data type")
            for ref in behavior.evidence_ids:
                if ref not in evidence or evidence[ref].status != "STATIC_POTENTIAL":
                    raise ValueError("A behavior requires existing static evidence")
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
                if sentence.excerpt not in documents[claim.document_id].text:
                    raise ValueError("Claim quote is not present in the policy snapshot")
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


class EvaluationResult(Model):
    job_id: str
    ruleset_version: str
    issues: list[PrivacyIssue]
