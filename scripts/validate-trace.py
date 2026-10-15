"""Validate PrivacyTrace #23 trace logs (one JSON object per line).

Required fields: ``ts``, ``sample_id``, ``job_id``, ``stage``, ``event``,
``status``. Field meanings and allowed values are documented in
``evidence/trace.schema.md``.

The contract covers the fields the dataset builder depends on, so a line cannot
pass validation and then be dropped silently while building: ``event`` must be a
known event type, ``evidence_ref`` is required on ``event=evidence`` lines and
rejected on every other event, and optional text fields must be non-empty when
present.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

REQUIRED = {"ts", "sample_id", "job_id", "stage", "event", "status"}
STATUSES = {"ok", "partial", "failed", "skipped"}
EVENTS = {"start", "evidence", "conclusion", "error", "done"}
OPTIONAL_STRINGS = ("evidence_ref", "data_type", "location", "detail")


def load_lines(path: Path) -> list[dict]:
    lines = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{number} is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise TypeError(f"{path.name}:{number} must be a JSON object")
        lines.append(parsed)
    return lines


def validate(lines: list[dict]) -> list[dict]:
    for index, line in enumerate(lines, start=1):
        missing = sorted(REQUIRED - set(line))
        if missing:
            raise ValueError(f"line {index} missing fields: {missing}")
        for field in REQUIRED:
            if not isinstance(line[field], str) or not line[field].strip():
                raise ValueError(f"line {index}: {field} must be non-empty string")
        if line["status"] not in STATUSES:
            raise ValueError(f"line {index}: unknown status {line['status']!r}")
        if line["event"] not in EVENTS:
            raise ValueError(
                f"line {index}: unknown event {line['event']!r}; "
                f"expected one of {sorted(EVENTS)}"
            )
        for field in OPTIONAL_STRINGS:
            if field in line and (
                not isinstance(line[field], str) or not line[field].strip()
            ):
                raise ValueError(f"line {index}: {field} must be non-empty string")
        if line["event"] == "evidence" and "evidence_ref" not in line:
            raise ValueError(f"line {index}: event=evidence requires evidence_ref")
        if line["event"] != "evidence" and "evidence_ref" in line:
            raise ValueError(
                f"line {index}: evidence_ref is only allowed on event=evidence"
            )
        try:
            parsed_ts = datetime.fromisoformat(line["ts"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"line {index}: ts is not ISO-8601") from exc
        if parsed_ts.tzinfo is None:
            raise ValueError(f"line {index}: ts must include timezone")
        duration = line.get("duration_ms")
        if duration is not None and (
            not isinstance(duration, int) or duration < 0
        ):
            raise ValueError(f"line {index}: duration_ms must be non-negative int")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="trace JSONL file")
    args = parser.parse_args()
    lines = validate(load_lines(args.input))
    print(json.dumps({"valid_lines": len(lines)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
