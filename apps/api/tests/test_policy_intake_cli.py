"""Public offline capture CLI acceptance, without private-method mocks."""

import hashlib
import json
import subprocess
import sys

import pytest


def invoke(*args):
    process = subprocess.run(
        [sys.executable, "-m", "privacytrace.policy_intake", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return process, json.loads(process.stdout)


@pytest.fixture
def captured(tmp_path):
    text = "\ufeff隐私😀\r\n我们不访问联系人。仅在用户授权时访问位置。\r\n末尾"
    raw = tmp_path / "raw.txt"
    raw.write_bytes(text.encode("utf-8"))
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            [
                {
                    "excerpt": "我们不访问联系人。",
                    "data_type": "CONTACTS",
                    "polarity": "NEGATIVE",
                    "subject": "HOST_APP",
                },
                {
                    "excerpt": "仅在用户授权时访问位置。",
                    "data_type": "LOCATION",
                    "polarity": "AFFIRMATIVE",
                    "condition": "用户授权",
                    "subject": "HOST_APP",
                },
                {"excerpt": "末尾", "data_type": "CONTACTS"},
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "capture"
    args = [
        "--raw",
        raw,
        "--source-url",
        "https://example.org/privacy",
        "--version",
        "1",
        "--output-dir",
        out,
        "--candidates",
        candidates,
        "--package",
        "org.example",
        "--version-code",
        "7",
    ]
    process, summary = invoke(*args)
    assert process.returncode == 0, process.stderr + process.stdout
    return text, out, args, summary


def test_lossless_spans_negative_conditional_unknown_and_audits(captured):
    text, out, _, summary = captured
    record = json.loads((out / "policy.capture.json").read_bytes())
    assert summary["human_review_gate"] == "NOT_REQUIRED_BY_WORKFLOW"
    assert record["human_review_gate"] == "NOT_REQUIRED_BY_WORKFLOW"
    assert (out / "policy.raw.txt").read_bytes() == text.encode()
    assert (out / "policy.processed.txt").read_bytes() == text.encode()
    assert record["document"]["artifact"]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert "".join(chunk["text"] for chunk in record["chunks"]) == text
    for chunk in record["chunks"]:
        assert text[chunk["start"] : chunk["end"]] == chunk["text"]
    assert record["claims"][0]["polarity"] == "NEGATIVE"
    assert record["claims"][1]["condition"] == "用户授权"
    assert record["claims"][2]["polarity"] == "UNKNOWN"
    assert record["claims"][2]["subject"] == "UNKNOWN"
    assert record["claims"][2]["action"] == "UNKNOWN"
    assert record["document"]["review_status"] == "UNREVIEWED"
    assert record["document"]["extraction_status"] == "PARTIAL"
    assert record["document"]["attachments_status"] == "NOT_CHECKED"
    audits = json.loads((out / "policy.audits.json").read_bytes())
    for audit, claim in zip(audits, record["claims"], strict=True):
        assert audit["old"] is None
        assert audit["new"] == claim
        assert audit["actor"] == "Codex-assisted candidate"
        assert audit["evidence_ids"] == claim["evidence_ids"]
    # CLI output never contains private policy text.
    assert text not in json.dumps(summary)


def test_reject_overwrite(captured):
    _, _, args, _ = captured
    process, body = invoke(*args)
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"


@pytest.mark.parametrize(
    "source", ["http://example.org/policy", "https://user:secret@example.org/p"]
)
def test_reject_non_https_or_credentials(tmp_path, source):
    raw = tmp_path / "raw.txt"
    raw.write_text("policy", encoding="utf-8")
    process, body = invoke(
        "--raw", raw, "--source-url", source, "--version", "1", "--output-dir", tmp_path / "out"
    )
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"
    assert "secret" not in process.stdout


@pytest.mark.parametrize("text", ["", "a" * 200001], ids=["empty", "oversize"])
def test_text_limits(tmp_path, text):
    raw = tmp_path / "raw.txt"
    raw.write_bytes(text.encode())
    process, _ = invoke(
        "--raw",
        raw,
        "--source-url",
        "https://example.org/p",
        "--version",
        "1",
        "--output-dir",
        tmp_path / "out",
    )
    assert process.returncode == 1


def test_duplicate_excerpt_requires_span(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_text("same same", encoding="utf-8")
    candidates = tmp_path / "candidates.json"
    candidates.write_text('[{"excerpt":"same","data_type":"CONTACTS"}]', encoding="utf-8")
    args = [
        "--raw",
        raw,
        "--source-url",
        "https://example.org/p",
        "--version",
        "1",
        "--candidates",
        candidates,
        "--output-dir",
        tmp_path / "out",
    ]
    process, _ = invoke(*args)
    assert process.returncode == 1
    candidates.write_text(
        '[{"start_offset":5,"end_offset":9,"data_type":"CONTACTS"}]', encoding="utf-8"
    )
    process, _ = invoke(*args)
    assert process.returncode == 0


def test_maximum_text_and_large_chunk_are_lossless(tmp_path):
    raw = tmp_path / "raw.txt"
    text = "中" * 200000
    raw.write_bytes(text.encode())
    out = tmp_path / "out"
    process, _ = invoke(
        "--raw", raw, "--source-url", "https://example.org/p", "--version", "1", "--output-dir", out
    )
    assert process.returncode == 0, process.stdout
    record = json.loads((out / "policy.capture.json").read_bytes())
    assert len(record["chunks"]) == 20
    assert "".join(chunk["text"] for chunk in record["chunks"]) == text


def test_invalid_utf8_is_rejected(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_bytes(b"\xff\xfe")
    process, _ = invoke(
        "--raw",
        raw,
        "--source-url",
        "https://example.org/p",
        "--version",
        "1",
        "--output-dir",
        tmp_path / "out",
    )
    assert process.returncode == 1


def test_maximum_punctuation_policy_publishes_complete_capture(tmp_path):
    raw = tmp_path / "raw.txt"
    text = "。" * 200000
    raw.write_bytes(text.encode("utf-8"))
    out = tmp_path / "out"
    process, body = invoke(
        "--raw", raw, "--source-url", "https://example.org/p", "--version", "1", "--output-dir", out
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert body["status"] == "CAPTURED_UNREVIEWED"
    record = json.loads((out / "policy.capture.json").read_bytes())
    assert len(record["chunks"]) == 200000
    assert "".join(chunk["text"] for chunk in record["chunks"]) == text
    assert set(p.name for p in out.iterdir()) == {
        "policy.raw.txt",
        "policy.processed.txt",
        "policy.capture.json",
        "policy.audits.json",
    }
    assert not list(tmp_path.glob(".policy-capture-*"))


def test_oversize_serialized_capture_rejected_without_partial_output(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_bytes(("。" * 200000).encode("utf-8"))
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            [
                {
                    "start_offset": 0,
                    "end_offset": 1,
                    "data_type": "CONTACTS",
                    "declared_purpose": "x" * (19 * 1024 * 1024),
                }
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    args = [
        "--raw",
        raw,
        "--source-url",
        "https://example.org/p",
        "--version",
        "1",
        "--output-dir",
        out,
        "--candidates",
        candidates,
    ]
    process, body = invoke(*args)
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"
    assert not out.exists()
    assert not list(tmp_path.glob(".policy-capture-*"))
    # A rejected preflight must not poison a later valid capture at the same path.
    candidates.write_text("[]", encoding="utf-8")
    process, _ = invoke(*args)
    assert process.returncode == 0


def test_existing_empty_directory_is_not_replaced(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_bytes(b"policy")
    out = tmp_path / "existing"
    out.mkdir()
    process, _ = invoke(
        "--raw", raw, "--source-url", "https://example.org/p", "--version", "1", "--output-dir", out
    )
    assert process.returncode == 1
    assert list(out.iterdir()) == []
    assert not list(tmp_path.glob(".policy-capture-*"))


def test_policy_intake_cli_enable_llm_cached(tmp_path):
    from privacytrace.policy_llm_extractor import (
        ACTIVE_RULESET_VERSION,
        PROMPT_VERSION,
        compute_cache_key,
    )

    sentence = "我们仅在您开启定位权限后收集您的地理位置信息以提供导航服务。"
    raw = tmp_path / "raw.txt"
    raw.write_bytes(sentence.encode("utf-8"))

    cache_dir = tmp_path / "llm_cache"
    cache_dir.mkdir()
    cache_key = compute_cache_key(
        model="gpt-4o-mini",
        prompt_version=PROMPT_VERSION,
        ruleset_version=ACTIVE_RULESET_VERSION,
        text=sentence,
    )
    cached_payload = {
        "raw_items": [
            {
                "excerpt": "地理位置信息",
                "data_type": "LOCATION",
                "polarity": "AFFIRMATIVE",
                "condition": "开启定位权限",
                "declared_purpose": "提供导航服务",
            }
        ],
        "tokens": {"prompt_tokens": 15, "completion_tokens": 10, "total_tokens": 25},
    }
    (cache_dir / f"{cache_key}.json").write_text(
        json.dumps(cached_payload, ensure_ascii=False), encoding="utf-8"
    )

    out = tmp_path / "out"
    args = [
        "--raw",
        raw,
        "--source-url",
        "https://example.org/p",
        "--version",
        "1",
        "--output-dir",
        out,
        "--enable-llm",
        "--llm-cache-dir",
        cache_dir,
    ]
    process, body = invoke(*args)
    assert process.returncode == 0, process.stderr
    assert body["status"] == "CAPTURED_UNREVIEWED"
    assert body["claims"] == 1
    assert "llm_extraction" in body
    assert body["llm_extraction"]["status"] == "SUCCESS"
    assert body["llm_extraction"]["cached"] is True
    assert body["llm_extraction"]["extracted_claims"] == 1

    record = json.loads((out / "policy.capture.json").read_bytes())
    assert len(record["claims"]) == 1
    claim = record["claims"][0]
    assert claim["data_type"] == "LOCATION"
    assert claim["polarity"] == "AFFIRMATIVE"
    assert claim["condition"] == "开启定位权限"
    assert claim["declared_purpose"] == "提供导航服务"

    audits = json.loads((out / "policy.audits.json").read_bytes())
    assert len(audits) == 1
    assert audits[0]["actor"] == "LLM-assisted candidate (gpt-4o-mini)"
    assert audits[0]["authority"] == "UNAUTHENTICATED_INITIAL_CANDIDATE"

