"""Apply TheMasterplan adoption plans with immutable source locking."""

from __future__ import annotations

from pathlib import Path

from .source import Source, read_package_file
from .util import (
    TheMasterplanError,
    read_json,
    safe_join,
    sha256_of_block,
    sha256_of_file,
    write_bytes_atomic,
    write_json_atomic,
)

BLOCK_BEGIN = "<!-- THEMASTERPLAN:BEGIN MANAGED -->"
BLOCK_END = "<!-- THEMASTERPLAN:END MANAGED -->"
BLOCK_BEGIN_BYTES = BLOCK_BEGIN.encode("utf-8")
BLOCK_END_BYTES = BLOCK_END.encode("utf-8")
SELF_PREFIX = "<self>:"

EXECUTOR_FILES = (
    "themasterplan.py",
    "tmlib/__init__.py",
    "tmlib/util.py",
    "tmlib/manifest.py",
    "tmlib/source.py",
    "tmlib/inspect.py",
    "tmlib/planning.py",
    "tmlib/apply.py",
    "tmlib/verify.py",
    "tmlib/update.py",
    "tmlib/doctor.py",
    "tmlib/update_check.py",
)


class ApplyError(TheMasterplanError):
    """Raised when a plan cannot be applied safely."""


def _sha256_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _validate_plan(plan: dict) -> None:
    if not isinstance(plan, dict):
        raise ApplyError("plan must be an object")
    if plan.get("schema_version") != 1 or plan.get("plan_type") != "adopt":
        raise ApplyError("unsupported plan: schema_version/plan_type mismatch")
    for key in ("source", "selection", "files"):
        if key not in plan:
            raise ApplyError(f"plan missing key: {key}")
    if plan.get("stop_conditions"):
        raise ApplyError(f"plan has stop conditions: {plan['stop_conditions']}")
    files = plan["files"]
    if not isinstance(files, list) or not files:
        raise ApplyError("plan files must be a non-empty list")

    seen: set[str] = set()
    for operation in files:
        if not isinstance(operation, dict):
            raise ApplyError("plan file entry must be an object")
        for key in ("source", "destination", "ownership", "classification"):
            if key not in operation:
                raise ApplyError(f"plan file entry missing key: {key}")
        source = operation["source"]
        if not isinstance(source, str) or not source:
            raise ApplyError("plan source must be a non-empty string")
        destination = operation["destination"]
        if not isinstance(destination, str) or not destination:
            raise ApplyError("plan destination must be a non-empty string")
        safe_join(Path("."), source)
        safe_join(Path("."), destination)
        if destination in seen:
            raise ApplyError(f"plan has duplicate destination: {destination}")
        seen.add(destination)
        if operation["ownership"] not in (
            "managed-replace",
            "managed-block",
            "generated-if-missing",
            "project-owned",
        ):
            raise ApplyError(
                f"unknown ownership: {operation['ownership']}"
            )
        if operation["classification"] not in (
            "ADD",
            "UNCHANGED",
            "CONFLICT",
            "BLOCK_PRESENT",
            "BLOCK_MISSING",
            "EXISTS_KEEP",
            "PROJECT_OWNED",
        ):
            raise ApplyError(
                f"unknown classification: {operation['classification']}"
            )


def _read_self(relative: str) -> bytes:
    executor_root = Path(__file__).resolve().parent.parent
    return read_package_file(executor_root, relative)


def _read_package_bytes(package_root: Path | None, operation: dict) -> bytes:
    source = operation["source"]
    if source.startswith(SELF_PREFIX):
        content = _read_self(source[len(SELF_PREFIX) :])
    else:
        if package_root is None:
            raise ApplyError(
                f"plan requires package source for "
                f"{operation['destination']}; pass --source"
            )
        content = read_package_file(package_root, source)
    expected = operation.get("source_sha256")
    if expected and _sha256_bytes(content) != expected:
        raise ApplyError(f"source file changed since plan: {source}")
    return content


def _block_bounds_bytes(data: bytes) -> tuple[int, int] | None:
    if data.count(BLOCK_BEGIN_BYTES) != 1 or data.count(BLOCK_END_BYTES) != 1:
        return None
    begin = data.find(BLOCK_BEGIN_BYTES)
    end = data.find(BLOCK_END_BYTES)
    if end < begin:
        return None
    return begin, end + len(BLOCK_END_BYTES)


def _block_bounds(text: str) -> tuple[int, int] | None:
    if text.count(BLOCK_BEGIN) != 1 or text.count(BLOCK_END) != 1:
        return None
    begin = text.index(BLOCK_BEGIN)
    end = text.index(BLOCK_END)
    if end <= begin:
        return None
    return begin, end + len(BLOCK_END)


