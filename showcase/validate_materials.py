#!/usr/bin/env python3
"""Re-derive the showcase material manifests from the files on disk.

The v0.2 batch ships two films, each documented by a ``materials.json`` that
binds the delivery film, the captures it was built from, the caption sources and
the QA report.  This script re-computes every binding (bytes, SHA-256, commit,
date, caption tokens, ffprobe facts, QA facts) so a stale or hand-edited
manifest cannot pass unnoticed.

Usage::

    python showcase/validate_materials.py [--root PATH] [--only 90s|review]

Paths inside ``materials.json`` are normally resolved against the film's project
directory (``showcase/privacytrace-90s`` or ``showcase/privacytrace-review``),
not against the manifest file itself: the review manifest lives in ``delivery/``
yet still names paths such as ``delivery/PrivacyTrace-Review-1080p.mp4``.  The
current batch builder writes repo-root-relative paths instead
(``showcase/privacytrace-90s/delivery/...``) with ``qa`` nested inside ``film``;
both layouts are accepted, and the project-relative form wins if both exist.

Exit codes: 0 = every assertion passed, 1 = at least one failure, 2 = bad usage.
Standard library only; ``ffprobe`` is required on PATH.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

#: The two films covered by a capture batch.  ``materials`` is repo-root
#: relative, ``project`` is the root that paths inside the manifest resolve to.
FILMS = {
    "90s": {
        "materials": "showcase/privacytrace-90s/materials.json",
        "project": "showcase/privacytrace-90s",
    },
    "review": {
        "materials": "showcase/privacytrace-review/delivery/materials.json",
        "project": "showcase/privacytrace-review",
    },
}

COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
RATIONAL_RE = re.compile(r"([0-9]+)/([0-9]+)")

ALLOWED_ASSET_KINDS = ("screenshot", "recording")
QA_SOURCES = ("showcase-qa", "review-manifest")

# Policy thresholds from issue #264.  They are rules, not capture data, so they
# stay in the script while every hash/date/count is read from the manifest.
DURATION_TOLERANCE_SECONDS = 0.2
FPS_TOLERANCE = 0.01
MAX_BLACK_SEGMENTS = 6
LOUDNESS_LUFS_RANGE = (-20.0, -12.0)

# QA generators spell these differently; support nested and flat variants.
LOUDNESS_KEYS = (
    "loudness.integratedLufs",
    "loudness.integrated_lufs",
    "integratedLufs",
    "integrated_lufs",
)
# The review manifest records either mean/peak dBFS (older EAC report) or
# integrated LUFS plus true peak (rebuild_manifest.py); both satisfy the
# "audio level was measured" assertion.
AUDIO_MEAN_KEYS = ("meanDb", "mean_db", "mean", "integratedLufs", "integrated_lufs")
AUDIO_PEAK_KEYS = ("peakDb", "peak_db", "peak", "truePeakDbfs", "true_peak_dbfs", "truePeakDb")

ABSENT = object()
Report = Callable[[str, str], None]


# --------------------------------------------------------------------------- #
# Small typed readers: they report through a ``report(where, message)`` callable
# so the same helpers can describe failures rooted in materials.json or in a
# nested QA file.
# --------------------------------------------------------------------------- #


def shape(value: object) -> str:
    """Compact, single-line description of an unexpected JSON value."""
    text = repr(value)
    if len(text) > 72:
        text = text[:69] + "..."
    return f"{type(value).__name__} {text}"


def join_where(where: str, key: str) -> str:
    return f"{where}.{key}" if where else key


def field_of(mapping: object, key: str, report: Report, where: str) -> object:
    """Read ``mapping[key]``, reporting a missing key instead of raising."""
    if not isinstance(mapping, dict):
        report(where, f"expected object, got {shape(mapping)}")
        return ABSENT
    if key not in mapping:
        report(join_where(where, key), "missing")
        return ABSENT
    return mapping[key]


def expect_string(value: object, report: Report, where: str) -> str | None:
    if value is ABSENT:
        return None
    if isinstance(value, str) and value.strip():
        return value
    report(where, f"expected non-empty string, got {shape(value)}")
    return None


def expect_int(value: object, report: Report, where: str, *, positive: bool = False) -> int | None:
    if value is ABSENT:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        report(where, f"expected integer, got {shape(value)}")
        return None
    if positive and value <= 0:
        report(where, f"expected positive integer, got {value}")
        return None
    return value


def expect_number(value: object, report: Report, where: str, *, positive: bool = False) -> float | None:
    if value is ABSENT:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        report(where, f"expected number, got {shape(value)}")
        return None
    number = float(value)
    if not math.isfinite(number):
        report(where, f"expected finite number, got {value!r}")
        return None
    if positive and number <= 0:
        report(where, f"expected positive number, got {number}")
        return None
    return number


def expect_true(value: object, report: Report, where: str) -> bool | None:
    if value is ABSENT:
        return None
    if value is not True:
        report(where, f"expected true, got {shape(value)}")
        return None
    return True


def expect_list(value: object, report: Report, where: str) -> list | None:
    if value is ABSENT:
        return None
    if not isinstance(value, list):
        report(where, f"expected array, got {shape(value)}")
        return None
    return value


def expect_string_list(value: object, report: Report, where: str, *, label: str) -> list[str] | None:
    items = expect_list(value, report, where)
    if items is None:
        return None
    cleaned: list[str] = []
    valid = True
    for index, item in enumerate(items):
        if isinstance(item, str) and item:
            cleaned.append(item)
        else:
            report(f"{where}[{index}]", f"expected non-empty string in {label} array, got {shape(item)}")
            valid = False
    return cleaned if valid else None


def expect_commit(value: object, report: Report, where: str) -> str | None:
    if value is ABSENT:
        return None
    if isinstance(value, str) and COMMIT_RE.fullmatch(value):
        return value
    report(where, f"expected 40 lowercase hex characters, got {shape(value)}")
    return None


def expect_sha256(value: object, report: Report, where: str) -> str | None:
    if value is ABSENT:
        return None
    if isinstance(value, str) and SHA256_RE.fullmatch(value):
        return value
    report(where, f"expected 64 lowercase hex characters, got {shape(value)}")
    return None


def expect_date(value: object, report: Report, where: str) -> str | None:
    if value is ABSENT:
        return None
    if isinstance(value, str) and DATE_RE.fullmatch(value):
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            pass
        else:
            return value
    report(where, f"expected ISO date (YYYY-MM-DD), got {shape(value)}")
    return None


def parse_fps(value: object) -> float | None:
    """Accept a number or an ffprobe-style ``num/den`` (also a decimal string)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    if isinstance(value, str):
        text = value.strip()
        match = RATIONAL_RE.fullmatch(text)
        if match is not None:
            denominator = int(match.group(2))
            return int(match.group(1)) / denominator if denominator else None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) and number > 0 else None
    return None


