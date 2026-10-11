"""Regression tests for versioned LLM capture, provenance and resource safety."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from privacytrace.policy_intake import (
    capture,
    load_policy,
    merge_llm_candidates,
)
from privacytrace.policy_llm_extractor import (
    LLMExtractorConfig,
    MockLLMClient,
    PolicyLLMExtractor,
)


def _policy(tmp_path):
    raw = tmp_path / "policy.txt"
    raw.write_text("我们收集位置信息。", encoding="utf-8")
    return raw


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("subject", "THIRD_PARTY"),
        ("declared_recipient", "SDK provider"),
        ("declared_purpose", "advertising"),
        ("condition", "with consent"),
        ("polarity", "NEGATIVE"),
        ("action", "ACCESS"),
    ],
)
def test_semantic_differences_survive_and_are_audited(field, value):
    text = "我们收集位置信息。"
    manual = {"excerpt": "位置信息", "data_type": "LOCATION"}
    llm = {**manual, field: value}
    combined, sources, conflicts, dropped = merge_llm_candidates(
        text, [manual], [llm], "test-model"
    )
    assert len(combined) == 2
    assert dropped == 0
    assert len(conflicts) == 1
    assert field in conflicts[0]["fields"]
    assert conflicts[0]["other_candidate_index"] == 2
    assert conflicts[0]["requires_human_review"] is True
    assert sources[1][0].startswith("LLM-assisted candidate")
    assert sources[0][0] == "Codex-assisted candidate"


def test_duplicate_with_manual_missing_offsets_keeps_manual_provenance():
    text = "我们收集位置信息。"
    manual = {"excerpt": "位置信息", "data_type": "LOCATION"}
    llm = {
        "excerpt": "位置信息", "data_type": "LOCATION",
        "start_offset": text.index("位置信息"),
        "end_offset": text.index("位置信息") + len("位置信息"),
        "polarity": "UNKNOWN", "subject": "UNKNOWN", "action": "UNKNOWN",
    }
    merged, sources, conflicts, dropped = merge_llm_candidates(
        text, [manual], [llm], "test-model"
    )
    assert merged == [manual]
    assert sources == {}
    assert conflicts == []
    assert dropped == 0


def test_programmatic_llm_capture_produces_hash_checked_v2_audit(tmp_path):
    raw = _policy(tmp_path)
    mock = MockLLMClient(lambda s, u: json.dumps([{
        "excerpt": "位置信息", "data_type": "LOCATION",
        "subject": "THIRD_PARTY",
    }], ensure_ascii=False))
    extractor = PolicyLLMExtractor(
        LLMExtractorConfig(enabled=True, client=mock, model="audit-test-model")
    )
    manual = [{"excerpt": "位置信息", "data_type": "LOCATION",
               "subject": "HOST_APP"}]
    output = tmp_path / "out"
    path = capture(
        raw, "https://example.org/privacy", "1", output,
        candidates=manual, llm_extractor=extractor,
    )
    record = load_policy(path)
    assert record["schema_version"] == 2
    assert len(record["claims"]) == 2
    assert record["document"]["review_status"] == "UNREVIEWED"
    entry = record["files"]["llm_execution"]
    audit_bytes = (output / entry["path"]).read_bytes()
    assert hashlib.sha256(audit_bytes).hexdigest() == entry["sha256"]
    audit = json.loads(audit_bytes)
    assert audit["status"] == "SUCCESS"
    assert audit["model"] == "audit-test-model"
    assert audit["prompt_version"] and audit["ruleset_version"]
    assert len(audit["prompt_sha256"]) == 64
    assert len(audit["endpoint_identifier"]) == 64
    assert audit["document_sha256"] == record["document"]["artifact"]["sha256"]
    assert audit["processed_spans"] == 1
    assert len(audit["candidate_conflicts"]) == 1
    assert "subject" in audit["candidate_conflicts"][0]["fields"]
    assert audit["requires_human_review"] is True
    assert "Authorization" not in json.dumps(audit)
    assert mock.call_count == 1

    # Tampering with the audit file must invalidate the manifest.
    (output / entry["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="failed validation"):
        load_policy(path)


def test_disabled_capture_remains_schema_v1(tmp_path):
    raw = _policy(tmp_path)
    record = load_policy(capture(
        raw, "https://example.org/privacy", "1", tmp_path / "out"
    ))
    assert record["schema_version"] == 1
    assert set(record["files"]) == {"raw", "processed", "audits"}


def test_llm_fails_without_network_and_audit_is_still_published(tmp_path):
    raw = _policy(tmp_path)
    client = MockLLMClient(lambda s, u: "{not valid json")
    extractor = PolicyLLMExtractor(LLMExtractorConfig(
        enabled=True, client=client, max_retries=1,
    ))
    path = capture(raw, "https://example.org/p", "1",
                   tmp_path / "out", llm_extractor=extractor)
    record = load_policy(path)
    audit = json.loads((tmp_path / "out" / "policy.llm-execution.json").read_text())
    assert audit["status"] == "FAILED"
    assert audit["failed_spans"][0]["code"] == "INVALID_LLM_RESPONSE"
    assert audit["requires_human_review"] is True
    assert len(record["claims"]) == 0


@pytest.mark.parametrize("kwargs", [
    {"version_code": -1},
    {"package": ""},
    {"product_scope": ""},
    {"regions": [""]},
    {"regions": ["CN"] * 101},
])
def test_invalid_metadata_does_not_call_model(tmp_path, kwargs):
    raw = _policy(tmp_path)
    mock = MockLLMClient()
    extractor = PolicyLLMExtractor(
        LLMExtractorConfig(enabled=True, client=mock)
    )
    with pytest.raises(ValueError):
        capture(raw, "https://example.org/p", "1",
                tmp_path / "out", llm_extractor=extractor, **kwargs)
    assert mock.call_count == 0
    assert not (tmp_path / "out").exists()


def test_cache_writer_does_not_follow_directory_symlink_or_corrupt_parallel(tmp_path):
    source = tmp_path / "cache"
    actual = tmp_path / "actual"
    actual.mkdir()
    source.symlink_to(actual, target_is_directory=True)
    extractor = PolicyLLMExtractor(LLMExtractorConfig(cache_dir=source))
    extractor._write_cache("a" * 64, {"raw_items": []})
    assert list(actual.iterdir()) == []

    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    other = PolicyLLMExtractor(LLMExtractorConfig(cache_dir=safe))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(other._write_cache, "b" * 64, {"raw_items": [i]})
            for i in range(2)
        ]
        for result in futures:
            result.result()
    files = list(safe.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["raw_items"] in ([0], [1])
    assert list(safe.glob("*.tmp")) == []


def test_response_and_per_chunk_candidate_limits(tmp_path):
    raw = _policy(tmp_path)
    enormous = MockLLMClient(lambda s, u: "x" * 500)
    ex1 = PolicyLLMExtractor(LLMExtractorConfig(
        enabled=True, client=enormous, max_response_bytes=50,
    ))
    result1 = ex1.extract_from_spans(raw.read_text(encoding="utf-8"), [
        {"start": 0, "end": len(raw.read_text()), "text": raw.read_text()}
    ])
    assert result1.status == "FAILED"
    assert enormous.call_count == 1
    assert "RESPONSE_TOO_LARGE" in " ".join(result1.telemetry.errors)

    multiple = MockLLMClient(lambda s, u: json.dumps([
        {"excerpt": "位置信息", "data_type": "LOCATION"}
        for _ in range(3)
    ], ensure_ascii=False))
    ex2 = PolicyLLMExtractor(LLMExtractorConfig(
        enabled=True, client=multiple, max_candidates_per_response=2,
    ))
    result2 = ex2.extract_from_chunk(raw.read_text(encoding="utf-8"))
    assert result2.status == "FAILED"
    assert multiple.call_count == 1
    assert "CANDIDATE_RESPONSE_LIMIT" in " ".join(result2.telemetry.errors)