def _block_content_matches(destination: Path, block_content: bytes) -> bool:
    data = destination.read_bytes()
    bounds = _block_bounds_bytes(data)
    if bounds is None:
        return False
    begin, end = bounds
    content_end = block_content.find(BLOCK_END_BYTES)
    if content_end < 0:
        return False
    expected = block_content[: content_end + len(BLOCK_END_BYTES)]
    return data[begin:end].strip() == expected.strip()


def _current_hash(target: Path, ownership: str) -> str:
    if ownership == "managed-block":
        return sha256_of_block(target)
    return sha256_of_file(target)


def _check_observed(project_root: Path, operation: dict) -> None:
    destination = safe_join(project_root, operation["destination"])
    observed = operation.get("observed_sha256")
    if observed is None:
        raise ApplyError(
            f"plan missing observed hash: {operation['destination']}"
        )
    if (
        not destination.is_file()
        or _current_hash(destination, operation["ownership"]) != observed
    ):
        raise ApplyError(
            f"target changed since plan: {operation['destination']}"
        )


def _render_template(content: bytes, plan: dict) -> bytes:
    text = content.decode("utf-8")
    selection = plan.get("selection", {})
    text = text.replace(
        "{{validation_path}}",
        selection.get("validation_path", "scripts/check.sh"),
    )
    text = text.replace(
        "{{default_branch}}",
        selection.get("default_branch", "main"),
    )
    return text.encode("utf-8")


def _make_minimal_agents(block_content: bytes) -> bytes:
    block = block_content.decode("utf-8")
    return (
        "# TheMasterplan\n\n"
        "> 本文件由 /TheMasterplan 接入生成；规则由 TheMasterplan 管理区块声明。\n\n"
        f"{block}\n"
    ).encode("utf-8")


def _apply_block(
    project_root: Path,
    operation: dict,
    block_content: bytes,
) -> None:
    destination = safe_join(project_root, operation["destination"])
    data = destination.read_bytes()
    bounds = _block_bounds_bytes(data)
    if bounds is None:
        raise ApplyError(
            "managed block markers invalid: "
            f"{operation['destination']}"
        )
    begin, end = bounds
    content_end = block_content.find(BLOCK_END_BYTES)
    if content_end < 0:
        raise ApplyError(
            f"managed block template missing END marker: "
            f"{operation['source']}"
        )
    block = block_content[: content_end + len(BLOCK_END_BYTES)]
    write_bytes_atomic(destination, data[:begin] + block + data[end:])


def _prepare_sources(
    plan: dict,
    package_root: Path | None,
) -> dict[str, bytes]:
    prepared: dict[str, bytes] = {}
    for operation in plan["files"]:
        if operation["classification"] not in (
            "ADD",
            "UPDATE_SAFE",
            "BLOCK_PRESENT",
        ):
            continue
        prepared[operation["destination"]] = _read_package_bytes(
            package_root,
            operation,
        )
    return prepared


def _executor_root(source: Source | None) -> Path:
    if source is None:
        return Path(__file__).resolve().parent.parent

    candidates = (
        source.package_root / "skills" / "themasterplan" / "scripts",
        # Temporary compatibility for a branch before the directory rename.
        source.package_root
        / "skills"
        / "agentic-wonderwall"
        / "scripts",
    )
    for candidate in candidates:
        if (candidate / "themasterplan.py").is_file():
            return candidate
    raise ApplyError(
        "source package does not contain the TheMasterplan executor"
    )


def prepare_executor_bundle(source: Source | None) -> dict[str, bytes]:
    """Read every executor file before the first executor write."""
    root = _executor_root(source)
    prepared: dict[str, bytes] = {}
    for relative in EXECUTOR_FILES:
        prepared[relative] = read_package_file(root, relative)
    return prepared


def install_executor(
    project_root: Path,
    written: list[str],
    unchanged: list[str],
    *,
    source: Source | None = None,
    prepared: dict[str, bytes] | None = None,
) -> tuple[list[str], list[str]]:
    """Install the executor from the target source, never from the old copy."""
    bundle = prepared or prepare_executor_bundle(source)
    bin_root = safe_join(project_root, ".themasterplan/bin")
    changed = False
    for relative, content in bundle.items():
        target = safe_join(bin_root, relative)
        if target.is_file() and sha256_of_file(target) == _sha256_bytes(content):
            continue
        write_bytes_atomic(target, content)
        changed = True

    summary_path = ".themasterplan/bin/themasterplan.py"
    if changed:
        written.append(summary_path)
    else:
        unchanged.append(summary_path)
    return written, unchanged


