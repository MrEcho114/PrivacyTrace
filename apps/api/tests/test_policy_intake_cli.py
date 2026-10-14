import hashlib
import json
import os
import subprocess
import sys

import pytest

from privacytrace.policy_llm_extractor import CACHE_FILE_PREFIX


def invoke(*args, env=None):
    merged_env = {**os.environ, **env} if env is not None else None
    process = subprocess.run(
        [sys.executable, "-m", "privacytrace.policy_intake", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=merged_env,
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
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key}.json").write_text(
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


def test_policy_intake_cli_malformed_llm_json_fields_graceful_recovery(tmp_path):
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
    # LLM returned list for polarity, dict for subject, invalid string for action
    cached_payload = {
        "raw_items": [
            {
                "excerpt": "地理位置信息",
                "data_type": "LOCATION",
                "polarity": ["AFFIRMATIVE"],
                "subject": {"invalid": "object"},
                "action": 999,
                "condition": [],
                "declared_purpose": {},
            }
        ],
        "tokens": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key}.json").write_text(
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

    record = json.loads((out / "policy.capture.json").read_bytes())
    claim = record["claims"][0]
    assert claim["data_type"] == "LOCATION"
    assert claim["polarity"] == "UNKNOWN"
    assert claim["subject"] == "UNKNOWN"
    assert claim["action"] == "UNKNOWN"


def test_policy_intake_cli_mixed_candidates_distinct_audits(tmp_path):
    from privacytrace.policy_llm_extractor import (
        ACTIVE_RULESET_VERSION,
        PROMPT_VERSION,
        compute_cache_key,
    )

    full_policy = "我们不访问联系人。\n我们仅在您开启定位权限后收集您的地理位置信息以提供导航服务。"
    raw = tmp_path / "raw.txt"
    raw.write_bytes(full_policy.encode("utf-8"))

    # 1. Manual candidate for first sentence
    manual_cand_file = tmp_path / "manual_candidates.json"
    manual_cand_file.write_text(
        json.dumps(
            [
                {
                    "excerpt": "我们不访问联系人。",
                    "data_type": "CONTACTS",
                    "polarity": "NEGATIVE",
                    "subject": "HOST_APP",
                }
            ]
        ),
        encoding="utf-8",
    )

    # 2. Cached LLM response for second sentence
    cache_dir = tmp_path / "llm_cache"
    cache_dir.mkdir()
    second_sentence = "我们仅在您开启定位权限后收集您的地理位置信息以提供导航服务。"
    cache_key_2 = compute_cache_key(
        model="gpt-4o-mini",
        prompt_version=PROMPT_VERSION,
        ruleset_version=ACTIVE_RULESET_VERSION,
        text=second_sentence,
    )
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key_2}.json").write_text(
        json.dumps(
            {
                "raw_items": [
                    {
                        "excerpt": "地理位置信息",
                        "data_type": "LOCATION",
                        "polarity": "AFFIRMATIVE",
                        "condition": "开启定位权限",
                        "action": "ACCESS",
                    }
                ],
                "tokens": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # First sentence cache empty so it doesn't double add
    first_sentence = "我们不访问联系人。\n"
    cache_key_1 = compute_cache_key(
        model="gpt-4o-mini",
        prompt_version=PROMPT_VERSION,
        ruleset_version=ACTIVE_RULESET_VERSION,
        text=first_sentence,
    )
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key_1}.json").write_text(
        json.dumps({"raw_items": [], "tokens": {}}, ensure_ascii=False), encoding="utf-8"
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
        manual_cand_file,
        "--enable-llm",
        "--llm-cache-dir",
        cache_dir,
    ]
    process, body = invoke(*args)
    assert process.returncode == 0, process.stderr
    assert body["status"] == "CAPTURED_UNREVIEWED"
    assert body["claims"] == 2

    audits = json.loads((out / "policy.audits.json").read_bytes())
    assert len(audits) == 2
    # Manual candidate audit provenance
    assert audits[0]["actor"] == "Codex-assisted candidate"
    assert audits[0]["reason"] == "Initial offline candidate capture"
    # LLM-assisted candidate audit provenance
    assert audits[1]["actor"] == "LLM-assisted candidate (gpt-4o-mini)"
    assert audits[1]["reason"] == "LLM-assisted candidate extraction with verbatim verification"


