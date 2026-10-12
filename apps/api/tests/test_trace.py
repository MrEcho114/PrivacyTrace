import importlib.util
import json

import pytest

from privacytrace.resources import ROOT

spec = importlib.util.spec_from_file_location(
    "validate_trace", ROOT / "scripts/validate-trace.py"
)
trace_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace_mod)


def write_trace(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def valid_line():
    return {
        "ts": "2026-10-10T01:00:00Z",
        "sample_id": "app-1",
        "job_id": "job-1",
        "stage": "dex",
        "event": "evidence",
        "status": "ok",
        "evidence_ref": "ev-1",
    }


def test_validate_accepts_valid_line(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_trace(path, [json.dumps(valid_line())])
    assert trace_mod.validate(trace_mod.load_lines(path)) == [valid_line()]


def test_validate_rejects_missing_field(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_trace(path, [json.dumps({"ts": "2026-10-10T01:00:00Z"})])
    with pytest.raises(ValueError, match="missing fields"):
        trace_mod.validate(trace_mod.load_lines(path))


def test_validate_rejects_unknown_status(tmp_path):
    line = valid_line()
    line["status"] = "weird"
    with pytest.raises(ValueError, match="unknown status"):
        trace_mod.validate([line])


def test_validate_rejects_timestamp_without_timezone(tmp_path):
    line = valid_line()
    line["ts"] = "2026-10-10T01:00:00"
    with pytest.raises(ValueError, match="timezone"):
        trace_mod.validate([line])


def test_validate_rejects_invalid_json_line(tmp_path):
    path = tmp_path / "trace.jsonl"
    write_trace(path, ["not json"])
    with pytest.raises(ValueError, match="not valid JSON"):
        trace_mod.load_lines(path)
