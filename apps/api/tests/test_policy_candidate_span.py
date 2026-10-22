"""A candidate may name only one endpoint; the other follows the excerpt (#230)."""

import json

import pytest

from privacytrace.policy_intake import _candidate_identity, capture, preflight_capture

TEXT = "隐私😀我们不访问联系人。仅在用户授权时访问位置。"
EXCERPT = "仅在用户授权时访问位置。"
START = TEXT.index(EXCERPT)
END = START + len(EXCERPT)


def raw_file(tmp_path):
    raw = tmp_path / "raw.txt"
    raw.write_text(TEXT, encoding="utf-8")
    return raw


def test_preflight_accepts_a_single_endpoint(tmp_path):
    raw = raw_file(tmp_path)
    start_only = {"data_type": "LOCATION", "excerpt": EXCERPT, "start_offset": START}
    end_only = {"data_type": "LOCATION", "excerpt": EXCERPT, "end_offset": END}
    for candidate in (start_only, end_only):
        preflight_capture(raw, "https://example.org/p", tmp_path / "out", [candidate])
        assert not (tmp_path / "out").exists()


def test_capture_derives_the_missing_end_from_the_excerpt(tmp_path):
    raw = raw_file(tmp_path)
    out = tmp_path / "capture"
    capture(raw, "https://example.org/p", "1", out, [
        {"data_type": "LOCATION", "excerpt": EXCERPT, "start_offset": START},
    ])
    record = json.loads((out / "policy.capture.json").read_bytes())
    sentence = record["evidence"][1]
    assert (sentence["start_offset"], sentence["end_offset"]) == (START, END)
    assert sentence["excerpt"] == EXCERPT
    assert record["claims"][0]["evidence_ids"] == [sentence["id"]]


def test_candidate_identity_matches_the_full_span_shape():
    start_only = {"data_type": "LOCATION", "excerpt": EXCERPT, "start_offset": START}
    explicit = {**start_only, "end_offset": END}
    assert _candidate_identity(start_only, TEXT) == _candidate_identity(explicit, TEXT)
    assert _candidate_identity(start_only, TEXT)[0] == (START, END, "LOCATION")


def test_excerpt_must_match_the_derived_span(tmp_path):
    raw = raw_file(tmp_path)
    with pytest.raises(ValueError, match="does not match span"):
        preflight_capture(raw, "https://example.org/p", tmp_path / "out", [
            {"data_type": "LOCATION", "excerpt": "不存在的句子", "start_offset": START},
        ])


def test_single_endpoint_without_an_excerpt_is_rejected():
    with pytest.raises(ValueError, match="requires an excerpt"):
        _candidate_identity({"data_type": "LOCATION", "start_offset": START}, TEXT)


@pytest.mark.parametrize("offset", [True, "3", 3.0])
def test_non_integer_offsets_are_still_rejected(offset):
    candidate = {"data_type": "LOCATION", "excerpt": EXCERPT, "start_offset": offset}
    with pytest.raises(ValueError, match="Invalid candidate codepoint span"):
        _candidate_identity(candidate, TEXT)


def test_neither_endpoint_still_requires_a_unique_excerpt():
    with pytest.raises(ValueError, match="occur exactly once"):
        _candidate_identity({"data_type": "LOCATION", "excerpt": "访问"}, TEXT)
