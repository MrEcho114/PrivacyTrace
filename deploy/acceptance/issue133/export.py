"""Export only lane E's sanitized observations; never infer case PASSED."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

SOURCES = {
    "baseline": ["baseline-report-observed.json", "d1-report-after-fixed.json"],
    "n12": [
        "client-restore-after-reclaim.log",
        "n12-restore-complete.log",
        "n12-offline-refresh.log",
        "n12-offline-cancel.log",
        "n12-offline-retry.log",
        "n12-retry-scope.json",
        "n12-old-report-after-retry.json",
        "n12-fixed-reclaim.log",
        "n12-fixed-restore.log",
        "n12-fixed-force-stop.log",
        "n12-fixed-force-stop-restore.log",
        "n12-fixed-restored.json",
    ],
    "polling-red": ["polling-red-begin.log", "polling-red-watch.log", "polling-red-observe.json"],
    "polling-green": [
        "polling-green-begin.log",
        "polling-green-watch.log",
        "polling-green-cancel.log",
        "polling-green-cancel-observe.json",
    ],
    "f05-queued": ["f05-queued-cancel.log", "f05-queued-cancel-observe.json"],
    "f05-scanning": [
        "f05-scan-active.json",
        "f05-scan-cancel.log",
        "f05-scan-after-cancel.json",
        "f05-scan-final.json",
    ],
    "f05-precommit-failed": ["f05-precommit-result.json", "f05-precommit-revoked.json"],
    "f05-precommit-fixed": [
        "f05-precommit-fixed/completed-result-before-commit.json",
        "f05-precommit-fixed/client-cancel.log",
        "f05-precommit-fixed/after.json",
        "f05-precommit-fixed/persistent-after-late-consumer.json",
    ],
    "f06-queued": [
        "f06-queued-before.json",
        "f06-queued-delete.log",
        "f06-queued-replay.json",
        "f06-queued-after.json",
    ],
    "f06-scanning": [
        "f06-scan-active.json",
        "f06-scan-delete.log",
        "f06-scan-replay.json",
        "f06-scan-after.json",
    ],
    "f06-precommit-fixed": [
        "f06-precommit-fixed/completed-result-before-commit.json",
        "f06-precommit-fixed/client-delete.log",
        "f06-precommit-fixed/old-access.json",
        "f06-precommit-fixed/persistent-after-late-consumer.json",
    ],
    "upload-40s": [
        "upload-delay.json",
        "f05-upload-active.json",
        "f05-upload-stop.log",
        "f06-upload-restore.log",
        "f06-upload-delete.log",
        "f06-upload-replay.json",
    ],
    "upload-80s": [
        "upload-delay80.json",
        "f06-upload80-active.json",
        "f06-upload80-stop.log",
        "f06-upload80-restore.log",
        "f06-upload80-delete.log",
        "f06-upload80-revoked.json",
        "f06-upload80-replay.json",
        "f06-upload80-after-late.json",
    ],
    "cleanup": ["cleanup.json"],
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def compact(value):
    if isinstance(value, list):
        return [compact(item) for item in value]
    if not isinstance(value, dict):
        return value
    # Inputs must come from the controlled observer, never raw Caddy logs or reports.
    result = {
        key: compact(item)
        for key, item in value.items()
        if key
        not in {
            "requests",
            "request_counts",
            "native_request_counts",
            "visible_scope_ids",
            "evidence",
        }
    }
    if "visible_scope_ids" in value:
        result["visible_job_aliases"] = [
            digest(item.encode())[:12] for item in value["visible_scope_ids"]
        ]
    if "requests" in value:
        # Preserve the final 60s window with actors, route templates and aliases.
        # Full-history request counts remain explicitly labelled as such.
        requests = value["requests"]
        end = max((item["at"] for item in requests), default=0)
        groups = defaultdict(list)
        for item in requests:
            if item["at"] >= end - 60:
                key = (
                    item.get("actor", "UNKNOWN"),
                    item.get("scope_alias"),
                    item["method"],
                    item["route"],
                    item["status"],
                )
                groups[key].append(item["at"])
        result["last_60s_request_groups"] = [
            dict(
                actor=key[0],
                scope_alias=key[1],
                method=key[2],
                route=key[3],
                status=key[4],
                count=len(times),
                first_epoch=min(times),
                last_epoch=max(times),
            )
            for key, times in groups.items()
        ]
        result["request_window_end_epoch"] = end
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    index = []
    for group, names in SOURCES.items():
        records = []
        for name in names:
            raw = (args.private_run / name).read_bytes()
            text = raw.decode("utf-8-sig")
            if name.endswith(".log"):
                value = json.loads(next(line for line in text.splitlines() if line.startswith("{")))
            else:
                value = json.loads(text)
            records.append(
                {
                    "private_locator": name,
                    "private_capture_sha256": digest(raw),
                    "observation": compact(value),
                }
            )
        data = (
            json.dumps(
                {"group": group, "case_passed": False, "records": records},
                ensure_ascii=False,
                indent=2,
            ).encode()
            + b"\n"
        )
        # Fail closed on raw task IDs and capability/header names.
        # Full SHA256s are intentional, so only exact 32-hex strings are rejected.
        if re.search(rb'"[a-f0-9]{32}"|Authorization|Bearer |access_token', data):
            raise ValueError("Private identity detected; preserve private source, fix exporter")
        target = args.output / (group + ".json")
        target.write_bytes(data)
        index.append({"path": target.name, "sha256": digest(data), "group": group})
    for name in sorted((args.private_run / "ui").glob("*-process-*.json")):
        raw = name.read_bytes()
        target = args.output / name.name
        target.write_bytes(raw)
        index.append({"path": target.name, "sha256": digest(raw), "group": "n12-process"})
    (args.output / "index.json").write_text(
        json.dumps(
            {
                "format": "privacytrace-issue133-observations/1",
                "case_passed": False,
                "evidence": index,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"sanitized_files": len(index), "case_passed": False}))


if __name__ == "__main__":
    main()
