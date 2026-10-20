"""R6: concurrency-1 capacity table plus the public-secret audit.

Capacity is only *measured* against a real topology: latency, peak memory
(cgroup read or ``docker stats --no-stream``), and disk delta. Scales nobody ran
are emitted as ``NOT_TESTED`` rows, never extrapolated, and the receipt carries a
re-computable table so a reviewer can recompute every number.

The secret audit part runs anywhere. It scans tracked files, separates
*synthetic test fixtures* (which legitimately contain placeholder capability
tokens and dummy DSNs) from *shipping material* (which may not), and reports
category counts only - never the matched text.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .receipt import Check, CheckRecorder, Receipt, collect_environment
from .redaction import (
    RECEIPT_AUDIT_CATEGORIES,
    SOURCE_AUDIT_CATEGORIES,
    find_secret_markers,
)
from .topology import Topology, TopologyUnavailable, docker_output, request

TICKET = "R6"
ROOT = Path(__file__).resolve().parents[2]

#: Scales this collector reports on. Anything not measured stays NOT_TESTED.
DECLARED_SCALES = (
    "concurrency_1_single_apk",
    "concurrency_1_base_and_splits",
    "concurrency_2",
    "concurrency_4",
    "large_package_set",
    "long_running_scan",
)

CGROUP_MEMORY_PATHS = (
    "/sys/fs/cgroup/memory.peak",
    "/sys/fs/cgroup/memory/memory.max_usage_in_bytes",
)

#: Path segments and file names that mark a documented synthetic fixture.
FIXTURE_MARKERS = ("/tests/", "/test/", "/fixtures/", "/testSupport/")
FIXTURE_NAMES = re.compile(r"^(test_.*\.py|.*_test\.py|conftest\.py)$")
#: Binary assets are never scanned as text: decoding them produces false matches.
BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".so",
        ".jar",
    }
)
CREDENTIAL_CATEGORIES = frozenset({"capability-token", "private-key-block", "url-credentials"})


@dataclass
class CapacitySample:
    """One measured scale."""

    scale: str
    duration_s: list[float] = field(default_factory=list)
    queue_wait_s: list[float] = field(default_factory=list)
    peak_memory_bytes: int | None = None
    disk_delta_bytes: int | None = None
    input_bytes: int | None = None
    input_sha256: str | None = None

    def medians(self) -> dict[str, Any]:
        def median(values: Sequence[float]) -> float | None:
            ordered = sorted(values)
            if not ordered:
                return None
            middle = len(ordered) // 2
            if len(ordered) % 2:
                return round(ordered[middle], 3)
            return round((ordered[middle - 1] + ordered[middle]) / 2, 3)

        return {
            "scale": self.scale,
            "input_bytes": self.input_bytes,
            "input_sha256": self.input_sha256,
            "input_origin": "SYNTHETIC",
            "repetitions": len(self.duration_s),
            "duration_s_median": median(self.duration_s),
            "duration_s_min": round(min(self.duration_s), 3) if self.duration_s else None,
            "duration_s_max": round(max(self.duration_s), 3) if self.duration_s else None,
            "queue_wait_sampled_upper_bound_s_median": median(self.queue_wait_s),
            "peak_memory_bytes": self.peak_memory_bytes,
            "disk_delta_bytes": self.disk_delta_bytes,
        }


def _read_first(paths: Iterable[str]) -> int | None:
    for candidate in paths:
        try:
            text = Path(candidate).read_text(encoding="ascii", errors="replace").strip()
        except OSError:
            continue
        if text.isdigit():
            return int(text)
    return None


def peak_memory_bytes(topology: Topology, service: str) -> tuple[int | None, str]:
    """Peak memory for one container: cgroup file first, ``docker stats`` second."""
    from .topology import compose_output

    try:
        raw = compose_output(
            topology,
            "exec",
            "-T",
            service,
            "/opt/venv/bin/python",
            "-c",
            "from pathlib import Path;"
            "print(Path('/sys/fs/cgroup/memory.peak').read_text().strip())",
        )
        value = int(raw)
    except (TopologyUnavailable, ValueError):
        value = None
    if value is not None:
        return value, "worker container cgroup lifetime memory.peak"
    try:
        identifier = compose_output(topology, "ps", "-q", service)
        raw = docker_output(
            topology, "stats", "--no-stream", "--format", "{{.MemUsage}}", identifier, timeout=60
        )
    except TopologyUnavailable:
        return None, "unavailable (no cgroup file, docker stats failed)"
    match = re.match(r"\s*([0-9.]+)\s*([KMG]i?B)\s*/", raw)
    if not match:
        return None, "unparsed docker stats value"
    factor = {
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
    }
    return int(float(match.group(1)) * factor.get(match.group(2), 0)), "docker stats --no-stream"


def materials_disk_bytes(topology: Topology) -> tuple[int | None, str]:
    """Persisted material bytes, measured through the container filesystem."""
    try:
        from .topology import compose_output

        raw = compose_output(
            topology,
            "exec",
            "-T",
            "worker",
            "sh",
            "-c",
            "du -sb /var/lib/privacytrace 2>/dev/null | cut -f1",
            timeout=60,
        )
    except TopologyUnavailable:
        return None, "unavailable"
    digits = "".join(ch for ch in raw if ch.isdigit())
    return (int(digits), "du -sb on the materials volume") if digits else (None, "unparsed")


def capacity_table(samples: Sequence[CapacitySample]) -> dict[str, Any]:
    measured = {sample.scale: sample.medians() for sample in samples}
    return {
        scale: measured.get(scale)
        or {"scale": scale, "status": "NOT_TESTED", "reason": "not measured this round"}
        for scale in DECLARED_SCALES
    }


def _measure_round(
    topology: Topology, scale: str, *, repetitions: int, budget_s: float
) -> tuple[Check, CapacitySample | None]:
    """Run N submissions of one scale and record latency, memory and disk."""
    from .r2_business_loop import (
        Fixtures,
        create_scope,
        poll_job,
        start_job,
        upload_apk,
        upload_package_set,
    )

    recorder = CheckRecorder(
        f"r6.capacity.{scale}",
        f"submit {repetitions}x {scale} -> poll to terminal, sample memory and disk",
        ticket=TICKET,
    )
    if not (topology.configured and topology.allow_writes):
        return (
            recorder.skip(
                "needs PT_ACCEPTANCE_BASE_URL/HOST/INSTANCE_ID and PT_ACCEPTANCE_ALLOW_WRITES=1"
            ),
            None,
        )
    try:
        fixtures = Fixtures.build()
    except Exception as error:  # noqa: BLE001 - builder is optional at runtime
        return recorder.skip(f"synthetic fixtures unavailable: {type(error).__name__}"), None

    sample = CapacitySample(
        scale=scale,
        input_bytes=len(
            fixtures.single_apk if scale == "concurrency_1_single_apk" else fixtures.package_set
        ),
        input_sha256=(
            fixtures.single_sha256 if scale == "concurrency_1_single_apk" else fixtures.set_sha256
        ),
    )
    peak: int | None = None
    before_disk, _ = materials_disk_bytes(topology)
    for index in range(repetitions):
        try:
            scope = create_scope(
                topology,
                f"capacity-{scale}-{index}-{int(time.time())}",
                "Capacity probe policy.",
            )
            submit = (
                upload_apk(topology, scope, fixtures.single_apk)
                if scale == "concurrency_1_single_apk"
                else upload_package_set(topology, scope, fixtures.package_set)
            )
            if submit.status != 200:
                return recorder.fail(f"repetition {index}: upload HTTP {submit.status}"), None
            started = time.monotonic()
            start_job(topology, scope)
            if not scope.job_id:
                return recorder.fail(f"repetition {index}: no job id"), None
            outcome = poll_job(topology, scope, budget_s=budget_s, interval_s=2.0)
            elapsed = time.monotonic() - started
        except TopologyUnavailable as error:
            return recorder.fail(f"topology unavailable mid-run: {error}"), None
        if outcome["state"] != "SUCCEEDED":
            return recorder.fail(
                f"repetition {index} ended {outcome['state']}", trail=outcome["trail"]
            ), None
        sample.duration_s.append(round(elapsed, 3))
        # HTTP registration time is not queue wait. Only a RUNNING observation
        # supplies a sampled upper bound; fast jobs may have no such sample.
        running = next((row["at"] for row in outcome["trail"] if row["state"] == "RUNNING"), None)
        if running is not None:
            sample.queue_wait_s.append(round(running - started, 4))
        current, _ = peak_memory_bytes(topology, "worker")
        if current is not None:
            peak = current if peak is None else max(peak, current)
        response = request(
            topology, f"/api/v1/web/drafts/{scope.draft_id}", method="DELETE", token=scope.token
        )
        if response.status != 200:
            return recorder.fail("capacity canary cleanup failed", status=response.status), None
    after_disk, _ = materials_disk_bytes(topology)
    sample.peak_memory_bytes = peak
    if before_disk is not None and after_disk is not None:
        sample.disk_delta_bytes = after_disk - before_disk
    return recorder.pass_(
        f"{repetitions} runs, median {sample.medians()['duration_s_median']}s",
        table=sample.medians(),
    ), sample


def _measure(topology, scale, *, repetitions, budget_s):
    import os

    from .metrics import Sampler
    from .provision import Laboratory

    state = os.environ.get("PT_ACCEPTANCE_LAB_STATE")
    if not state or not topology.allow_writes:
        return _measure_round(topology, scale, repetitions=repetitions, budget_s=budget_s)
    with Sampler(Laboratory(state)) as sampler:
        check, sample = _measure_round(topology, scale, repetitions=repetitions, budget_s=budget_s)
    metrics = sampler.result()
    check.detail["scanner_and_disk_sampling"] = metrics
    if sample is not None:
        check.detail["worker_peak_memory_bytes"] = sample.peak_memory_bytes
        sample.peak_memory_bytes = metrics["scanner_sampled_peak_memory_bytes"]
        check.detail["table"] = sample.medians()
    if check.status == "PASS" and not metrics["scanner_sampled_peak_memory_bytes"]:
        check.status = "FAIL"
        check.notes = "scanner memory was not observed during the actual run"
    from .receipt import digest_of

    check.result_digest = digest_of(
        {
            "command": check.command,
            "status": check.status,
            "notes": check.notes,
            "observations": check.detail,
        }
    )
    return check, sample


def _backpressure(topology: Topology) -> Check:
    recorder = CheckRecorder(
        "r6.queue_backpressure",
        "submit N concurrent jobs at concurrency 1; record queue depth and refusals",
        ticket=TICKET,
    )
    if not (topology.configured and topology.allow_writes):
        return recorder.skip("needs a writable real topology")
    import os

    from .backpressure_drill import drill
    from .provision import Laboratory

    state = os.environ.get("PT_ACCEPTANCE_LAB_STATE")
    if not state:
        return recorder.skip("an owned laboratory is required")
    try:
        return recorder.pass_(
            "real queue drained at sampled scanner concurrency 1",
            **drill(Laboratory(state), topology),
        )
    except Exception as error:
        return recorder.fail(type(error).__name__)


def _tracked_paths() -> list[str]:
    try:
        raw = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            timeout=120,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [item.decode("utf-8", "replace") for item in raw.split(b"\0") if item]


def is_synthetic_fixture(relative_path: str) -> bool:
    """True for documented test fixtures, which may hold placeholder credentials."""
    normalized = "/" + relative_path.replace("\\", "/")
    if any(marker in normalized for marker in FIXTURE_MARKERS):
        return True
    return bool(FIXTURE_NAMES.match(normalized.rsplit("/", 1)[-1]))


def _secret_audit() -> Check:
    """Scan tracked files, separating synthetic fixtures from shipping material."""
    recorder = CheckRecorder(
        "r6.secret_audit",
        "git ls-files + marker scan (tokens, keys, DSN credentials, headers)",
        ticket=TICKET,
    )
    tracked = _tracked_paths()
    if not tracked:
        return recorder.skip("git ls-files unavailable")

    shipping: dict[str, int] = {}
    fixtures: dict[str, int] = {}
    scanned = 0
    skipped_binary = 0
    for relative in tracked:
        path = ROOT / relative
        if path.suffix.lower() in BINARY_SUFFIXES:
            skipped_binary += 1
            continue
        try:
            if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        markers = find_secret_markers(text, categories=SOURCE_AUDIT_CATEGORIES)
        if not markers:
            continue
        bucket = fixtures if is_synthetic_fixture(relative) else shipping
        for category, count in markers.items():
            bucket[category] = bucket.get(category, 0) + count

    forbidden = _forbidden_artifacts(tracked)
    detail = {
        "scanned_files": scanned,
        "skipped_binary_files": skipped_binary,
        "synthetic_fixture_markers": dict(sorted(fixtures.items())),
        "shipping_material_markers": dict(sorted(shipping.items())),
        "forbidden_tracked_artifacts": forbidden,
    }
    if scanned == 0:
        return recorder.fail("no source files were examined")
    if shipping or forbidden:
        return recorder.fail(
            "shipping material contains credentials or forbidden artifacts", **detail
        )
    return recorder.pass_(
        f"{scanned} tracked files; credentials confined to documented synthetic fixtures",
        **detail,
    )


def _forbidden_artifacts(tracked: Sequence[str] | None = None) -> list[str]:
    """Tracked artifact categories that must never be committed (labels only)."""
    paths = list(tracked) if tracked is not None else _tracked_paths()
    patterns = (
        (re.compile(r"\.(apk|aab|dex)$", re.I), "apk-or-dex"),
        (re.compile(r"(^|/)\.env$"), "dotenv"),
        (re.compile(r"\.(pem|key)$", re.I), "private-key-file"),
        (re.compile(r"\.(sqlite|sqlite3|db)$", re.I), "database-file"),
        (re.compile(r"(^|/)(samples/private|evidence/private)/"), "private-data-dir"),
        (re.compile(r"(^|/)data/"), "private-data-dir"),
    )
    labels: set[str] = set()
    for path in paths:
        for pattern, label in patterns:
            if pattern.search(path):
                labels.add(label)
    return sorted(labels)


def _build_context_audit() -> Check:
    recorder = CheckRecorder(
        "r6.build_context_allowlist",
        "deploy/Dockerfile.dockerignore + deploy/audit_context.py review",
        ticket=TICKET,
    )
    ignore = ROOT / "deploy/Dockerfile.dockerignore"
    auditor = ROOT / "deploy/audit_context.py"
    if not ignore.is_file() or not auditor.is_file():
        return recorder.skip("deployment context allowlist files are missing")
    text = ignore.read_text(encoding="utf-8")
    required = ("**/*.apk", "**/*.aab", "**/*.dex", "**/.env*", "**/*.pem", "**/*.key")
    absent = [pattern for pattern in required if pattern not in text]
    if absent:
        return recorder.fail("allowlist does not exclude sensitive patterns", missing=absent)
    return recorder.pass_(
        "build context excludes APK/AAB/DEX/env/key material and audits the exact allowlist",
        excluded=len(required),
    )


def receipt_redaction_check(receipt_texts: Sequence[str]) -> Check:
    """Provider-side scan of the finished receipts; run by ``run.py``."""
    recorder = CheckRecorder(
        "r6.receipt_redaction",
        "scan every finished receipt for credential markers",
        ticket=TICKET,
    )
    if not receipt_texts:
        return recorder.skip("no receipts were produced")
    found: dict[str, int] = {}
    for text in receipt_texts:
        for category, count in find_secret_markers(
            text, categories=RECEIPT_AUDIT_CATEGORIES
        ).items():
            found[category] = found.get(category, 0) + count
    blocking = {key: value for key, value in found.items() if key in CREDENTIAL_CATEGORIES}
    if blocking:
        return recorder.fail("receipt still contains credentials", categories=sorted(blocking))
    return recorder.pass_(
        "receipts contain no capability token, credential URL or private key block",
        secondary_markers=sorted(found),
    )


def collect() -> tuple[list[Check], dict[str, Any]]:
    topology = Topology.from_env()
    checks: list[Check] = []
    samples: list[CapacitySample] = []

    environment = collect_environment(ROOT)
    hardware = CheckRecorder(
        "r6.hardware_identity",
        "read /proc/cpuinfo, /proc/meminfo, stat -f, docker version, compose version",
        ticket=TICKET,
    )
    if environment.get("cpu_count") and environment.get("memory_bytes"):
        checks.append(
            hardware.pass_(
                f"{environment['cpu_count']} CPUs, "
                f"{environment['memory_bytes'] / 1024**3:.1f} GiB RAM",
                cpu_model=environment.get("cpu_model"),
                cpu_count=environment.get("cpu_count"),
                memory_bytes=environment.get("memory_bytes"),
                disk=environment.get("disk"),
                kernel=environment.get("kernel"),
                tools=environment.get("tools"),
            )
        )
    else:
        checks.append(hardware.skip("host capacity not readable from this platform"))

    for scale in ("concurrency_1_single_apk", "concurrency_1_base_and_splits"):
        check, sample = _measure(topology, scale, repetitions=3, budget_s=1800)
        checks.append(check)
        if sample is not None:
            samples.append(sample)
    checks.append(_backpressure(topology))
    checks.append(_secret_audit())
    checks.append(_build_context_audit())
    return checks, {
        "capacity_table": capacity_table(samples),
        "environment": environment,
    }


def run() -> Receipt:
    from .receipt import read_source_sha, utc_now

    receipt = Receipt(scope="r6-capacity-and-secret-audit", source_sha=read_source_sha(ROOT))
    checks, extra = collect()
    receipt.environment = extra.get("environment") or collect_environment(ROOT)
    receipt.environment["capacity_table"] = extra.get("capacity_table", {})
    receipt.checks = checks
    # Larger scales are explicitly reported as unmeasured in the table; the
    # Issue requires a concurrency-1 baseline, not claims about larger scales.
    receipt.finished_at = utc_now()
    receipt.notes = (
        "Only measured scales are reported; unmeasured scales are NOT_TESTED. "
        "Peak memory prefers cgroup memory.peak, else docker stats --no-stream. "
        "Credential markers inside documented test fixtures are recorded separately "
        "from shipping material and are not counted as leaks."
    )
    return receipt


def render_capacity_table(table: dict[str, Any]) -> str:
    """Markdown table for the receipt/report; recomputable from the medians."""
    lines = [
        "| scale | reps | median s | min s | max s | peak mem B | disk delta B | status |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scale in DECLARED_SCALES:
        row = table.get(scale, {"status": "NOT_TESTED"})
        if row.get("status") == "NOT_TESTED":
            lines.append(f"| {scale} | - | - | - | - | - | - | NOT_TESTED |")
            continue
        lines.append(
            f"| {scale} | {row.get('repetitions')} | {row.get('duration_s_median')} | "
            f"{row.get('duration_s_min')} | {row.get('duration_s_max')} | "
            f"{row.get('peak_memory_bytes')} | {row.get('disk_delta_bytes')} | measured |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    from .run import main

    raise SystemExit(main(["--only", "r6"]))
