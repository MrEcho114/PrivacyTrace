"""Versioned third-party SDK signature ruleset, pinned to a JSON Schema contract.

The ruleset is data, not code, so it needs the same authority as the other
versioned resources: a model that defines its shape, exported to
``packages/contracts`` by ``scripts/export-schema.py`` and asserted against the
file on disk. Without that, ``load_index`` would be hand-rolling validation the
repo derives from models everywhere else.
"""

from typing import Literal

from pydantic import Field, model_validator

from .models import Model


class SdkSignature(Model):
    """One vendor attribution, bounded to package ranges the vendor published."""

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    vendor: str = Field(min_length=1, max_length=200)
    package_prefixes: list[str] = Field(min_length=1, max_length=50)
    potential_data_types: list[str] = Field(min_length=1, max_length=50)
    source: str = Field(min_length=1, max_length=1000)
    source_url: str = Field(pattern=r"^https://", max_length=1000)
    license: str = Field(min_length=1, max_length=1000)
    verified_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_prefixes(self):
        for prefix in self.package_prefixes:
            # A prefix is a package path, never a partial segment or wildcard.
            if prefix != prefix.strip(".") or ".." in prefix or not prefix:
                raise ValueError(f"Malformed package prefix {prefix!r}")
            if any(not segment.isidentifier() for segment in prefix.split(".")):
                raise ValueError(f"Package prefix {prefix!r} is not a package path")
        if len(set(self.package_prefixes)) != len(self.package_prefixes):
            raise ValueError("Duplicate package prefixes in one signature")
        return self


class SdkSignatureRuleset(Model):
    """The whole ``rules/sdk-signatures.*.json`` document."""

    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: Literal["SYNTHETIC_SEED_ONLY", "LIMITED_SOURCED_SEED"]
    scope_note: str = Field(min_length=1, max_length=2000)
    boundaries: list[str] = Field(min_length=1, max_length=20)
    evidence_kind: Literal["VENDOR_PUBLISHED_PACKAGE_NAME"]
    signatures: list[SdkSignature] = Field(min_length=1, max_length=500)
    excluded_namespaces: list[str] = Field(min_length=1, max_length=200)
    exclusion_note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_no_prefix_collisions(self):
        """Two vendors claiming one prefix would make attribution ambiguous."""
        owner: dict[str, str] = {}
        for signature in self.signatures:
            for prefix in signature.package_prefixes:
                if prefix in owner:
                    raise ValueError(
                        f"Package prefix {prefix!r} claimed by "
                        f"{owner[prefix]} and {signature.id}"
                    )
                owner[prefix] = signature.id
        if len({signature.id for signature in self.signatures}) != len(self.signatures):
            raise ValueError("Duplicate signature ids")
        if len(set(self.excluded_namespaces)) != len(self.excluded_namespaces):
            raise ValueError("Duplicate excluded namespaces")
        return self
