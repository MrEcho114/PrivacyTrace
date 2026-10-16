"""Untrusted model metadata and candidates must not block manual capture."""

import json
import sys

import pytest

from privacytrace import policy_intake
from privacytrace.policy_llm_extractor import (
    LLMExtractorConfig,
    MockLLMClient,
    PolicyLLMExtractor,
    UrllibLLMClient,
)


def _capture(tmp_path, monkeypatch, entrypoint, response, tokens):
    raw = tmp_path / "policy.txt"
    raw.write_text("我们访问位置。", encoding="utf-8")
    manual = [{"excerpt": "位置", "data_type": "LOCATION"}]
    output = tmp_path / "capture"
    if entrypoint == "cli":
        candidates = tmp_path / "candidates.json"
        candidates.write_text(json.dumps(manual), encoding="utf-8")
        monkeypatch.setattr(UrllibLLMClient, "call", lambda *_: (response, tokens))
        monkeypatch.setattr(sys, "argv", [
            "policy_intake", "--raw", str(raw), "--source-url", "https://example.org/p",
            "--version", "1", "--output-dir", str(output),
            "--candidates", str(candidates), "--enable-llm",
        ])
        assert policy_intake.main() == 0
        path = output / "policy.capture.json"
    else:
        extractor = PolicyLLMExtractor(LLMExtractorConfig(
            enabled=True, client=MockLLMClient(lambda *_: (response, tokens)),
        ))
        path = policy_intake.capture(
            raw, "https://example.org/p", "1", output,
            candidates=manual, llm_extractor=extractor,
        )
    record = policy_intake.load_policy(path)
    assert len(record["claims"]) == 1
    assert record["claims"][0]["data_type"] == "LOCATION"
    assert record["document"]["review_status"] == "UNREVIEWED"
    provenance = json.loads((output / "policy.audits.json").read_text())
    assert provenance[0]["actor"] == "Codex-assisted candidate"
    return json.loads((output / "policy.llm-execution.json").read_text())


@pytest.mark.parametrize("entrypoint", ["cli", "programmatic"])
@pytest.mark.parametrize("tokens", [
    {"prompt_tokens": -1, "completion_tokens": 2, "total_tokens": 1},
    {"prompt_tokens": 1.5, "completion_tokens": 2, "total_tokens": 4},
    {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3},
    {"prompt_tokens": 1, "completion_tokens": None, "total_tokens": 1},
    {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 0},
])
def test_invalid_token_usage_preserves_manual_capture(
    tmp_path, monkeypatch, entrypoint, tokens,
):
    audit = _capture(tmp_path, monkeypatch, entrypoint, "[]", tokens)
    assert audit["status"] == "FAILED"
    assert audit["failed_spans"][0]["code"] == "INVALID_LLM_RESPONSE"
    assert audit["prompt_tokens"] == audit["completion_tokens"] == audit["total_tokens"] == 0


@pytest.mark.parametrize("entrypoint", ["cli", "programmatic"])
def test_missing_total_tokens_is_derived_from_valid_components(
    tmp_path, monkeypatch, entrypoint,
):
    audit = _capture(tmp_path, monkeypatch, entrypoint, "[]", {
        "prompt_tokens": 10, "completion_tokens": 4,
    })
    assert audit["status"] == "SUCCESS"
    assert audit["total_tokens"] == 14


@pytest.mark.parametrize("entrypoint", ["cli", "programmatic"])
def test_schema_invalid_model_candidate_does_not_block_manual_capture(
    tmp_path, monkeypatch, entrypoint,
):
    response = json.dumps([{
        "excerpt": "位置", "data_type": "LOCATION", "condition": "x" * 10001,
    }])
    audit = _capture(tmp_path, monkeypatch, entrypoint, response, {})
    assert audit["status"] == "PARTIAL"
    assert audit["rejected_count"] == 1
    assert audit["extracted_candidates"] == 0
