"""Portable package drift and synthetic compatibility; never live discovery/model proof."""

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from privacytrace.main import create_app
from privacytrace.policy_llm_extractor import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    LLMExtractorConfig,
    MockLLMClient,
    PolicyLLMExtractor,
)
from privacytrace.resources import ACTIVE_RULESET_VERSION
from privacytrace.web_models import WebSource

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "skills/privacytrace-policy-collection"
EXAMPLES = json.loads((PACKAGE / "assets/examples.json").read_text(encoding="utf-8"))
HEADERS = {"X-PrivacyTrace-Local": "1"}


def test_exports_are_current_and_canonical_prompt_is_unchanged():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/export-policy-collection.py"), "--check"],
        cwd=ROOT, check=True,
    )
    manifest = json.loads((PACKAGE / "references/manifest.json").read_text(encoding="utf-8"))
    assert manifest["prompt_version"] == PROMPT_VERSION
    assert manifest["ruleset_version"] == ACTIVE_RULESET_VERSION
    exported = (PACKAGE / "references/extraction-prompt.txt").read_text(encoding="utf-8")
    assert exported == SYSTEM_PROMPT
    for name, expected in manifest["generated_files"].items():
        content = (PACKAGE / name).read_text(encoding="utf-8").encode("utf-8")
        assert hashlib.sha256(content).hexdigest() == expected


def test_skill_references_are_portable_and_not_scaffold_placeholders():
    skill = (PACKAGE / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: privacytrace-policy-collection\n")
    for link in re.findall(r"\]\(([^)]+)\)", skill):
        target = (PACKAGE / link).resolve()
        assert target.is_relative_to(PACKAGE)
        assert target.is_file()
    instructions = (PACKAGE / "references/collection-instructions.md").read_text(encoding="utf-8")
    assert "{{" not in instructions
    assert SYSTEM_PROMPT not in instructions  # Optional extraction stays a separate mode.


@pytest.mark.parametrize("example", EXAMPLES["collection"], ids=lambda x: x["case"])
def test_collection_examples_match_existing_source_fields(example):
    output = example["output"]
    assert output["format_version"] == "privacytrace-policy-collection/1"
    assert 1 <= len(output["results"]) <= 8
    ids = []
    for result in output["results"]:
        assert set(result) <= {"discovery_status", "source", "reported_at"}
        if result.get("reported_at") is not None:
            assert datetime.fromisoformat(result["reported_at"]).tzinfo is not None
        state, source = result["discovery_status"], result["source"]
        if source is None:
            assert state in {"NO_NETWORK", "NOT_FOUND"}
            continue
        value = WebSource.model_validate(source)
        ids.append(value.id)
        assert not set(source) & {
            "status", "error_code", "captured_at", "sha256", "final_url", "model_audit",
        }
        if state in {"TEXT_RETRIEVED", "USER_PROVIDED"}:
            assert value.text.strip()
            assert "source_type" in source
        else:
            assert state in {"URL_ONLY", "NO_NETWORK", "FETCH_FAILED"}
            assert value.text == ""
        if state != "USER_PROVIDED":
            assert value.url.startswith("https://example.invalid/")
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("example", EXAMPLES["extraction"], ids=lambda x: x["case"])
def test_packaged_candidates_use_the_existing_verbatim_validator(example):
    raw = example.get("raw_response", json.dumps(example.get("candidates", [])))
    client = MockLLMClient(handler=lambda _system, _user: raw)
    extractor = PolicyLLMExtractor(LLMExtractorConfig(enabled=True, client=client, max_retries=1))
    result = extractor.extract_from_chunk(example["text"], full_text=example["text"])
    assert len(result.candidates) == example["accepted"]
    assert client.calls[0]["system"] == (PACKAGE / "references/extraction-prompt.txt").read_text(
        encoding="utf-8",
    )
    if example["case"] == "unknown_subject":
        assert result.candidates[0]["subject"] == "UNKNOWN"
        assert result.candidates[0]["action"] == "UNKNOWN"
    if example["case"] == "injected_instruction":
        assert "<untrusted_policy_text>" in client.calls[0]["user"]
        assert result.candidates[0]["excerpt"] == "我们不会读取联系人。"


def test_text_examples_keep_original_http_semantics(tmp_path):
    # Exercise the documented source projection through the existing public local endpoint.
    # This intentionally does not implement #70's future envelope importer.
    app = create_app(tmp_path)
    with TestClient(app) as client:
        for case, text in (
            ("retrieved_zh_unknown_applicability", "我们不会读取联系人。"),
            ("manual_en", "The SDK may access coarse location with your permission."),
        ):
            example = next(x for x in EXAMPLES["collection"] if x["case"] == case)
            source = example["output"]["results"][0]["source"]
            packaged = client.post(
                "/api/v1/web/drafts", headers=HEADERS,
                json={"name": "Packaged synthetic", "sources": [source]},
            )
            direct = client.post(
                "/api/v1/web/drafts", headers=HEADERS,
                json={"name": "Direct synthetic", "sources": [{**source, "text": text}]},
            )
            assert packaged.status_code == direct.status_code == 200
            actual = packaged.json()["sources"][0]
            original = direct.json()["sources"][0]
            for field in ("text", "sha256", "source_type", "version", "status", "package_name"):
                assert actual[field] == original[field]
            assert actual["status"] == "manual"
            assert actual["model_audit"] == {}
            # Read through the same intake semantic seam used by ordinary requests.
            captures = app.state.web_intake.captures(packaged.json(), require_checked=False)
            document = captures[0]["document"]
            assert document.artifact.text == text
            assert document.review_status == "UNREVIEWED"
            assert document.completeness == "PARTIAL"
            assert document.attachments_status == "NOT_CHECKED"
            assert captures[0]["claims"] == []