def test_policy_intake_cli_duplicate_candidate_preserves_manual_provenance(tmp_path):
    from privacytrace.policy_llm_extractor import (
        ACTIVE_RULESET_VERSION,
        PROMPT_VERSION,
        compute_cache_key,
    )

    sentence = "我们仅在您开启定位权限后收集您的地理位置信息以提供导航服务。"
    raw = tmp_path / "raw.txt"
    raw.write_bytes(sentence.encode("utf-8"))

    # Both manual and LLM extract the exact same claim
    manual_cand_file = tmp_path / "manual_candidates.json"
    manual_cand_file.write_text(
        json.dumps(
            [
                {
                    "excerpt": "地理位置信息",
                    "data_type": "LOCATION",
                    "polarity": "AFFIRMATIVE",
                }
            ]
        ),
        encoding="utf-8",
    )

    cache_dir = tmp_path / "llm_cache"
    cache_dir.mkdir()
    cache_key = compute_cache_key(
        model="gpt-4o-mini",
        prompt_version=PROMPT_VERSION,
        ruleset_version=ACTIVE_RULESET_VERSION,
        text=sentence,
    )
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key}.json").write_text(
        json.dumps(
            {
                "raw_items": [
                    {
                        "excerpt": "地理位置信息",
                        "data_type": "LOCATION",
                        "polarity": "AFFIRMATIVE",
                    }
                ],
                "tokens": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
            ensure_ascii=False,
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
        manual_cand_file,
        "--enable-llm",
        "--llm-cache-dir",
        cache_dir,
    ]
    process, body = invoke(*args)
    assert process.returncode == 0, process.stderr
    # Duplicate was deduplicated: total claims is 1
    assert body["claims"] == 1

    audits = json.loads((out / "policy.audits.json").read_bytes())
    assert len(audits) == 1
    # Manual origin must be preserved
    assert audits[0]["actor"] == "Codex-assisted candidate"
    assert audits[0]["reason"] == "Initial offline candidate capture"


def test_policy_intake_cli_api_base_config_and_validation(tmp_path):
    from privacytrace.policy_llm_extractor import (
        ACTIVE_RULESET_VERSION,
        PROMPT_VERSION,
        compute_cache_key,
    )

    sentence = "我们仅在您开启定位权限后收集您的地理位置信息以提供导航服务。"
    raw = tmp_path / "raw.txt"
    raw.write_bytes(sentence.encode("utf-8"))

    custom_base = "http://127.0.0.1:8999/v1"
    cache_dir = tmp_path / "llm_cache"
    cache_dir.mkdir()
    cache_key = compute_cache_key(
        model="gpt-4o-mini",
        prompt_version=PROMPT_VERSION,
        ruleset_version=ACTIVE_RULESET_VERSION,
        text=sentence,
        api_base=custom_base,
    )
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key}.json").write_text(
        json.dumps(
            {
                "raw_items": [
                    {
                        "excerpt": "地理位置信息",
                        "data_type": "LOCATION",
                        "polarity": "AFFIRMATIVE",
                    }
                ],
                "tokens": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Valid custom api_base hits cache matching custom api_base
    out = tmp_path / "out_valid"
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
        "--llm-api-base",
        custom_base,
        "--llm-cache-dir",
        cache_dir,
    ]
    process, body = invoke(*args)
    assert process.returncode == 0, process.stderr
    assert body["claims"] == 1
    assert body["llm_extraction"]["cached"] is True

    # Invalid api_base URL is rejected with error
    out_invalid = tmp_path / "out_invalid"
    args_invalid = [
        "--raw",
        raw,
        "--source-url",
        "https://example.org/p",
        "--version",
        "1",
        "--output-dir",
        out_invalid,
        "--enable-llm",
        "--llm-api-base",
        "ftp://invalid.endpoint/v1",
        "--llm-cache-dir",
        cache_dir,
    ]
    process_bad, body_bad = invoke(*args_invalid)
    assert process_bad.returncode == 1
    assert body_bad["errors"][0]["code"] == "POLICY_INPUT_INVALID"


def test_policy_intake_cli_env_enable_llm(tmp_path):
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
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key}.json").write_text(
        json.dumps(
            {
                "raw_items": [
                    {
                        "excerpt": "地理位置信息",
                        "data_type": "LOCATION",
                        "polarity": "AFFIRMATIVE",
                    }
                ],
                "tokens": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    base_args = [
        "--raw",
        raw,
        "--source-url",
        "https://example.org/p",
        "--version",
        "1",
        "--llm-cache-dir",
        cache_dir,
    ]

    # 1. PRIVACYTRACE_LLM_ENABLED=true without --enable-llm -> enabled
    out1 = tmp_path / "out1"
    proc, body = invoke(*base_args, "--output-dir", out1, env={"PRIVACYTRACE_LLM_ENABLED": "true"})
    assert proc.returncode == 0
    assert "llm_extraction" in body
    assert body["claims"] == 1

    # 2. PRIVACYTRACE_LLM_ENABLED=1 without --enable-llm -> enabled
    out2 = tmp_path / "out2"
    proc, body = invoke(*base_args, "--output-dir", out2, env={"PRIVACYTRACE_LLM_ENABLED": "1"})
    assert proc.returncode == 0
    assert "llm_extraction" in body

    # 3. PRIVACYTRACE_LLM_ENABLED=false without --enable-llm -> disabled
    out3 = tmp_path / "out3"
    proc, body = invoke(*base_args, "--output-dir", out3, env={"PRIVACYTRACE_LLM_ENABLED": "false"})
    assert proc.returncode == 0
    assert "llm_extraction" not in body
    assert body["claims"] == 0

    # 4. PRIVACYTRACE_LLM_ENABLED=0 without --enable-llm -> disabled
    out4 = tmp_path / "out4"
    proc, body = invoke(*base_args, "--output-dir", out4, env={"PRIVACYTRACE_LLM_ENABLED": "0"})
    assert proc.returncode == 0
    assert "llm_extraction" not in body

    # 5. PRIVACYTRACE_LLM_ENABLED=false with explicit --enable-llm -> CLI takes precedence
    out5 = tmp_path / "out5"
    proc, body = invoke(
        *base_args,
        "--output-dir",
        out5,
        "--enable-llm",
        env={"PRIVACYTRACE_LLM_ENABLED": "false"},
    )
    assert proc.returncode == 0
    assert "llm_extraction" in body
    assert body["claims"] == 1

    # 6. Invalid boolean value -> fails with POLICY_INPUT_INVALID
    out6 = tmp_path / "out6"
    proc, body = invoke(
        *base_args,
        "--output-dir",
        out6,
        env={"PRIVACYTRACE_LLM_ENABLED": "not_a_valid_bool"},
    )
    assert proc.returncode == 1
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"

    # 7. PRIVACYTRACE_LLM_ENABLED=true with explicit --no-enable-llm -> CLI takes precedence
    out7 = tmp_path / "out7"
    proc, body = invoke(
        *base_args,
        "--output-dir",
        out7,
        "--no-enable-llm",
        env={"PRIVACYTRACE_LLM_ENABLED": "true"},
    )
    assert proc.returncode == 0
    assert "llm_extraction" not in body
    assert body["claims"] == 0


def test_policy_intake_cli_local_http_server_end_to_end(tmp_path):
    import http.server
    import threading

    captured = []

    class LocalServerHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)
            captured.append(json.loads(body.decode("utf-8")))

            resp_payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "excerpt": "地理位置信息",
                                        "data_type": "LOCATION",
                                        "polarity": "AFFIRMATIVE",
                                        "condition": "开启定位权限",
                                        "action": "ACCESS",
                                    }
                                ]
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 15, "completion_tokens": 8, "total_tokens": 23},
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_payload).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), LocalServerHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        sentence = "我们仅在您开启定位权限后收集您的地理位置信息以提供导航服务。"
        raw = tmp_path / "raw.txt"
        raw.write_bytes(sentence.encode("utf-8"))
        out = tmp_path / "out_http"

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
            "--llm-api-base",
            f"http://127.0.0.1:{port}/v1",
            "--llm-model",
            "test-local-model",
        ]
        process, body = invoke(*args)
        assert process.returncode == 0, process.stderr
        assert body["status"] == "CAPTURED_UNREVIEWED"
        assert body["claims"] == 1
        assert "llm_extraction" in body
        assert body["llm_extraction"]["status"] == "SUCCESS"
        assert body["llm_extraction"]["cached"] is False
        assert body["llm_extraction"]["extracted_claims"] == 1
        assert body["llm_extraction"]["total_tokens"] == 23

        assert len(captured) == 1
        assert captured[0]["model"] == "test-local-model"
    finally:
        server.shutdown()
        server.server_close()


