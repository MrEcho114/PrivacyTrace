"""Local web intake contracts. A checked candidate is not a reviewed policy."""

from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .models import Model

PolicySourceType = Literal["OFFICIAL_WEB_POLICY", "SDK_POLICY", "STORE_POLICY", "IN_APP_POLICY"]
PolicySourceProvenance = Literal[
    "MANIFEST_METADATA",
    "EXTERNAL_CHAT_EXPORT",
    "DIRECT_WEB_FETCH",
    "MANUAL_INPUT",
]


class WebCandidate(Model):
    id: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=100)
    excerpt: str = Field(min_length=1, max_length=5000)
    data_type: str = Field(min_length=1, max_length=100)
    polarity: Literal["AFFIRMATIVE", "NEGATIVE", "UNKNOWN"] = "UNKNOWN"
    subject: Literal["HOST_APP", "THIRD_PARTY", "UNKNOWN"] = "UNKNOWN"
    action: Literal["ACCESS", "UNKNOWN"] = "UNKNOWN"
    condition: str | None = Field(default=None, max_length=1000)
    declared_purpose: str | None = Field(default=None, max_length=1000)
    declared_recipient: str | None = Field(default=None, max_length=1000)
    ambiguity_flags: list[Literal["CATCH_ALL", "UNCLEAR_ACTION"]] = Field(default_factory=list)
    start_offset: int | None = Field(default=None, ge=0, strict=True)
    checked: bool = False


class WebSource(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    title: str = Field(min_length=1, max_length=100)
    url: str = Field(default="", max_length=2000)
    source_type: PolicySourceType = "OFFICIAL_WEB_POLICY"
    text: str = Field(default="", max_length=200000)
    version: str = Field(default="UNKNOWN", max_length=100)
    region: str = Field(default="", max_length=100)
    product: str = Field(default="", max_length=100)
    package_name: str = Field(default="", max_length=200)
    version_code: int | None = Field(default=None, ge=0, strict=True)
    status: Literal["ready", "manual", "empty", "failed", "url_only"] = "empty"
    error_code: str | None = None
    captured_at: str | None = None
    sha256: str | None = None
    final_url: str | None = None
    provenance: PolicySourceProvenance | None = Field(
        default=None,
        description=(
            "Server-derived source origin; input values are ignored. URL discovery origin "
            "is distinct from text acquisition and does not prove official policy verification."
        ),
    )
    model_audit: dict[str, str | int | bool] = Field(default_factory=dict)


class ExternalSourceFields(Model):
    source_type: PolicySourceType | None = None
    title: str = Field(default="External Policy", min_length=1, max_length=100)
    url: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=200000)
    version: str = Field(default="UNKNOWN", max_length=100)
    region: str = Field(default="", max_length=100)
    product: str = Field(default="", max_length=100)
    package_name: str = Field(default="", max_length=200)
    version_code: int | None = Field(default=None, ge=0, strict=True)


class ExternalSourceInput(ExternalSourceFields):
    id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    status: Literal["ready", "manual", "empty", "failed", "url_only"] | None = None


class CollectedSourceInput(ExternalSourceFields):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    title: str = Field(min_length=1, max_length=100)


class ExternalClaimInput(Model):
    excerpt: str = Field(min_length=1, max_length=5000)
    data_type: str = Field(min_length=1, max_length=100)
    polarity: Literal["AFFIRMATIVE", "NEGATIVE", "POSITIVE", "UNKNOWN"] = "UNKNOWN"
    subject: Literal["HOST_APP", "THIRD_PARTY", "UNKNOWN"] = "UNKNOWN"
    action: Literal["ACCESS", "UNKNOWN"] = "UNKNOWN"
    condition: str | None = Field(default=None, max_length=1000)
    declared_purpose: str | None = Field(default=None, max_length=1000)
    declared_recipient: str | None = Field(default=None, max_length=1000)


class ExternalPolicyExportInput(Model):
    source: ExternalSourceInput
    claims: list[ExternalClaimInput] = Field(default_factory=list, max_length=800)
    summary: str | None = Field(default=None, max_length=10000)


class ExternalCollectionResult(Model):
    state: Literal["RETRIEVED", "PROVIDED", "URL_ONLY", "OFFLINE", "NOT_FOUND", "UNAVAILABLE"]
    source: CollectedSourceInput | None = None
    observed_at: AwareDatetime | None = None

    @field_validator("observed_at", mode="before")
    @classmethod
    def validate_external_time(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError("observed_at must be an ISO 8601 string with timezone")
        return value

    @model_validator(mode="after")
    def validate_collection_state(self):
        source = self.source
        if source is None:
            if self.state not in {"OFFLINE", "NOT_FOUND"}:
                raise ValueError("This collection state requires a source")
            return self
        if self.state == "NOT_FOUND":
            raise ValueError("NOT_FOUND must not invent a source")
        if self.state in {"RETRIEVED", "PROVIDED"}:
            if not source.text.strip():
                raise ValueError("Retrieved or provided material needs policy text")
        elif source.text:
            raise ValueError("Unretrieved material cannot contain policy text")
        if self.state != "PROVIDED" and not source.url.strip():
            raise ValueError("This collection state requires a URL")
        return self


class ExternalPolicyCollectionInput(Model):
    version: Literal["privacytrace-policy-collector/1"]
    results: list[ExternalCollectionResult] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_source_ids(self):
        ids = [result.source.id for result in self.results if result.source is not None]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate external source IDs")
        return self


class DraftInput(Model):
    name: str = Field(min_length=1, max_length=200)
    sources: list[WebSource] = Field(min_length=1, max_length=8)


class CandidateInput(Model):
    revision: int = Field(ge=1, strict=True)
    candidates: list[WebCandidate] = Field(max_length=800)


class StartInput(Model):
    revision: int = Field(ge=1, strict=True)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class ModelSettings(Model):
    enabled: bool = False
    api_base: str = Field(default="", max_length=2000)
    model: str = Field(default="", max_length=100)
    api_key: str | None = Field(default=None, max_length=4096)


class FetchInput(Model):
    url: str = Field(min_length=1, max_length=2000)
