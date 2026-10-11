"""PR #42 round-three red/green regression tests (R3-01 through R3-06)."""

import hashlib
import http.server
import json
import sys
import threading

import pytest

from privacytrace.policy_intake import build_llm_execution, capture, load_policy, split_spans
from privacytrace.policy_llm_extractor import (
    LLMExtractorConfig,
    MockLLMClient,
    PolicyLLMExtractor,
    UrllibLLMClient,
)


def test_r3_01_programmatic_endpoint_env_and_explicit_precedence(monkeypatch):
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(self.path)
            self.rfile.read(int(self.headers["Content-Length"]))
            body = {"choices": [{"message": {"content": "[]"}}], "usage": {}}
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        monkeypatch.setenv("PRIVACYTRACE_LLM_API_BASE", base)
        config = LLMExtractorConfig(enabled=True, max_retries=1)
        assert config.api_base == base
        assert UrllibLLMClient().api_base == base
        result = PolicyLLMExtractor(config).extract_from_chunk("测试。")
        assert result.status == "SUCCESS"
        assert received == ["/v1/chat/completions"]
        audit = build_llm_execution(result, config, "测试。".encode(), [])
        assert audit["endpoint_identifier"] == hashlib.sha256(base.encode()).hexdigest()

        explicit = LLMExtractorConfig(api_base="https://explicit.example/v1")
        assert explicit.api_base == "https://explicit.example/v1"
        monkeypatch.delenv("PRIVACYTRACE_LLM_API_BASE")
        assert LLMExtractorConfig().api_base == "https://api.openai.com/v1"
        assert PolicyLLMExtractor(LLMExtractorConfig()).extract_from_chunk("测试。").status == (
            "DISABLED"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("data_type", ["NONEXISTENT_TYPE", None, 123])
def test_r3_02_invalid_manual_taxonomy_before_any_model_call(tmp_path, data_type):
    raw = tmp_path / "raw.txt"
    raw.write_text("我们使用位置。", encoding="utf-8")
    candidate = {"excerpt": "位置"}
    if data_type is not None:
        candidate["data_type"] = data_type
    mock = MockLLMClient()
    extractor = PolicyLLMExtractor(LLMExtractorConfig(enabled=True, client=mock))
    target = tmp_path / "published"
    with pytest.raises(ValueError):
        capture(
            raw, "https://example.org/privacy", "1", target,
            candidates=[candidate], llm_extractor=extractor,
        )
    assert mock.call_count == 0
    assert not target.exists()


def test_r3_02_valid_manual_taxonomy_still_succeeds(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_text("我们使用位置。", encoding="utf-8")
    mock = MockLLMClient()
    extractor = PolicyLLMExtractor(LLMExtractorConfig(enabled=True, client=mock))
    path = capture(
        raw, "https://example.org/privacy", "1", tmp_path / "out",
        candidates=[{"excerpt": "位置", "data_type": "LOCATION"}],
        llm_extractor=extractor,
    )
    assert len(load_policy(path)["claims"]) == 1
    assert mock.call_count == 1


def test_r3_03_untrusted_exception_never_enters_telemetry_or_cli(
    tmp_path, monkeypatch, capsys,
):
    secret = "SENSITIVE_POLICY_TEXT super-secret-key"

    def fail(*_args):
        raise RuntimeError(secret)

    mock = MockLLMClient(fail)
    result = PolicyLLMExtractor(
        LLMExtractorConfig(enabled=True, client=mock, max_retries=1)
    ).extract_from_chunk("我们访问位置。")
    assert result.status == "FAILED"
    assert result.telemetry.errors
    assert secret not in json.dumps(result.telemetry.__dict__)
    assert all("LLM_" in error or "BUDGET_" in error for error in result.telemetry.errors)

    from privacytrace import policy_intake

    monkeypatch.setattr(UrllibLLMClient, "call", fail)
    raw = tmp_path / "raw.txt"
    raw.write_text("我们访问位置。", encoding="utf-8")
    dest = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv",
        ["policy_intake", "--raw", str(raw), "--source-url",
         "https://example.org/p", "--version", "1", "--output-dir", str(dest),
         "--enable-llm", "--llm-max-requests", "1"],
    )
    assert policy_intake.main() == 0
    stdio = capsys.readouterr()
    audit = (dest / "policy.llm-execution.json").read_text(encoding="utf-8")
    assert secret not in stdio.out + stdio.err + audit
    assert json.loads(audit)["failed_spans"][0]["code"] == "LLM_REQUEST_FAILED"


def test_r3_04_cache_replay_cannot_bypass_response_limit_or_output_token_identity(tmp_path):
    text = "我们访问位置。"
    entries = [{"excerpt": "位置", "data_type": "LOCATION"}] * 3
    warm = MockLLMClient(lambda *_args: json.dumps(entries))
    cfg = LLMExtractorConfig(
        enabled=True, client=warm, cache_dir=tmp_path, max_retries=1,
        max_candidates_per_response=3, max_output_tokens=2048,
    )
    assert PolicyLLMExtractor(cfg).extract_from_chunk(text).status == "SUCCESS"
    assert warm.call_count == 1

    cached = PolicyLLMExtractor(cfg).extract_from_chunk(text)
    assert cached.telemetry.cached is True
    assert warm.call_count == 1

    small = MockLLMClient(lambda *_args: json.dumps(entries))
    constrained = PolicyLLMExtractor(LLMExtractorConfig(
        enabled=True, client=small, cache_dir=tmp_path, max_retries=1,
        max_candidates_per_response=1, max_output_tokens=2048,
    )).extract_from_chunk(text)
    assert not (constrained.status == "SUCCESS" and len(constrained.candidates) > 1)

    other = MockLLMClient(lambda *_args: "[]")
    changed = PolicyLLMExtractor(LLMExtractorConfig(
        enabled=True, client=other, cache_dir=tmp_path, max_retries=1,
        max_candidates_per_response=3, max_output_tokens=1024,
    )).extract_from_chunk(text)
    assert changed.telemetry.cached is False
    assert other.call_count == 1


def test_r3_05_duplicate_manual_candidate_does_not_consume_last_slot(tmp_path):
    text = "独特" + "位" * 1997 + "。新增信息。"
    raw = tmp_path / "raw.txt"
    raw.write_text(text, encoding="utf-8")
    manual = [
        {"excerpt": "独特", "start_offset": 0, "end_offset": 2,
         "data_type": "LOCATION"},
    ]
    manual.extend(
        {"excerpt": "位", "start_offset": index, "end_offset": index + 1,
         "data_type": "LOCATION"}
        for index in range(2, 1999)
    )
    assert len(manual) == 1998

    def handler(_system, user):
        excerpt = "新增信息" if "新增信息" in user else "独特"
        return json.dumps([{"excerpt": excerpt, "data_type": "LOCATION"}],
                          ensure_ascii=False)

    mock = MockLLMClient(handler)
    extractor = PolicyLLMExtractor(LLMExtractorConfig(
        enabled=True, client=mock, max_spans=3,
    ))
    target = tmp_path / "out"
    record = load_policy(capture(
        raw, "https://example.org/p", "1", target,
        candidates=manual, llm_extractor=extractor,
    ))
    assert len(record["claims"]) == 1999
    assert mock.call_count == 2
    assert record["claims"][-1]["data_type"] == "LOCATION"
    assert (target / "policy.audits.json").is_file()
    assert json.loads((target / "policy.llm-execution.json").read_text())[
        "status"
    ] == "SUCCESS"


def test_r3_05_llm_duplicates_with_existing_semantics_do_not_use_quota():
    text = "我们访问位置。我们访问通讯录。"
    manual = [{"excerpt": "位置", "start_offset": 4, "end_offset": 6,
               "data_type": "LOCATION"}]

    def handler(_system, user):
        if "通讯录" in user:
            return json.dumps([{"excerpt": "通讯录", "data_type": "CONTACTS"}],
                              ensure_ascii=False)
        return json.dumps(
            [{"excerpt": "位置", "data_type": "LOCATION"}] * 2,
            ensure_ascii=False,
        )

    mock = MockLLMClient(handler)
    result = PolicyLLMExtractor(LLMExtractorConfig(
        enabled=True, client=mock,
    )).extract_from_spans(
        text, split_spans(text), max_candidate_budget=1, existing_candidates=manual,
    )
    assert result.status == "SUCCESS"
    assert len(result.candidates) == 1
    assert result.candidates[0]["data_type"] == "CONTACTS"
    assert mock.call_count == 2


@pytest.mark.parametrize("field,value", [
    ("max_elapsed_seconds", float("inf")),
    ("max_elapsed_seconds", float("nan")),
    ("max_elapsed_seconds", float("-inf")),
    ("timeout_seconds", float("inf")),
    ("timeout_seconds", float("nan")),
    ("temperature", float("inf")),
    ("temperature", float("nan")),
    ("max_elapsed_seconds", "not-a-number"),
])
def test_r3_06_reject_nonfinite_or_nonnumeric_config(field, value):
    with pytest.raises(ValueError):
        LLMExtractorConfig(**{field: value})


@pytest.mark.parametrize("value", ["inf", "nan"])
def test_r3_06_cli_rejects_nonfinite_budget_without_output(tmp_path, monkeypatch, value):
    from privacytrace import policy_intake

    raw = tmp_path / "raw.txt"
    raw.write_text("测试。", encoding="utf-8")
    target = tmp_path / "out"
    monkeypatch.setattr(
        sys, "argv",
        ["policy_intake", "--raw", str(raw), "--source-url",
         "https://example.org/p", "--version", "1", "--output-dir", str(target),
         "--enable-llm", "--llm-max-elapsed-seconds", value],
    )
    assert policy_intake.main() == 1
    assert not target.exists()
