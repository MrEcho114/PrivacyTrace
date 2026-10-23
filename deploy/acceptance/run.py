"""One entry point for the R2/R4/R5/R6 acceptance collectors.

Usage::

    uv run --project apps/api --locked --extra worker \\
        python deploy/acceptance/run.py --only r2,r4,r5,r6 --receipt-dir tmp/acceptance

Without a topology the required deployment checks remain incomplete and exit 2.
A FAIL exits 1; only complete required evidence permits exit 0.

The module is also importable: :func:`main` takes an argument list and returns an
exit code, which keeps the unit tests free of subprocess use.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

if __package__ in {None, ""}:  # `python deploy/acceptance/run.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "deploy.acceptance"

from deploy.acceptance.receipt import (  # noqa: E402
    CheckRecorder,
    Receipt,
    collect_environment,
    is_evidence_free,
    read_source_sha,
    render_summary,
    summarize,
    utc_now,
)
from deploy.acceptance.redaction import redact_text  # noqa: E402
from deploy.acceptance.topology import (  # noqa: E402
    ENVIRONMENT_VARIABLES,
    Topology,
    docker_versions,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECEIPT_DIR = ROOT / "tmp/acceptance"
COLLECTORS = ("r1", "r2", "r3", "r4", "r5", "r6")


def _load(module: str) -> Callable[[], Receipt]:
    if module == "r1":
        from deploy.acceptance import r1_deployment as collector
    elif module == "r2":
        from deploy.acceptance import r2_business_loop as collector
    elif module == "r3":
        from deploy.acceptance import r3_isolation as collector
    elif module == "r4":
        from deploy.acceptance import r4_fault_recovery as collector
    elif module == "r5":
        from deploy.acceptance import r5_backup_recovery as collector
    elif module == "r6":
        from deploy.acceptance import r6_capacity_audit as collector
    else:  # pragma: no cover - argparse restricts the choice
        raise ValueError(module)
    return collector.run


def parse_only(values: Sequence[str]) -> list[str]:
    """Accept ``--only r2,r4`` and repeated ``--only r2 --only r4``."""
    tokens: list[str] = []
    for value in values:
        tokens.extend(part.strip().lower() for part in value.split(","))
    selected = []
    for token in tokens:
        if not token:
            continue
        if token not in COLLECTORS:
            raise ValueError(f"unknown collector {token!r}; choose from {', '.join(COLLECTORS)}")
        if token not in selected:
            selected.append(token)
    if not selected:
        raise ValueError("no collector selected")
    return selected


def _collect_one(module: str) -> Receipt:
    """Run one collector; an internal error becomes a FAIL check, not a crash."""
    collector = _load(module)
    try:
        receipt = collector()
    except Exception as error:  # noqa: BLE001 - a harness must never hide a crash
        receipt = Receipt(scope=f"{module}-collector-error", source_sha=read_source_sha(ROOT))
        recorder = CheckRecorder(
            f"{module}.collector_crash",
            f"deploy/acceptance {module} collector",
            ticket=module.upper(),
        )
        receipt.checks.append(
            recorder.fail(
                f"{type(error).__name__} while collecting",
                traceback=redact_text(traceback.format_exc()[-2000:]),
            )
        )
        receipt.finished_at = utc_now()
    from .r2_business_loop import cleanup_created_scopes

    failures = cleanup_created_scopes()
    if failures:
        recorder = CheckRecorder(
            f"{module}.cleanup",
            "DELETE only scopes created by this collector",
            ticket=module.upper(),
        )
        receipt.checks.append(recorder.fail("test scope cleanup failed", statuses=failures))
    return receipt


def combine(receipts: Sequence[Receipt]) -> dict:
    """Aggregate every check of every collector into one verdict."""
    checks = [check for receipt in receipts for check in receipt.checks]
    summary = summarize(checks)
    untested = [scope for receipt in receipts for scope in receipt.untested]
    summary["untested_scopes"] = len(untested)
    summary["evidence_free"] = is_evidence_free(summary)
    waivers = {
        item["id"]: item for receipt in receipts for item in receipt.environment.get("waivers", [])
    }
    summary["waivers"] = list(waivers.values())
    if summary["conclusion"] == "ALL_PASS" and waivers:
        summary["conclusion"] = "ALL_REQUIRED_CHECKS_PASS_WITH_WAIVER"
    # An explicit boolean so a reader of the raw JSON cannot mistake an
    # all-SKIP round for a green run.
    summary["no_pass_claimed"] = summary["pass"] == 0
    return summary


def write_receipts(
    receipts: Sequence[Receipt], directory: Path, *, scope: str = "issue81-r1-r6"
) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    written: list[Path] = []
    for receipt in receipts:
        name = f"acceptance-{receipt.scope}-{stamp}.json"
        written.append(receipt.write(directory / name))
    combined = {
        "receipt_version": 1,
        "scope": scope,
        "source_sha": receipts[0].source_sha if receipts else "UNKNOWN",
        "generated_at": utc_now(),
        "summary": combine(receipts),
        "receipts": [path.name for path in written],
        "untested": [scope for receipt in receipts for scope in receipt.untested],
    }
    redacted = redact_text(json.dumps(combined, indent=2, sort_keys=True))
    combined_path = directory / f"acceptance-summary-{stamp}.json"
    combined_path.write_text(redacted + "\n", encoding="utf-8")
    written.append(combined_path)
    return written


def _environment_block() -> dict:
    topology = Topology.from_env()
    tools = docker_versions(topology)
    tools["topology_base_url"] = topology.base_url or "UNSET"
    return collect_environment(
        ROOT,
        tools=tools,
        extra={
            "topology_configured": topology.configured,
            "allow_writes": topology.allow_writes,
            "allow_destructive": topology.allow_destructive,
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deploy/acceptance/run.py",
        description="Collect Issue #81 R2/R4/R5/R6 acceptance evidence with receipts.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="r2,r4,r5,r6",
        help="collectors to run (comma separated or repeated); default: all six",
    )
    parser.add_argument(
        "--receipt-dir",
        type=Path,
        default=None,
        help="directory for the JSON receipts (default tmp/acceptance)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="deployment env file; only non-secret values are read",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="print the required environment variables and exit",
    )
    parser.add_argument(
        "--no-write", action="store_true", help="print the summary without writing receipts"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list_checks:
        for key, description in ENVIRONMENT_VARIABLES.items():
            print(f"{key:38s} {description}")
        return 0

    try:
        selected = parse_only(args.only or list(COLLECTORS))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.env_file:
        os.environ["PT_ACCEPTANCE_ENV_FILE"] = str(args.env_file.resolve())
    receipt_dir = args.receipt_dir or Path(
        os.environ.get("PT_ACCEPTANCE_RECEIPT_DIR") or DEFAULT_RECEIPT_DIR
    )

    environment = _environment_block()
    receipts = [_collect_one(module) for module in selected]
    for receipt in receipts:
        receipt.environment = {
            **environment,
            **{key: value for key, value in receipt.environment.items() if key not in environment},
        }

    # The receipt-level redaction audit reads what the collectors produced, so it
    # runs after every collector. It is R6 evidence, so it only joins a round that
    # asked for R6; otherwise a purely-skipped R2 round would show one PASS and
    # look like a green run.
    if "r6" in selected:
        from deploy.acceptance.r6_capacity_audit import receipt_redaction_check

        audit = receipt_redaction_check([receipt.to_json() for receipt in receipts])
        audit.ticket = "R6"
        receipts[selected.index("r6")].checks.append(audit)

    summary = combine(receipts)
    # The single round keeps its historical label. A split round (the same checks
    # run as r1-r4 and r5-r6 jobs) must not claim evidence it did not collect.
    round_scope = (
        "issue81-r1-r6" if selected == list(COLLECTORS) else "issue81-" + "-".join(selected)
    )
    written = [] if args.no_write else write_receipts(receipts, receipt_dir, scope=round_scope)

    print("=" * 72)
    print(render_summary(summary, scope=",".join(selected), source_sha=receipts[0].source_sha))
    for waiver in summary.get("waivers", []):
        print(f"WAIVED_BY_USER: {waiver['scope']} ({waiver['authorization']})")
    print("=" * 72)
    for receipt in receipts:
        print(f"[{receipt.scope}]")
        print(render_summary(receipt.summary(), scope=receipt.scope, source_sha=receipt.source_sha))
        print("-" * 72)
    untested = [scope for receipt in receipts for scope in receipt.untested]
    if untested:
        print("UNTESTED SCOPES (this round):")
        for scope in dict.fromkeys(untested):
            print(f"  - {scope}")
        print("-" * 72)
    if is_evidence_free(summary):
        print("NO_REAL_EVIDENCE: no PASS/FAIL this round (all checks SKIP/NOT_TESTED).")
    if written:
        print("receipts:")
        for path in written:
            print(f"  {path}")
    # Incomplete evidence must not turn a deployment gate green.
    if summary.get("fail"):
        return 1
    return 2 if summary.get("skip") or summary.get("not_tested") or untested else 0


if __name__ == "__main__":
    raise SystemExit(main())
