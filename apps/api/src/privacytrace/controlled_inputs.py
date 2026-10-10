"""Strict, source-bound inputs for explicitly labelled local controlled evaluation."""

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from .models import Model
from .policy_intake import digest, read_safe


class ControlledCase(Model):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^C[0-9]{2}$")
    name: str = Field(min_length=1, max_length=200)
    package_name: str = Field(min_length=1, max_length=200)
    version_code: int = Field(ge=0, strict=True)
    product_scope: str = Field(min_length=1, max_length=200)
    region: str | None = Field(default=None, min_length=1, max_length=100)
    policy_regions: list[str] = Field(max_length=100)
    preparation: str = Field(min_length=1, max_length=2000)


class ControlledContext(Model):
    case: ControlledCase
    apk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    build_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_hashes: dict[str, str]
    toolchain_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class BuildReceipt(Model):
    schema_version: Literal[1]
    case_id: str = Field(pattern=r"^C[0-9]{2}$")
    source_hashes: dict[str, str]
    toolchain_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    apk: Literal["scenario.apk"]
    apk_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tools: dict[str, str] = Field(min_length=1)
    commands: list[list[str]] = Field(min_length=1, max_length=20)
    built_at: datetime
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)


def load_case(case_dir):
    return ControlledCase.model_validate_json(read_safe(Path(case_dir) / "input.json"))


def source_hashes(case_dir):
    root = Path(case_dir).absolute()
    sources = sorted((root / "src").rglob("*.java"))
    if not sources or len(sources) > 100:
        raise ValueError("Expected a bounded Java source scenario")
    files = [root / "AndroidManifest.xml", *sources]
    return {p.relative_to(root).as_posix(): digest(read_safe(p, root)) for p in files}


def input_hashes(case_dir):
    root = Path(case_dir)
    return {
        name: digest(read_safe(root / name))
        for name in (
            "input.json",
            "policy.txt",
            "candidates.json",
        )
    }


def load_controlled(case_dir, receipt_path):
    case_dir, receipt_path = Path(case_dir).absolute(), Path(receipt_path).absolute()
    case_raw = read_safe(case_dir / "input.json")
    case = ControlledCase.model_validate_json(case_raw)
    raw = read_safe(receipt_path)
    receipt = BuildReceipt.model_validate_json(raw).model_dump(mode="json")
    if receipt["schema_version"] != 1 or receipt["case_id"] != case.case_id:
        raise ValueError("Build receipt does not match the case")
    if receipt["source_hashes"] != source_hashes(case_dir):
        raise ValueError("Source changed since build")
    if receipt["toolchain_sha256"] != digest(read_safe(case_dir.parent / "toolchain.json")):
        raise ValueError("Build configuration changed")
    if receipt["apk"] != "scenario.apk" or not receipt["commands"] or not receipt["tools"]:
        raise ValueError("Missing reproducible build provenance")
    apk = receipt_path.parent / "scenario.apk"
    if digest(read_safe(apk, max_bytes=150 * 1024 * 1024)) != receipt["apk_sha256"]:
        raise ValueError("APK changed since build")
    hashes = input_hashes(case_dir)
    if hashes["input.json"] != digest(case_raw):
        raise ValueError("Case metadata changed while reading")
    context = ControlledContext(
        case=case,
        apk_sha256=receipt["apk_sha256"],
        build_receipt_sha256=digest(raw),
        input_sha256=digest(json.dumps(hashes, sort_keys=True).encode()),
        source_hashes=receipt["source_hashes"],
        toolchain_sha256=receipt["toolchain_sha256"],
    )
    return context, apk, hashes