def _check_precondition(
    project_root: Path,
    operation: dict,
    prepared_sources: dict[str, bytes],
    plan: dict,
) -> None:
    destination = safe_join(project_root, operation["destination"])
    classification = operation["classification"]
    if classification == "ADD":
        if destination.exists():
            content = prepared_sources[operation["destination"]]
            if operation["ownership"] == "managed-block":
                if _block_content_matches(destination, content):
                    return
                raise ApplyError(
                    "managed block differs: "
                    f"{operation['destination']}"
                )
            rendered = (
                _render_template(content, plan)
                if operation.get("render")
                else content
            )
            if destination.is_file() and (
                sha256_of_file(destination) == _sha256_bytes(rendered)
            ):
                return
            raise ApplyError(
                f"plan says ADD but target exists: "
                f"{operation['destination']}"
            )
        return
    if classification == "UNCHANGED":
        if not destination.is_file():
            raise ApplyError(
                f"plan says UNCHANGED but file is missing: "
                f"{operation['destination']}"
            )
        _check_observed(project_root, operation)
        return
    if classification in ("EXISTS_KEEP", "PROJECT_OWNED"):
        _check_observed(project_root, operation)
        return
    if classification == "CONFLICT":
        raise ApplyError(
            f"managed file conflict: {operation['destination']}"
        )
    if classification == "BLOCK_MISSING":
        raise ApplyError(
            f"managed block missing: {operation['destination']}"
        )
    if classification == "BLOCK_PRESENT":
        if not destination.is_file():
            raise ApplyError(
                f"managed-block target missing: "
                f"{operation['destination']}"
            )
        if _block_bounds(destination.read_text(
            encoding="utf-8",
            errors="replace",
        )) is None:
            raise ApplyError(
                f"managed block markers invalid: "
                f"{operation['destination']}"
            )
        _check_observed(project_root, operation)
        return
    raise ApplyError(f"unknown classification: {classification}")


def _executor_state(project_root: Path) -> dict[str, dict]:
    managed: dict[str, dict] = {}
    bin_root = safe_join(project_root, ".themasterplan/bin")
    for relative in EXECUTOR_FILES:
        target = safe_join(bin_root, relative)
        if not target.is_file():
            continue
        digest = sha256_of_file(target)
        destination = f".themasterplan/bin/{relative}"
        managed[destination] = {
            "source": f"<executor>:{relative}",
            "source_sha256": digest,
            "installed_sha256": digest,
            "ownership": "managed-replace",
        }
    return managed


def _build_state(project_root: Path, plan: dict) -> dict:
    managed: dict[str, dict] = {}
    for operation in plan["files"]:
        if operation["ownership"] not in (
            "managed-replace",
            "managed-block",
        ):
            continue
        destination = operation["destination"]
        target = safe_join(project_root, destination)
        if not target.is_file():
            continue
        installed = (
            sha256_of_block(target)
            if operation["ownership"] == "managed-block"
            else sha256_of_file(target)
        )
        managed[destination] = {
            "source": operation["source"],
            "source_sha256": operation.get("source_sha256"),
            "installed_sha256": installed,
            "ownership": operation["ownership"],
        }
    managed.update(_executor_state(project_root))
    return {
        "schema_version": 1,
        "source": plan["source"],
        "selection": plan["selection"],
        "managed_files": managed,
        "adoption": {
            "date": None,
            "platform": None,
            "git_version": None,
            "jj_version": None,
            "status": "PARTIAL",
        },
    }


def apply_adopt(
    project_root: Path,
    plan_path: Path,
    source: Source | None = None,
) -> dict:
    plan = read_json(plan_path)
    _validate_plan(plan)
    if source is None:
        raise ApplyError("apply-adopt requires --source")
    if source.as_dict() != plan.get("source"):
        raise ApplyError("resolver source does not match plan source")

    prepared_sources = _prepare_sources(plan, source.package_root)
    prepared_executor = prepare_executor_bundle(source)

    for operation in plan["files"]:
        _check_precondition(
            project_root,
            operation,
            prepared_sources,
            plan,
        )

    written: list[str] = []
    unchanged: list[str] = []
    for operation in plan["files"]:
        destination = safe_join(project_root, operation["destination"])
        classification = operation["classification"]
        if classification in ("EXISTS_KEEP", "PROJECT_OWNED", "UNCHANGED"):
            unchanged.append(operation["destination"])
            continue
        if classification == "ADD":
            if destination.is_file():
                unchanged.append(operation["destination"])
                continue
            content = prepared_sources[operation["destination"]]
            if operation.get("render"):
                content = _render_template(content, plan)
            if operation["destination"] == "AGENTS.md":
                content = _make_minimal_agents(content)
            write_bytes_atomic(destination, content)
            written.append(operation["destination"])
        elif classification == "BLOCK_PRESENT":
            _apply_block(
                project_root,
                operation,
                prepared_sources[operation["destination"]],
            )
            written.append(operation["destination"])
        else:
            raise ApplyError(
                f"cannot apply classification {classification}"
            )

    written, unchanged = install_executor(
        project_root,
        written,
        unchanged,
        source=source,
        prepared=prepared_executor,
    )
    write_json_atomic(
        project_root / ".themasterplan/state.json",
        _build_state(project_root, plan),
    )
    return {"written": written, "unchanged": unchanged}
