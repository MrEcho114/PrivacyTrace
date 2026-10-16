"""Local web intake contracts. A checked candidate is not a reviewed policy."""

from typing import Literal

from pydantic import Field

from .models import Model


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
    source_type: Literal["OFFICIAL_WEB_POLICY", "SDK_POLICY", "STORE_POLICY", "IN_APP_POLICY"] = (
        "OFFICIAL_WEB_POLICY"
    )
    text: str = Field(default="", max_length=200000)
    version: str = Field(default="UNKNOWN", max_length=100)
    region: str = Field(default="", max_length=100)
    product: str = Field(default="", max_length=100)
    package_name: str = Field(default="", max_length=200)
    version_code: int | None = Field(default=None, ge=0, strict=True)
    status: Literal["ready", "manual", "empty", "failed"] = "empty"
    error_code: str | None = None
    captured_at: str | None = None
    sha256: str | None = None
    final_url: str | None = None
    model_audit: dict[str, str | int | bool] = Field(default_factory=dict)


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
