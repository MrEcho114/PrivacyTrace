#!/usr/bin/env python3
"""TheMasterplan deterministic executor.

``themasterplan.py`` is the canonical executor entry; ``.themasterplan/`` is the
adoption state directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tmlib import TheMasterplanError
from tmlib.apply import apply_adopt
from tmlib.doctor import doctor
from tmlib.inspect import inspect
from tmlib.planning import plan_adopt
from tmlib.source import resolve_source
from tmlib.update import apply_update, plan_update
from tmlib.update_check import (
    REPOSITORY_RE,
    UpdateCheckError,
    check_update,
)
from tmlib.util import read_json, write_json_atomic
from tmlib.verify import verify


def _cache_dir(root: Path) -> Path:
    return root / ".themasterplan/cache"


def _resolve(args: argparse.Namespace, root: Path):
    return resolve_source(
        args.source,
        _cache_dir(root),
        commit=args.commit,
        expected_repository=args.repository or None,
    )


def _cmd_inspect(args: argparse.Namespace) -> int:
    result = inspect(Path(args.root), target_version=args.target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in (
        "CURRENT",
        "ABSENT",
        "INCOMPLETE",
        "OUTDATED",
    ) else 1


def _cmd_plan_adopt(args: argparse.Namespace) -> int:
    root = Path(args.root)
    source = _resolve(args, root)
    plan = plan_adopt(
        root,
        source,
        profile=args.profile,
        validation_path=args.validation_path,
        default_branch=args.default_branch,
        validation_path_exists=args.validation_path_exists,
    )
    write_json_atomic(Path(args.output), plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def _cmd_apply_adopt(args: argparse.Namespace) -> int:
    root = Path(args.root)
    result = apply_adopt(
        root,
        Path(args.plan),
        _resolve(args, root),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_plan_update(args: argparse.Namespace) -> int:
    root = Path(args.root)
    source = _resolve(args, root)
    state = read_json(root / ".themasterplan/state.json")
    plan = plan_update(root, source, state)
    write_json_atomic(Path(args.output), plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def _cmd_apply_update(args: argparse.Namespace) -> int:
    root = Path(args.root)
    result = apply_update(
        root,
        Path(args.plan),
        _resolve(args, root),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    result = verify(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    result = doctor(Path(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def _cmd_check_update(args: argparse.Namespace) -> int:
    if (
        args.repository is not None
        and REPOSITORY_RE.fullmatch(args.repository) is None
    ):
        print(
            "themasterplan: error: --repository must be owner/repo",
            file=sys.stderr,
        )
        return 2
    try:
        result = check_update(
            Path(args.root),
            repository=args.repository,
            include_prerelease=args.include_prerelease,
            use_cache=not args.no_cache,
        )
    except UpdateCheckError as exc:
        print(f"themasterplan: error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "UNAVAILABLE":
        return 3
    return 0


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        required=True,
        help="local path, release tag, or full commit SHA",
    )
    parser.add_argument(
        "--commit",
        default=None,
        help="expected full SHA; tag values are verified against GitHub",
    )
    parser.add_argument(
        "--repository",
        default=None,
        help="expected owner/repo; defaults to OasisSaber/TheMasterplan",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="themasterplan.py",
        description=__doc__,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser("inspect")
    inspect_parser.add_argument("--root", default=".")
    inspect_parser.add_argument("--target", default=None)
    inspect_parser.set_defaults(func=_cmd_inspect)

    plan_adopt_parser = commands.add_parser("plan-adopt")
    plan_adopt_parser.add_argument("--root", default=".")
    _add_source_args(plan_adopt_parser)
    plan_adopt_parser.add_argument(
        "--profile",
        required=True,
        choices=["git", "jj"],
    )
    plan_adopt_parser.add_argument("--validation-path", required=True)
    plan_adopt_parser.add_argument("--default-branch", default="main")
    plan_adopt_parser.add_argument(
        "--validation-path-exists",
        action="store_true",
    )
    plan_adopt_parser.add_argument("--output", required=True)
    plan_adopt_parser.set_defaults(func=_cmd_plan_adopt)

    apply_adopt_parser = commands.add_parser("apply-adopt")
    apply_adopt_parser.add_argument("--root", default=".")
    apply_adopt_parser.add_argument("--plan", required=True)
    _add_source_args(apply_adopt_parser)
    apply_adopt_parser.set_defaults(func=_cmd_apply_adopt)

    plan_update_parser = commands.add_parser("plan-update")
    plan_update_parser.add_argument("--root", default=".")
    _add_source_args(plan_update_parser)
    plan_update_parser.add_argument("--output", required=True)
    plan_update_parser.set_defaults(func=_cmd_plan_update)

    apply_update_parser = commands.add_parser("apply-update")
    apply_update_parser.add_argument("--root", default=".")
    apply_update_parser.add_argument("--plan", required=True)
    _add_source_args(apply_update_parser)
    apply_update_parser.set_defaults(func=_cmd_apply_update)

    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--root", default=".")
    verify_parser.set_defaults(func=_cmd_verify)

    doctor_parser = commands.add_parser("doctor")
    doctor_parser.add_argument("--root", default=".")
    doctor_parser.set_defaults(func=_cmd_doctor)

    check_update_parser = commands.add_parser("check-update")
    check_update_parser.add_argument("--root", default=".")
    check_update_parser.add_argument("--repository", default=None)
    check_update_parser.add_argument(
        "--include-prerelease",
        action="store_true",
    )
    check_update_parser.add_argument(
        "--no-cache",
        action="store_true",
    )
    check_update_parser.add_argument(
        "--json",
        action="store_true",
    )
    check_update_parser.set_defaults(func=_cmd_check_update)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TheMasterplanError as exc:
        print(f"themasterplan: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