def expect_fps(value: object, report: Report, where: str) -> float | None:
    if value is ABSENT:
        return None
    parsed = parse_fps(value)
    if parsed is None:
        report(where, f"expected fps as number or 'num/den' string, got {shape(value)}")
        return None
    return parsed


def lookup_dotted(document: dict, paths: tuple[str, ...]) -> object:
    """Look a value up as a flat key or as a dotted nested path."""
    for path in paths:
        if path in document:
            return document[path]
        current: object = document
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = ABSENT
                break
            current = current[part]
        if current is not ABSENT:
            return current
    return ABSENT


# --------------------------------------------------------------------------- #
# Filesystem, ffprobe and failure collection
# --------------------------------------------------------------------------- #


def read_json(path: Path) -> tuple[object | None, str | None]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, "file not found"
    except OSError as exc:
        return None, f"cannot read: {exc}"
    except UnicodeDecodeError as exc:
        return None, f"not valid UTF-8: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_int(value: object) -> int | None:
    number = _as_float(value)
    return int(number) if number is not None else None


def probe_media(path: Path) -> tuple[dict | None, str | None]:
    """Return ``(probe, error)`` with numeric duration/width/height/fps."""
    executable = shutil.which("ffprobe")
    if executable is None:
        return None, "ffprobe not found on PATH; cannot verify film duration, size and frame rate"
    try:
        completed = subprocess.run(
            [executable, "-v", "error", "-of", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        return None, f"cannot execute ffprobe: {exc}"
    if completed.returncode != 0:
        lines = [line for line in (completed.stderr or "").strip().splitlines() if line.strip()]
        detail = lines[-1] if lines else "no diagnostic output"
        return None, f"ffprobe failed (exit {completed.returncode}): {detail}"
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, f"ffprobe returned unparsable JSON: {exc}"
    streams = payload.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if not isinstance(video, dict):
        return None, "ffprobe found no video stream"
    fmt = payload.get("format") or {}
    duration = _as_float(fmt.get("duration"))
    if duration is None:
        duration = _as_float(video.get("duration"))
    width = _as_int(video.get("width"))
    height = _as_int(video.get("height"))
    fps = parse_fps(video.get("avg_frame_rate"))
    if fps is None:
        fps = parse_fps(video.get("r_frame_rate"))
    if duration is None:
        return None, "ffprobe did not report a duration"
    if width is None or height is None:
        return None, "ffprobe did not report video dimensions"
    if fps is None:
        return None, "ffprobe did not report a frame rate"
    return {"duration": duration, "width": width, "height": height, "fps": fps}, None


class Checker:
    """Collects one-line failures for a single film's manifest."""

    def __init__(self, film_id: str, materials_rel: str, root: Path, project_dir: Path) -> None:
        self.film_id = film_id
        self.materials_rel = materials_rel
        self.root = root
        self.project_dir = project_dir
        self.failures: list[str] = []
        self.header: dict[str, str | None] = {"batch": None, "baselineCommit": None, "capturedAt": None}

    def fail(self, where: str, message: str) -> None:
        where = " ".join(str(where).splitlines())
        message = " ".join(str(message).splitlines())
        location = f"{self.materials_rel}: {where}" if where else self.materials_rel
        self.failures.append(f"[{self.film_id}] {location}: {message}")

    report = fail

    def raw_fail(self, message: str) -> None:
        self.failures.append(f"[{self.film_id}] {self.materials_rel}: {' '.join(message.splitlines())}")

    def check(self, condition: bool, where: str, message: str) -> bool:
        if not condition:
            self.fail(where, message)
        return bool(condition)

    def display(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return Path(path).as_posix()


def resolve_path(checker: Checker, rel: str | None, where: str) -> Path | None:
    """Resolve a manifest path against the project root, then the repo root.

    The canonical layout is project-relative (``delivery/x.mp4``); the batch
    builder in ``showcase/materials-20261023-v02`` writes repo-root-relative
    paths (``showcase/privacytrace-90s/delivery/x.mp4``).  The project-relative
    candidate wins when both resolve to an existing file.
    """
    if rel is None:
        return None
    candidate = Path(rel)
    if candidate.is_absolute():
        checker.fail(where, f"expected a project-relative path, got {rel!r}")
        return None
    project_dir = checker.project_dir.resolve()
    root = checker.root.resolve()
    project_target = (project_dir / candidate).resolve()
    try:
        project_target.relative_to(project_dir)
    except ValueError:
        checker.fail(where, f"path escapes the project directory: {rel!r}")
        return None
    root_target = (root / candidate).resolve()
    try:
        root_target.relative_to(root)
    except ValueError:
        checker.fail(where, f"path escapes the repository root: {rel!r}")
        return None
    if project_target.exists():
        return project_target
    if root_target.exists():
        return root_target
    first_part = candidate.parts[0] if candidate.parts else ""
    if first_part and (root / first_part).exists() and not (project_dir / first_part).exists():
        return root_target
    return project_target


def check_file(
    checker: Checker,
    target: Path | None,
    where: str,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
    *,
    bytes_where: str | None = None,
    sha256_where: str | None = None,
) -> bool:
    """Assert existence, size and digest of one material file."""
    if target is None:
        return False
    shown = checker.display(target)
    if not target.is_file():
        checker.fail(where, f"file not found: {shown}")
        return False
    if expected_bytes is not None:
        actual = target.stat().st_size
        checker.check(
            actual == expected_bytes,
            bytes_where or where,
            f"bytes mismatch: JSON {expected_bytes}, file {actual} ({shown})",
        )
    if expected_sha256 is not None:
        try:
            actual = sha256_of(target)
        except OSError as exc:
            checker.fail(sha256_where or where, f"cannot read {shown}: {exc}")
            return False
        checker.check(
            actual == expected_sha256,
            sha256_where or where,
            f"sha256 mismatch: JSON {expected_sha256}, file {actual} ({shown})",
        )
    return True


# --------------------------------------------------------------------------- #
# Assertions a-e
# --------------------------------------------------------------------------- #


def validate_header(checker: Checker, data: dict) -> dict[str, str | None]:
    checker.header["batch"] = expect_string(field_of(data, "batch", checker.report, ""), checker.report, "batch")
    checker.header["baselineCommit"] = expect_commit(
        field_of(data, "baselineCommit", checker.report, ""), checker.report, "baselineCommit"
    )
    checker.header["capturedAt"] = expect_date(
        field_of(data, "capturedAt", checker.report, ""), checker.report, "capturedAt"
    )
    return checker.header


def validate_film_block(checker: Checker, data: dict) -> dict | None:
    film = field_of(data, "film", checker.report, "")
    if film is ABSENT:
        return None
    if not isinstance(film, dict):
        checker.fail("film", f"expected object, got {shape(film)}")
        return None
    info = {
        "path": expect_string(field_of(film, "path", checker.report, "film"), checker.report, "film.path"),
        "bytes": expect_int(
            field_of(film, "bytes", checker.report, "film"), checker.report, "film.bytes", positive=True
        ),
        "sha256": expect_sha256(field_of(film, "sha256", checker.report, "film"), checker.report, "film.sha256"),
        "durationSeconds": expect_number(
            field_of(film, "durationSeconds", checker.report, "film"),
            checker.report,
            "film.durationSeconds",
            positive=True,
        ),
        "fps": expect_fps(field_of(film, "fps", checker.report, "film"), checker.report, "film.fps"),
        "width": expect_int(
            field_of(film, "width", checker.report, "film"), checker.report, "film.width", positive=True
        ),
        "height": expect_int(
            field_of(film, "height", checker.report, "film"), checker.report, "film.height", positive=True
        ),
        # The batch builder nests QA under film; keep it for validate_qa.
        "qa": film.get("qa"),
    }
    target = resolve_path(checker, info["path"], "film.path")
    if target is not None:
        # Existence is required even when bytes/sha256 themselves are malformed.
        check_file(
            checker,
            target,
            "film.path",
            info["bytes"],
            info["sha256"],
            bytes_where="film.bytes",
            sha256_where="film.sha256",
        )
        if target.is_file():
            validate_probe(checker, target, info)
    return info


def validate_probe(checker: Checker, target: Path, film: dict) -> None:
    probe, error = probe_media(target)
    if error is not None:
        checker.fail("film", error)
        return
    expected_duration = film["durationSeconds"]
    if expected_duration is not None:
        difference = abs(probe["duration"] - expected_duration)
        checker.check(
            difference <= DURATION_TOLERANCE_SECONDS,
            "film.durationSeconds",
            f"duration mismatch: JSON {expected_duration:.3f}s, ffprobe {probe['duration']:.3f}s "
            f"(diff {difference:.3f}s > {DURATION_TOLERANCE_SECONDS}s tolerance)",
        )
    for key in ("width", "height"):
        expected = film[key]
        if expected is not None:
            checker.check(
                probe[key] == expected,
                f"film.{key}",
                f"{key} mismatch: JSON {expected}, ffprobe {probe[key]}",
            )
    expected_fps = film["fps"]
    if expected_fps is not None:
        checker.check(
            abs(probe["fps"] - expected_fps) <= FPS_TOLERANCE,
            "film.fps",
            f"fps mismatch: JSON {expected_fps:g}, ffprobe {probe['fps']:g}",
        )


def validate_assets(checker: Checker, data: dict) -> int:
    assets = field_of(data, "assets", checker.report, "")
    if assets is ABSENT:
        return 0
    if not isinstance(assets, list):
        checker.fail("assets", f"expected array, got {shape(assets)}")
        return 0
    baseline_commit = checker.header["baselineCommit"]
    batch_date = checker.header["capturedAt"]
    checked = 0
    for index, asset in enumerate(assets):
        where = f"assets[{index}]"
        if not isinstance(asset, dict):
            checker.fail(where, f"expected object, got {shape(asset)}")
            continue
        rel = expect_string(field_of(asset, "path", checker.report, where), checker.report, f"{where}.path")
        expected_bytes = expect_int(
            field_of(asset, "bytes", checker.report, where), checker.report, f"{where}.bytes", positive=True
        )
        expected_sha = expect_sha256(
            field_of(asset, "sha256", checker.report, where), checker.report, f"{where}.sha256"
        )
        capture_commit = expect_commit(
            field_of(asset, "captureCommit", checker.report, where), checker.report, f"{where}.captureCommit"
        )
        captured_at = expect_date(
            field_of(asset, "capturedAt", checker.report, where), checker.report, f"{where}.capturedAt"
        )
        kind = expect_string(field_of(asset, "kind", checker.report, where), checker.report, f"{where}.kind")
        if kind is not None and kind not in ALLOWED_ASSET_KINDS:
            checker.fail(f"{where}.kind", f"expected 'screenshot' or 'recording', got {kind!r}")
        if capture_commit is not None and baseline_commit is not None and capture_commit != baseline_commit:
            checker.fail(
                f"{where}.captureCommit",
                f"does not match baselineCommit {baseline_commit} (got {capture_commit})",
            )
        if captured_at is not None and batch_date is not None and captured_at != batch_date:
            checker.fail(
                f"{where}.capturedAt",
                f"does not match batch capturedAt {batch_date} (got {captured_at})",
            )
        target = resolve_path(checker, rel, f"{where}.path")
        if check_file(
            checker,
            target,
            f"{where}.path",
            expected_bytes,
            expected_sha,
            bytes_where=f"{where}.bytes",
            sha256_where=f"{where}.sha256",
        ):
            checked += 1
    return checked


def validate_captions(checker: Checker, data: dict) -> int:
    captions = field_of(data, "captions", checker.report, "")
    if captions is ABSENT:
        return 0
    if not isinstance(captions, list):
        checker.fail("captions", f"expected array, got {shape(captions)}")
        return 0
    checked = 0
    for index, caption in enumerate(captions):
        where = f"captions[{index}]"
        if not isinstance(caption, dict):
            checker.fail(where, f"expected object, got {shape(caption)}")
            continue
        rel = expect_string(field_of(caption, "path", checker.report, where), checker.report, f"{where}.path")
        required = expect_string_list(
            field_of(caption, "required", checker.report, where),
            checker.report,
            f"{where}.required",
            label="required",
        )
        forbidden = expect_string_list(
            field_of(caption, "forbidden", checker.report, where),
            checker.report,
            f"{where}.forbidden",
            label="forbidden",
        )
        target = resolve_path(checker, rel, f"{where}.path")
        if target is None:
            continue
        shown = checker.display(target)
        if not target.is_file():
            checker.fail(f"{where}.path", f"file not found: {shown}")
            continue
        try:
            text = target.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            checker.fail(f"{where}.path", f"cannot read {shown}: {exc}")
            continue
        if not text.strip():
            checker.fail(f"{where}.path", f"caption file is empty: {shown}")
            continue
        for token_index, token in enumerate(required or []):
            if token not in text:
                checker.fail(
                    f"{where}.required[{token_index}]",
                    f"missing required token {token!r} in {shown}",
                )
        for token_index, token in enumerate(forbidden or []):
            if token in text:
                checker.fail(
                    f"{where}.forbidden[{token_index}]",
                    f"forbidden token {token!r} present in {shown}",
                )
        checked += 1
    return checked


def validate_qa(checker: Checker, data: dict, film: dict) -> int:
    container = "qa"
    if "qa" in data:
        qa = data["qa"]
    elif isinstance(film, dict) and "qa" in film:
        container = "film.qa"
        qa = film["qa"]
    else:
        checker.fail("qa", "missing (expected top-level 'qa' or 'film.qa')")
        return 0
    if not isinstance(qa, dict):
        checker.fail(container, f"expected object, got {shape(qa)}")
        return 0
    rel = expect_string(
        field_of(qa, "path", checker.report, container), checker.report, f"{container}.path"
    )
    source = expect_string(
        field_of(qa, "source", checker.report, container), checker.report, f"{container}.source"
    )
    if source is not None and source not in QA_SOURCES:
        checker.fail(f"{container}.source", f"expected one of {', '.join(QA_SOURCES)}, got {source!r}")
        return 0
    target = resolve_path(checker, rel, f"{container}.path")
    if target is None or source is None:
        return 0
    shown = checker.display(target)
    report_data, error = read_json(target)
    if error is not None:
        checker.fail(f"{container}.path", f"{shown}: {error}")
        return 0
    if not isinstance(report_data, dict):
        checker.fail(
            f"{container}.path", f"{shown}: top-level JSON must be an object, got {shape(report_data)}"
        )
        return 0
    if source == "showcase-qa":
        validate_showcase_qa(checker, report_data, film, shown)
    else:
        validate_review_manifest(checker, report_data, film, shown)
    return 1


def validate_showcase_qa(checker: Checker, report: dict, film: dict, shown: str) -> None:
    def fail(where: str, message: str) -> None:
        checker.fail(f"qa source {shown}", f"{where}: {message}")

    probe = field_of(report, "probe", fail, "")
    if probe is not ABSENT and not isinstance(probe, dict):
        fail("probe", f"expected object, got {shape(probe)}")
        probe = ABSENT
    if isinstance(probe, dict):
        video = field_of(probe, "video", fail, "probe")
        if video is not ABSENT and not isinstance(video, dict):
            fail("probe.video", f"expected object, got {shape(video)}")
            video = ABSENT
        if isinstance(video, dict):
            width = expect_int(field_of(video, "width", fail, "probe.video"), fail, "probe.video.width", positive=True)
            height = expect_int(
                field_of(video, "height", fail, "probe.video"), fail, "probe.video.height", positive=True
            )
            fps = expect_fps(field_of(video, "fps", fail, "probe.video"), fail, "probe.video.fps")
            for label, actual, expected in (
                ("width", width, film.get("width")),
                ("height", height, film.get("height")),
            ):
                if actual is not None and expected is not None and actual != expected:
                    fail(f"probe.video.{label}", f"does not match film.{label} {expected:g} (got {actual:g})")
            expected_fps = film.get("fps")
            if fps is not None and expected_fps is not None and abs(fps - expected_fps) > FPS_TOLERANCE:
                fail("probe.video.fps", f"does not match film.fps {expected_fps:g} (got {fps:g})")
        duration = expect_number(
            field_of(probe, "duration", fail, "probe"), fail, "probe.duration", positive=True
        )
        expected_duration = film.get("durationSeconds")
        if duration is not None and expected_duration is not None:
            difference = abs(duration - expected_duration)
            if difference > DURATION_TOLERANCE_SECONDS:
                fail(
                    "probe.duration",
                    f"does not match film.durationSeconds {expected_duration:.3f}s "
                    f"(got {duration:.3f}s, diff {difference:.3f}s > {DURATION_TOLERANCE_SECONDS}s)",
                )
    black = expect_list(field_of(report, "blackSegments", fail, ""), fail, "blackSegments")
    if black is not None and len(black) > MAX_BLACK_SEGMENTS:
        fail("blackSegments", f"{len(black)} black segments exceed the allowed {MAX_BLACK_SEGMENTS}")
    # Presence only: long static holds are expected in this film style.
    expect_list(field_of(report, "frozenSegments", fail, ""), fail, "frozenSegments")
    loudness = lookup_dotted(report, LOUDNESS_KEYS)
    if loudness is ABSENT:
        fail("loudness.integratedLufs", "missing")
    else:
        lufs = expect_number(loudness, fail, "loudness.integratedLufs")
        if lufs is not None and not (LOUDNESS_LUFS_RANGE[0] <= lufs <= LOUDNESS_LUFS_RANGE[1]):
            fail(
                "loudness.integratedLufs",
                f"integrated loudness {lufs:g} LUFS outside "
                f"[{LOUDNESS_LUFS_RANGE[0]:g}, {LOUDNESS_LUFS_RANGE[1]:g}]",
            )


def validate_review_manifest(checker: Checker, report: dict, film: dict, shown: str) -> None:
    def fail(where: str, message: str) -> None:
        checker.fail(f"qa source {shown}", f"{where}: {message}")

    file_block = field_of(report, "file", fail, "")
    if isinstance(file_block, dict):
        sha = expect_sha256(field_of(file_block, "sha256", fail, "file"), fail, "file.sha256")
        nbytes = expect_int(
            field_of(file_block, "bytes", fail, "file"), fail, "file.bytes", positive=True
        )
        if sha is not None and film.get("sha256") is not None and sha != film["sha256"]:
            fail("file.sha256", f"does not match film.sha256 {film['sha256']} (got {sha})")
        if nbytes is not None and film.get("bytes") is not None and nbytes != film["bytes"]:
            fail("file.bytes", f"does not match film.bytes {film['bytes']} (got {nbytes})")
    elif file_block is not ABSENT:
        fail("file", f"expected object, got {shape(file_block)}")

    render = field_of(report, "render", fail, "")
    if isinstance(render, dict):
        expect_true(field_of(render, "deterministic", fail, "render"), fail, "render.deterministic")
        expect_true(field_of(render, "exactPixels", fail, "render"), fail, "render.exactPixels")
        missing = expect_list(
            field_of(render, "missingAssets", fail, "render"), fail, "render.missingAssets"
        )
        if missing is not None and missing:
            fail("render.missingAssets", f"expected empty array, got {shape(missing)}")
    elif render is not ABSENT:
        fail("render", f"expected object, got {shape(render)}")

    qa_block = field_of(report, "qa", fail, "")
    if isinstance(qa_block, dict):
        expect_true(field_of(qa_block, "ok", fail, "qa"), fail, "qa.ok")
        black = expect_list(
            field_of(qa_block, "blackSegments", fail, "qa"), fail, "qa.blackSegments"
        )
        if black is not None and len(black) > MAX_BLACK_SEGMENTS:
            fail("qa.blackSegments", f"{len(black)} black segments exceed the allowed {MAX_BLACK_SEGMENTS}")
        audio = field_of(qa_block, "audio", fail, "qa")
        if isinstance(audio, dict):
            for label, keys in (("mean", AUDIO_MEAN_KEYS), ("peak", AUDIO_PEAK_KEYS)):
                value = lookup_dotted(audio, keys)
                if value is ABSENT:
                    fail(f"qa.audio.{label}", "missing")
                else:
                    expect_number(value, fail, f"qa.audio.{label}")
        elif audio is not ABSENT:
            fail("qa.audio", f"expected object, got {shape(audio)}")
    elif qa_block is not ABSENT:
        fail("qa", f"expected object, got {shape(qa_block)}")


# --------------------------------------------------------------------------- #
# Batch consistency and driver
# --------------------------------------------------------------------------- #


def read_quiet_header(root: Path, film_id: str) -> dict[str, str] | None:
    """Header-only read used by ``--only`` for the film that is not selected."""
    data, error = read_json(root / FILMS[film_id]["materials"])
    if error is not None or not isinstance(data, dict):
        return None
    header: dict[str, str] = {}
    for key in ("batch", "baselineCommit", "capturedAt"):
        value = data.get(key)
        if isinstance(value, str) and value:
            header[key] = value
    return header


def compare_batch_headers(
    left_id: str,
    left_header: dict[str, str | None],
    right_id: str,
    right_header: dict[str, str | None],
) -> list[str]:
    problems: list[str] = []
    for key in ("batch", "baselineCommit", "capturedAt"):
        left_value = left_header.get(key)
        right_value = right_header.get(key)
        if left_value is None or right_value is None:
            continue
        if left_value != right_value:
            problems.append(
                f"batch mismatch: {FILMS[left_id]['materials']} {key}={left_value!r} != "
                f"{FILMS[right_id]['materials']} {key}={right_value!r}"
            )
    return problems


def run(root: Path, only: str | None) -> tuple[list[str], dict[str, int], list[str]]:
    failures: list[str] = []
    notes: list[str] = []
    stats = {"films": 0, "assets": 0, "captions": 0, "qa": 0}
    headers: dict[str, dict[str, str | None]] = {}

    selected = [only] if only is not None else list(FILMS)
    for film_id in selected:
        spec = FILMS[film_id]
        materials_rel = spec["materials"]
        project_dir = (root / spec["project"]).resolve()
        checker = Checker(film_id, materials_rel, root, project_dir)
        data, error = read_json(root / materials_rel)
        if error is not None:
            checker.raw_fail(f"materials manifest {error}")
        elif not isinstance(data, dict):
            checker.raw_fail(f"top-level JSON must be an object, got {shape(data)}")
        else:
            headers[film_id] = validate_header(checker, data)
            film = validate_film_block(checker, data)
            stats["assets"] += validate_assets(checker, data)
            stats["captions"] += validate_captions(checker, data)
            stats["qa"] += validate_qa(checker, data, film or {})
            stats["films"] += 1
        failures.extend(checker.failures)

    if only is None:
        if len(headers) == 2:
            failures.extend(compare_batch_headers("90s", headers["90s"], "review", headers["review"]))
    elif only in headers:
        other_id = "review" if only == "90s" else "90s"
        other_header = read_quiet_header(root, other_id)
        if other_header is None:
            notes.append(
                f"note: {FILMS[other_id]['materials']} is not readable; batch consistency was not checked"
            )
        else:
            failures.extend(compare_batch_headers(only, headers[only], other_id, other_header))

    return failures, stats, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the showcase materials manifests, films, assets, captions and QA reports.",
    )
    parser.add_argument("--root", type=Path, help="repository root (default: parent of this script's directory)")
    parser.add_argument("--only", choices=sorted(FILMS), help="validate a single film")
    args = parser.parse_args(argv)

    root = args.root.resolve() if args.root is not None else Path(__file__).resolve().parent.parent
    if not root.is_dir():
        print(f"FAIL: --root is not a directory: {root}", file=sys.stderr)
        return 1

    failures, stats, notes = run(root, args.only)
    for note in notes:
        print(note, file=sys.stderr)
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        print(f"FAILED: {len(failures)} failure(s)", file=sys.stderr)
        return 1

    label = args.only if args.only is not None else "90s + review"
    print(
        f"OK: {label} materials validated "
        f"({stats['films']} film(s), {stats['assets']} asset(s), "
        f"{stats['captions']} caption file(s), {stats['qa']} QA source(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