def test_policy_intake_cli_malformed_candidates_list_graceful_exit(tmp_path):
    sentence = "我们收集地理位置信息。"
    raw = tmp_path / "raw.txt"
    raw.write_bytes(sentence.encode("utf-8"))

    # Candidate file containing a string instead of dict
    cand_file = tmp_path / "bad_candidates.json"
    cand_file.write_text(json.dumps(["not a dict candidate"]), encoding="utf-8")

    out = tmp_path / "out_bad"
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
        cand_file,
    ]
    process, body = invoke(*args)
    assert process.returncode == 1
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"


def test_policy_intake_cli_duplicate_candidate_distinct_polarity_preserves_manual(tmp_path):
    from privacytrace.policy_llm_extractor import (
        ACTIVE_RULESET_VERSION,
        PROMPT_VERSION,
        compute_cache_key,
    )

    sentence = "我们仅在您开启定位权限后收集您的地理位置信息以提供导航服务。"
    raw = tmp_path / "raw.txt"
    raw.write_bytes(sentence.encode("utf-8"))

    # Manual candidate specifies NEGATIVE polarity
    manual_cand_file = tmp_path / "manual_candidates.json"
    manual_cand_file.write_text(
        json.dumps(
            [
                {
                    "excerpt": "地理位置信息",
                    "data_type": "LOCATION",
                    "polarity": "NEGATIVE",
                    "condition": "严格限制",
                }
            ]
        ),
        encoding="utf-8",
    )

    cache_dir = tmp_path / "llm_cache"
    cache_dir.mkdir()
    cache_key = compute_cache_key(
        model="gpt-4o-mini",
        prompt_version=PROMPT_VERSION,
        ruleset_version=ACTIVE_RULESET_VERSION,
        text=sentence,
    )
    # LLM extracts the same excerpt/data_type but with AFFIRMATIVE polarity
    (cache_dir / f"{CACHE_FILE_PREFIX}{cache_key}.json").write_text(
        json.dumps(
            {
                "raw_items": [
                    {
                        "excerpt": "地理位置信息",
                        "data_type": "LOCATION",
                        "polarity": "AFFIRMATIVE",
                    }
                ],
                "tokens": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
            ensure_ascii=False,
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
        manual_cand_file,
        "--enable-llm",
        "--llm-cache-dir",
        cache_dir,
    ]
    process, body = invoke(*args)
    assert process.returncode == 0, process.stderr
    assert body["claims"] == 2

    record = json.loads((out / "policy.capture.json").read_bytes())
    claim = record["claims"][0]
    assert record["claims"][1]["polarity"] == "AFFIRMATIVE"
    # Manual candidate's attributes must be preserved over LLM's
    assert claim["data_type"] == "LOCATION"
    assert claim["polarity"] == "NEGATIVE"
    assert claim["condition"] == "严格限制"
    conflicts = body["llm_extraction"]["conflicting_candidates"]
    assert len(conflicts) == 1
    assert conflicts[0]["existing_polarity"] == "NEGATIVE"
    assert conflicts[0]["llm_polarity"] == "AFFIRMATIVE"
    assert conflicts[0]["requires_human_review"] is True

    audits = json.loads((out / "policy.audits.json").read_bytes())
    assert len(audits) == 2
    assert audits[0]["actor"] == "Codex-assisted candidate"
    assert "conflicting LLM candidate requires human review" in audits[0]["reason"]
    assert audits[1]["actor"].startswith("LLM-assisted candidate")




def test_cli_does_not_accept_api_key_argument(tmp_path):
    secret = "CLI-SECRET-DO-NOT-LOG"
    raw = tmp_path / "policy.txt"
    raw.write_text("我们收集位置。", encoding="utf-8")
    args = [sys.executable, "-m", "privacytrace.policy_intake",
            "--raw", str(raw), "--source-url", "https://example.org/p",
            "--version", "1", "--output-dir", str(tmp_path / "out"),
            "--enable-llm", "--llm-api-key", secret]
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode != 0
    assert secret not in result.stdout
    assert secret not in result.stderr
    assert not (tmp_path / "out").exists()


def test_cli_rejects_forged_candidate_audit_identity(tmp_path):
    raw = tmp_path / "policy.txt"
    raw.write_text("我们收集位置。", encoding="utf-8")
    candidates = tmp_path / "candidates.json"
    candidates.write_text(json.dumps([{
        "excerpt": "位置", "data_type": "LOCATION",
        "actor": "Human Reviewer", "reason": "Manually verified"
    }]), encoding="utf-8")
    out = tmp_path / "out"
    result, body = invoke("--raw", raw, "--source-url", "https://example.org/p",
                          "--version", "1", "--output-dir", out,
                          "--candidates", candidates)
    assert result.returncode == 1
    assert body["errors"][0]["code"] == "POLICY_INPUT_INVALID"
    assert not out.exists()


def test_preflight_invalid_destination_makes_no_llm_calls(tmp_path):
    from privacytrace.policy_intake import capture
    from privacytrace.policy_llm_extractor import (
        LLMExtractorConfig,
        MockLLMClient,
        PolicyLLMExtractor,
    )
    raw = tmp_path / "policy.txt"
    raw.write_text("我们收集位置。", encoding="utf-8")
    output = tmp_path / "existing"
    output.mkdir()
    mock = MockLLMClient()
    extractor = PolicyLLMExtractor(LLMExtractorConfig(enabled=True, client=mock))
    with pytest.raises(ValueError, match="already exists"):
        capture(raw, "https://example.org/p", "1", output, llm_extractor=extractor)
    assert mock.call_count == 0


def test_cli_budget_exhaustion_outputs_skipped_offsets(tmp_path):
    from privacytrace.policy_llm_extractor import (
        ACTIVE_RULESET_VERSION,
        PROMPT_VERSION,
        compute_cache_key,
    )
    text = "我们访问位置。第二句。第三句。"
    raw = tmp_path / "policy.txt"
    raw.write_text(text, encoding="utf-8")
    cache = tmp_path / "cache"
    cache.mkdir()
    first_span = "我们访问位置。"
    key = compute_cache_key("gpt-4o-mini", PROMPT_VERSION, ACTIVE_RULESET_VERSION, first_span)
    (cache / f"{CACHE_FILE_PREFIX}{key}.json").write_text(json.dumps({
        "raw_items": [{"excerpt": "位置", "data_type": "LOCATION"}], "tokens": {}
    }), encoding="utf-8")
    output = tmp_path / "out"
    process, body = invoke("--raw", raw, "--source-url", "https://example.org/p",
                           "--version", "1", "--output-dir", output,
                           "--enable-llm", "--llm-cache-dir", cache,
                           "--llm-max-spans", 1)
    assert process.returncode == 0, process.stderr
    assert body["llm_extraction"]["status"] == "PARTIAL"
    assert body["llm_extraction"]["skipped_spans"] == 2
    skipped = body["llm_extraction"]["skipped_span_details"]
    assert skipped[0]["start"] == len(first_span)
    assert skipped[0]["reason"] == "SPAN_BUDGET_EXHAUSTED"
    assert body["claims"] == 1
    assert json.loads((output / "policy.capture.json").read_text(encoding="utf-8"))[
        "document"
    ]["review_status"] == "UNREVIEWED"
