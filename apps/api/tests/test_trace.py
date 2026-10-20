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


def test_validate_rejects_unknown_event():
    line = valid_line()
    line["event"] = "wired"
    with pytest.raises(ValueError, match="unknown event"):
        trace_mod.validate([line])


def test_validate_requires_evidence_ref_on_evidence_event():
    line = valid_line()
    del line["evidence_ref"]
    with pytest.raises(ValueError, match="requires evidence_ref"):
        trace_mod.validate([line])


def test_validate_rejects_evidence_ref_on_non_evidence_event():
    line = valid_line()
    line["event"] = "conclusion"
    with pytest.raises(ValueError, match="only allowed on event=evidence"):
        trace_mod.validate([line])


def test_validate_rejects_empty_optional_string():
    line = valid_line()
    line["location"] = "   "
    with pytest.raises(ValueError, match="location must be non-empty"):
        trace_mod.validate([line])


@pytest.mark.parametrize("event", ["start", "error", "done"])
def test_validate_accepts_lifecycle_events(event):
    line = valid_line()
    del line["evidence_ref"]
    line["event"] = event
    assert trace_mod.validate([line]) == [line]


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


@pytest.mark.parametrize("raw", ["[]", '"scalar"', "42", "null"])
def test_rejects_non_object_json(tmp_path, raw):
    path = tmp_path / "trace.jsonl"
    write_trace(path, [raw])
    with pytest.raises(ValueError, match="must be a JSON object"):
        trace_mod.load_lines(path)


def test_cli_non_object_error_is_code_2(tmp_path, monkeypatch, capsys):
    import sys

    path = tmp_path / "trace.jsonl"
    write_trace(path, ["[]"])
    monkeypatch.setattr(sys, "argv", ["validate-trace.py", str(path)])
    with pytest.raises(SystemExit) as excinfo:
        trace_mod.main()
    assert excinfo.value.code == 2
    assert "error: trace.jsonl:1 must be a JSON object" in capsys.readouterr().err
