"""Single-host intake: private immutable input revisions and bounded scan workers."""

import hashlib
from copy import deepcopy
import json
import os
import re
import shutil
import stat
import time
import zipfile
import zlib
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import uuid4

from . import pipeline
from .isolated_scan import MAX_INPUT, ScanError, inspect_package_isolated
from .job_store import JobStore
from .models import AnalysisJob, EvaluationInput, PolicyClaim, PolicyDocument
from .package_set import (
    PackageFile,
    PackageSetIntegrityError,
    validate_package_set,
)
from .policy_fetch import FetchError, display_url, fetch_policy
from .policy_intake import build_llm_execution, read_safe
from .policy_llm_extractor import (
    LLMExtractorConfig,
    PolicyLLMExtractor,
    UrllibLLMClient,
    validate_and_normalize_api_base,
)
from .resources import taxonomy
from .web_models import (
    CandidateInput,
    DraftInput,
    ExternalPolicyExportInput,
    ModelSettings,
    StartInput,
    WebCandidate,
)

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


class UploadTooLarge(ValueError):
    """APK upload exceeded the documented byte limit."""


def inspect_uploaded_package(path):
    try:
        metadata = inspect_package_isolated(path)
    except ScanError as exc:
        if exc.code not in {"CORRUPTED_FILE", "DUPLICATE_SPLIT_NAME", "ZIP_INVALID"}:
            raise
        raise PackageSetIntegrityError(exc.code, "Isolated manifest inspection failed") from exc
    package = PackageFile.model_validate({**metadata["package_file"], "file_name": path.name})
    return package




def now():
    return datetime.now(timezone.utc).isoformat()


def write_private(path, value):
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Input revision too large")
    temp = path.parent / (uuid4().hex + ".tmp")
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class WebIntake:
    MAX_DRAFTS = 12  # At most 12 * 150 MiB of retained uploads, plus bounded revisions.
    MAX_REVISIONS = 256
    MAX_DRAFTS_PER_IP = 3
    DRAFT_TTL_SECONDS = 24 * 60 * 60

    def __init__(self, store):
        self.store = store
        self.root = store.root / "web"
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="privacytrace-scan")
        self.futures = {}
        self.active_drafts = {}
        self.owner_fd = None
        self.root.mkdir(exist_ok=True, mode=0o700)
        self._safe(self.root)
        self.data_store = JobStore(self.root)

    def _safe(self, path):
        if not path.absolute().is_relative_to(self.store.root):
            raise ValueError("Unsafe input path")
        if any(
            p.is_symlink() or getattr(p, "is_junction", lambda: False)()
            for p in (path, *path.parents)
        ):
            raise ValueError("Linked input path rejected")
        return path

    def directory(self, draft_id):
        if not re.fullmatch(r"[a-f0-9]{32}", draft_id):
            raise ValueError("Invalid draft ID")
        return self._safe(self.root / draft_id)

    def _read(self, path):
        return json.loads(read_safe(self._safe(path), max_bytes=8 * 1024 * 1024))

    def _write_private(self, path, value):
        write_private(self._safe(path), value)

    def _document_exists(self, path):
        return self._safe(path).exists()

    def _draft_directories(self):
        return [p for p in self.root.iterdir()
                if p.is_dir() and re.fullmatch(r"[a-f0-9]{32}", p.name)]

    def _save(self, draft):
        directory = self.directory(draft["id"])
        revision = draft["revision"]
        if revision > self.MAX_REVISIONS:
            raise ValueError("Input revision limit reached; create a new draft")
        if sum(p.stat().st_size for p in directory.glob("revision-*.json")) > 128 * 1024 * 1024:
            raise ValueError("Input history quota reached; create a new draft")
        snapshot = self._safe(directory / f"revision-{revision}.json")
        if self._document_exists(snapshot):
            raise ValueError("Input revision already exists")
        self._write_private(snapshot, draft)
        self._write_private(self._safe(directory / "current.json"), draft)
        return draft

    def _get(self, draft_id):
        path = self.directory(draft_id) / "current.json"
        if not self._document_exists(path):
            raise KeyError(draft_id)
        return self._read(path)

    def get(self, draft_id):
        with self.data_store._transaction():
            draft = self._get(draft_id)
            self._touch(draft_id)
            return draft

    def _touch(self, draft_id):
        # mtime tracks last activity without creating a new immutable revision.
        os.utime(self._safe(self.directory(draft_id) / "current.json"), None)

    @contextmanager
    def _draft_activity(self, draft_id):
        """Pin inputs across external I/O without holding the storage lock."""
        with self.data_store._transaction():
            self._get(draft_id)
            self._touch(draft_id)
            self.active_drafts[draft_id] = self.active_drafts.get(draft_id, 0) + 1
        try:
            yield
        finally:
            with self.data_store._transaction():
                remaining = self.active_drafts[draft_id] - 1
                if remaining:
                    self.active_drafts[draft_id] = remaining
                else:
                    del self.active_drafts[draft_id]
                self._touch(draft_id)

    def get_draft_token_digest(self, draft_id: str) -> str | None:
        with self.data_store._transaction():
            self._get(draft_id)
            path = self._safe(self.directory(draft_id) / "capability.json")
            if not self._document_exists(path):
                return None
            return self._read(path)["token_digest"]

    def _cleanup_expired_drafts(self):
        """Lazy cleanup during creation. Caller holds the intake transaction lock.

        Finished job reports live in JobStore outside draft directories. Active
        or uncertain jobs and ongoing uploads prevent deletion.
        """
        cutoff = time.time() - self.DRAFT_TTL_SECONDS
        for directory in self.root.iterdir():
            if not directory.is_dir() or not re.fullmatch(r"[a-f0-9]{32}", directory.name):
                continue
            directory = self.directory(directory.name)
            current = self._safe(directory / "current.json")
            capability = self._safe(directory / "capability.json")
            # Legacy local-mode inputs have no remote capability metadata.
            if not current.exists() or not capability.exists():
                continue
            if (
                current.stat().st_mtime >= cutoff
                or self.active_drafts.get(directory.name, 0)
                or any(
                    p.name.startswith("upload.pending") or p.name.startswith("packages.pending")
                    for p in directory.iterdir()
                )
            ):
                continue
            try:
                draft = self._read(current)
                active = False
                for run in draft["jobs"]:
                    future = self.futures.get(run["job_id"])
                    if future is not None and not future.done():
                        active = True
                        break
                    if self.store.get(run["job_id"]).state not in TERMINAL:
                        active = True
                        break
                if active:
                    continue
            except (KeyError, ValueError, OSError, TypeError):
                # Unknown state is not evidence of safe deletion.
                continue
            shutil.rmtree(directory)

    def create(
        self,
        payload: DraftInput,
        token_digest: str | None = None,
        owner_ip: str | None = None,
    ):
        if len({s.id for s in payload.sources}) != len(payload.sources):
            raise ValueError("Duplicate source IDs")
        sources = []
        for source in payload.sources:
            value = source.model_dump()
            # Capture/audit fields are owned by the backend, never trusted from the browser.
            value["model_audit"] = {}
            value["final_url"] = None
            value["captured_at"] = now() if source.text.strip() else None
            value["sha256"] = (
                hashlib.sha256(source.text.encode()).hexdigest() if source.text else None
            )
            value["status"] = (
                "failed"
                if source.status == "failed"
                else "manual"
                if source.text.strip()
                else "empty"
            )
            value["error_code"] = "SOURCE_UNAVAILABLE" if value["status"] == "failed" else None
            sources.append(value)
        with self.data_store._transaction():
            self._safe(self.root)
            if token_digest is not None:
                self._cleanup_expired_drafts()
            drafts = [p / "current.json" for p in self._draft_directories()
                      if self._document_exists(p / "current.json")]
            if len(drafts) >= self.MAX_DRAFTS:
                raise ValueError("Local draft quota reached")
            # Derived by the transport middleware from the trusted client peer.
            owner_hash = hashlib.sha256(owner_ip.encode()).hexdigest() if owner_ip else None
            if token_digest is not None and owner_hash:
                owned = 0
                for current in drafts:
                    capability = self._safe(current.parent / "capability.json")
                    if (
                        self._document_exists(capability)
                        and self._read(capability).get("owner_hash") == owner_hash
                    ):
                        owned += 1
                if owned >= self.MAX_DRAFTS_PER_IP:
                    raise ValueError("Client draft quota reached")
            draft_id = uuid4().hex
            directory = self.directory(draft_id)
            directory.mkdir(mode=0o700)
            try:
                if token_digest is not None:
                    self._write_private(
                        self._safe(directory / "capability.json"),
                        {"token_digest": token_digest, "owner_hash": owner_hash},
                    )
                return self._save(
                    {
                        "id": draft_id,
                        "revision": 1,
                        "name": payload.name,
                        "sources": sources,
                        "candidates": [],
                        "uploaded": False,
                        "apk_sha256": None,
                        "package_set": None,
                        "jobs": [],
                        "created_at": now(),
                    }
                )
            except Exception:
                shutil.rmtree(directory)
                raise

    @staticmethod
    def _is_multi_package_archive(path: Path) -> bool:
        """Return True if archive is a multi-package archive without root manifest."""
        if not zipfile.is_zipfile(path):
            return False
        try:
            with zipfile.ZipFile(path, "r") as zf:
                namelist = zf.namelist()
                if "AndroidManifest.xml" in namelist:
                    return False
                return any(
                    name.lower().endswith(".apk") and not name.endswith("/")
                    for name in namelist
                )
        except Exception:
            return False

    def _unpack_package_set(self, archive_path: Path, target_dir: Path) -> None:
        """Safely unpack an .apks or .zip archive containing APK files into target_dir."""
        max_entries = 500
        max_total_uncompressed = MAX_INPUT  # 150 MiB hard cap

        try:
            archive = zipfile.ZipFile(archive_path, "r")
        except (zipfile.BadZipFile, EOFError, zlib.error) as exc:
            raise PackageSetIntegrityError(
                "CORRUPTED_FILE", f"Archive is not a valid ZIP file: {exc}"
            ) from exc

        with archive:
            entries = archive.infolist()
            if len(entries) > max_entries:
                raise PackageSetIntegrityError(
                    "CORRUPTED_FILE", "Archive exceeds entry count limit"
                )

            seen = set()
            total_uncompressed = 0
            apk_entries = []

            for entry in entries:
                name = entry.filename
                if name in seen:
                    raise PackageSetIntegrityError(
                        "CORRUPTED_FILE", "Duplicate ZIP entry"
                    )
                if (
                    "\\" in entry.orig_filename
                    or name.startswith("/")
                    or ":" in name
                    or ".." in PurePosixPath(name).parts
                    or stat.S_ISLNK(entry.external_attr >> 16)
                ):
                    raise PackageSetIntegrityError(
                        "CORRUPTED_FILE", "Escaping, symbolic, or unsafe ZIP entry"
                    )
                if entry.flag_bits & 1:
                    raise PackageSetIntegrityError(
                        "CORRUPTED_FILE", "Encrypted ZIP entries are unsupported"
                    )

                seen.add(name)
                total_uncompressed += entry.file_size

                if (
                    entry.file_size > MAX_INPUT
                    or total_uncompressed > max_total_uncompressed
                    or entry.file_size > max(1, entry.compress_size) * 200
                ):
                    raise PackageSetIntegrityError(
                        "PACKAGE_SET_TOO_LARGE",
                        "Expanded size or compression ratio exceeds limit",
                        http_status=413,
                    )

                if name.lower().endswith(".apk") and not name.endswith("/"):
                    apk_entries.append(entry)

            if not apk_entries:
                raise PackageSetIntegrityError(
                    "EMPTY_PACKAGE_SET", "No APK files found in package set archive"
                )

            for entry in apk_entries:
                file_basename = PurePosixPath(entry.filename).name
                dest_path = self._safe(target_dir / file_basename)
                if not dest_path.resolve().is_relative_to(target_dir.resolve()):
                    raise PackageSetIntegrityError(
                        "CORRUPTED_FILE", "Extracted path escapes target directory"
                    )

                fd = os.open(dest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    with os.fdopen(fd, "wb") as dest_handle, archive.open(entry) as src_stream:
                        while chunk := src_stream.read(1024 * 1024):
                            dest_handle.write(chunk)
                        dest_handle.flush()
                        os.fsync(dest_handle.fileno())
                except (zipfile.BadZipFile, EOFError, zlib.error) as exc:
                    dest_path.unlink(missing_ok=True)
                    raise PackageSetIntegrityError(
                        "CORRUPTED_FILE",
                        f"Archive entry '{entry.filename}' is corrupted: {exc}",
                        http_status=400,
                    ) from exc
                except Exception:
                    dest_path.unlink(missing_ok=True)
                    raise

    async def upload(self, draft_id, request, expect_package_set: bool = False):
        directory = self.directory(draft_id)
        pending = self._safe(directory / "upload.pending")
        staging_packages = self._safe(directory / f"packages.pending.{uuid4().hex}")
        fd = None
        owns_pending = False
        published_packages = False
        published_apk = False
        rollback_draft = None
        rollback_revision = None
        try:
            with self.data_store._transaction():
                draft = self._get(draft_id)
                if draft["uploaded"] or draft["jobs"]:
                    raise ValueError("APK already uploaded; new materials require a new draft")
                fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                owns_pending = True
            size = 0
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as handle:
                fd = None  # The file object now owns the descriptor.
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_INPUT:
                        raise UploadTooLarge("Upload exceeds 150 MiB")
                    digest.update(chunk)
                    handle.write(chunk)
                if size == 0:
                    if expect_package_set:
                        raise PackageSetIntegrityError(
                            "EMPTY_PACKAGE_SET", "Package set upload is empty"
                        )
                    raise ValueError("Upload is empty")
                handle.flush()
                os.fsync(handle.fileno())

            is_pkg_set = expect_package_set or self._is_multi_package_archive(pending)

            if is_pkg_set:
                if not zipfile.is_zipfile(pending):
                    raise PackageSetIntegrityError(
                        "CORRUPTED_FILE", "Upload is not a valid ZIP/APK archive"
                    )

                try:
                    with zipfile.ZipFile(pending, "r") as zf:
                        has_root_manifest = "AndroidManifest.xml" in zf.namelist()
                except (zipfile.BadZipFile, EOFError, zlib.error) as exc:
                    raise PackageSetIntegrityError(
                        "CORRUPTED_FILE",
                        f"Upload archive central directory is corrupted: {exc}",
                        http_status=400,
                    ) from exc

                staging_packages.mkdir(mode=0o700, exist_ok=False)

                if has_root_manifest:
                    staged_base = staging_packages / "base.apk"
                    shutil.copyfile(pending, staged_base)
                    pkg_file = inspect_uploaded_package(staged_base)
                    package_set = validate_package_set([pkg_file])
                else:
                    self._unpack_package_set(pending, staging_packages)
                    package_set = validate_package_set([
                        inspect_uploaded_package(p) for p in sorted(staging_packages.iterdir())
                    ])

                with self.data_store._transaction():
                    draft = self._get(draft_id)
                    if draft["uploaded"] or draft["jobs"]:
                        raise ValueError("APK already uploaded; new materials require a new draft")

                    rollback_draft = deepcopy(draft)
                    rollback_revision = draft["revision"] + 1
                    target_packages = self._safe(directory / "packages")
                    if target_packages.exists():
                        shutil.rmtree(target_packages)
                    os.replace(staging_packages, target_packages)
                    published_packages = True

                    # Maintain input.apk as copy of base APK for backward compatibility
                    base_path = target_packages / package_set.base.file_name
                    input_apk = self._safe(directory / "input.apk")
                    if base_path.exists():
                        published_apk = True
                        shutil.copyfile(base_path, input_apk)

                    draft.update(
                        uploaded=True,
                        apk_sha256=package_set.base.sha256,
                        package_set=package_set.model_dump(),
                        revision=draft["revision"] + 1,
                    )
                    return self._save(draft)
            else:
                with self.data_store._transaction():
                    draft = self._get(draft_id)
                    if draft["uploaded"] or draft["jobs"]:
                        raise ValueError("APK already uploaded; new materials require a new draft")
                    rollback_draft = deepcopy(draft)
                    rollback_revision = draft["revision"] + 1
                    os.replace(pending, self._safe(directory / "input.apk"))
                    published_apk = True
                    draft.update(
                        uploaded=True,
                        apk_sha256=digest.hexdigest(),
                        package_set=None,
                        revision=draft["revision"] + 1,
                    )
                    return self._save(draft)
        except Exception:
            # The DB transaction may have rolled back, while rename/copy already
            # published bytes on the private volume. Only remove files owned by
            # this request; never touch an existing upload reservation.
            if published_apk:
                self._safe(directory / "input.apk").unlink(missing_ok=True)
            if published_packages:
                shutil.rmtree(self._safe(directory / "packages"), ignore_errors=True)
            if rollback_draft is not None:
                with self.data_store._transaction():
                    snapshot = self._safe(directory / f"revision-{rollback_revision}.json")
                    if not getattr(self.store, "uses_postgres", False):
                        current = self._get(draft_id)
                        if current.get("revision") == rollback_revision and current.get("uploaded"):
                            self._write_private(directory / "current.json", rollback_draft)
                    # PostgreSQL manifests roll back atomically; a marker without
                    # a document is equally safe to remove.
                    if not self._document_exists(snapshot) or not getattr(self.store, "uses_postgres", False):
                        snapshot.unlink(missing_ok=True)
            raise
        finally:
            if fd is not None:
                os.close(fd)
            if owns_pending:
                pending.unlink(missing_ok=True)
            if staging_packages.exists():
                shutil.rmtree(staging_packages, ignore_errors=True)

    def _settings(self, private=False):
        path = self._safe(self.root / "model.json")
        config = (
            self._read(path)
            if self._document_exists(path)
            else {
                "enabled": os.environ.get("PRIVACYTRACE_LLM_ENABLED", "0") == "1",
                "api_base": os.environ.get("PRIVACYTRACE_LLM_API_BASE", ""),
                "model": os.environ.get("PRIVACYTRACE_LLM_MODEL", ""),
                "api_key": os.environ.get("PRIVACYTRACE_LLM_API_KEY", ""),
            }
        )
        if private:
            return config
        public_base = config["api_base"]
        if public_base:
            try:
                public_base = validate_and_normalize_api_base(public_base)
            except ValueError:
                public_base = ""
        return {
            "enabled": config["enabled"],
            "api_base": public_base,
            "model": config["model"],
            "key_configured": bool(config.get("api_key")),
            "max_apk_bytes": MAX_INPUT,
        }

    def settings(self, private=False):
        with self.data_store._transaction():
            return self._settings(private)

    def configure(self, payload: ModelSettings):
        with self.data_store._transaction():
            previous = self._settings(private=True)
            config = payload.model_dump()
            if config["api_key"] is None:
                config["api_key"] = previous.get("api_key", "")
            if config["api_base"]:
                config["api_base"] = validate_and_normalize_api_base(config["api_base"])
            previous_base = previous.get("api_base", "").strip().rstrip("/")
            if payload.api_key is None and config["api_base"] != previous_base:
                # A credential is bound to its configured endpoint. Do not silently
                # forward a retained credential after the destination changes.
                config["api_key"] = ""
            if config["enabled"] and (
                not config["api_base"]
                or not config["model"]
                or (not config["api_key"] and not config["api_base"].startswith("http://"))
            ):
                raise ValueError("MODEL_CONFIGURATION_INCOMPLETE")
            self._write_private(self._safe(self.root / "model.json"), config)
            return self._settings()

    def fetch_source(self, draft_id, source_id, revision):
        with self._draft_activity(draft_id):
            return self._fetch_source(draft_id, source_id, revision)

    def _fetch_source(self, draft_id, source_id, revision):
        draft = self.get(draft_id)
        if draft["revision"] != revision or draft["jobs"]:
            raise ValueError("Input changed or already started")
        source = next((s for s in draft["sources"] if s["id"] == source_id), None)
        if source is None:
            raise KeyError(source_id)
        try:
            fetched = fetch_policy(source["url"])
        except FetchError as exc:
            fetched = {"status": "failed", "error_code": exc.code}
        with self.data_store._transaction():
            current = self._get(draft_id)
            if current["revision"] != revision or current["jobs"]:
                raise ValueError("Input changed while capture was running")
            source = next(s for s in current["sources"] if s["id"] == source_id)
            source.update(fetched)
            source["model_audit"] = {}
            current["candidates"] = [
                c for c in current["candidates"] if c["source_id"] != source_id
            ]
            current["revision"] += 1
            return self._save(current)

    def extract(self, draft_id, source_id, revision):
        with self._draft_activity(draft_id):
            return self._extract(draft_id, source_id, revision)

    def _extract(self, draft_id, source_id, revision):
        draft = self.get(draft_id)
        if draft["revision"] != revision or draft["jobs"]:
            raise ValueError("Input version changed or already started")
        source = next((s for s in draft["sources"] if s["id"] == source_id), None)
        if source is None or not source["text"].strip() or source["status"] == "failed":
            raise ValueError("Source text unavailable")
        config = self.settings(private=True)
        if not config["enabled"]:
            raise ValueError("MODEL_NOT_CONFIGURED")
        extractor_config = LLMExtractorConfig(
            enabled=True,
            api_base=config["api_base"],
            api_key=config["api_key"],
            model=config["model"],
            max_retries=1,
            max_requests=4,
            max_spans=4,
            max_elapsed_seconds=120,
            timeout_seconds=60,
            max_output_tokens=4096,
            max_document_candidates=100,
            client=UrllibLLMClient(
                api_key=config["api_key"],
                api_base=config["api_base"],
                model=config["model"],
                timeout=60,
                max_output_tokens=4096,
                thinking_mode=False
                if urlsplit(config["api_base"]).hostname == "api.deepseek.com"
                else None,
            ),
        )
        text = source["text"]
        # A chunk contains context across adjacent sentences; the plugin verifies every quote.
        spans = [
            {"start": i, "end": min(i + 4000, len(text)), "text": text[i : i + 4000]}
            for i in range(0, len(text), 4000)
        ]
        result = PolicyLLMExtractor(extractor_config).extract_from_spans(text, spans)
        execution = build_llm_execution(result, extractor_config, text.encode(), [])
        audit = {k: v for k, v in execution.items() if type(v) in (str, int, bool)}
        with self.data_store._transaction():
            current = self._get(draft_id)
            if current["revision"] != revision or current["jobs"]:
                raise ValueError("Input changed while extraction was running")
            source = next(s for s in current["sources"] if s["id"] == source_id)
            source["model_audit"] = audit
            # Retry replaces only this source's unchecked suggestions, preserving checked edits.
            current["candidates"] = [
                c for c in current["candidates"] if c["source_id"] != source_id or c["checked"]
            ]
            available = max(0, 800 - len(current["candidates"]))
            accepted = result.candidates[:available]
            if len(accepted) < len(result.candidates):
                audit["status"] = "PARTIAL"
                audit["limited_candidates"] = (
                    int(audit.get("limited_candidates", 0)) + len(result.candidates) - len(accepted)
                )
            for candidate in accepted:
                current["candidates"].append(
                    WebCandidate.model_validate(
                        {
                            **{k: v for k, v in candidate.items() if k != "end_offset"},
                            "id": uuid4().hex,
                            "source_id": source_id,
                        }
                    ).model_dump()
                )
            current["revision"] += 1
            return self._save(current)

    def captures(self, draft, require_checked=True):
        evidence, claims, documents = [], [], []
        for source in draft["sources"]:
            if source["status"] in {"failed", "empty", "url_only"} or not source["text"].strip():
                continue
            document_id = "web-" + source["id"]
            ref = document_id + "-snapshot"
            text = source["text"]
            document = PolicyDocument.model_validate(
                {
                    "id": document_id,
                    "source_type": source["source_type"],
                    "title": source["title"],
                    "version": source["version"] or "UNKNOWN",
                    "captured_at": source["captured_at"],
                    "artifact": {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()},
                    "completeness": "PARTIAL",
                    "extraction_status": "PARTIAL",
                    "review_status": "UNREVIEWED",
                    "attachments_status": "NOT_CHECKED",
                    "applicability": {
                        "package_name": source["package_name"] or None,
                        "version_codes": []
                        if source["version_code"] is None
                        else [source["version_code"]],
                        "regions": [source["region"]]
                        if source["region"] not in {"", "UNKNOWN"}
                        else [],
                        "product_scope": source["product"]
                        if source["product"] not in {"", "UNKNOWN"}
                        else None,
                    },
                    "evidence_id": ref,
                }
            )
            documents.append(document)
            source_locator = display_url(
                source.get("final_url") or source["url"] or "Manually supplied local policy text"
            )
            evidence.append(
                {
                    "id": ref,
                    "kind": "POLICY_DOCUMENT",
                    "status": "DECLARED",
                    "source": source_locator[:1000],
                    "locator": "Captured UTF-8 text; completeness unknown",
                    "document_id": document_id,
                    "artifact_sha256": document.artifact.sha256,
                }
            )
            for candidate in (c for c in draft["candidates"] if c["source_id"] == source["id"]):
                if require_checked and not candidate["checked"]:
                    raise ValueError("All remaining candidates must be checked or removed")
                excerpt = candidate["excerpt"]
                start = candidate.get("start_offset")
                if start is None:
                    if text.count(excerpt) != 1:
                        raise ValueError("Quote needs an unambiguous source offset")
                    start = text.index(excerpt)
                if text[start : start + len(excerpt)] != excerpt:
                    raise ValueError("Candidate quote does not match its source")
                sentence_id = "web-sentence-" + candidate["id"]
                evidence.append(
                    {
                        "id": sentence_id,
                        "kind": "POLICY_SENTENCE",
                        "status": "DECLARED",
                        "source": source_locator[:1000],
                        "locator": f"codepoints [{start},{start + len(excerpt)})",
                        "document_id": document_id,
                        "start_offset": start,
                        "end_offset": start + len(excerpt),
                        "excerpt": excerpt,
                    }
                )
                claims.append(
                    PolicyClaim.model_validate(
                        {
                            **{
                                k: candidate[k]
                                for k in (
                                    "data_type",
                                    "polarity",
                                    "subject",
                                    "action",
                                    "condition",
                                    "declared_purpose",
                                    "declared_recipient",
                                    "ambiguity_flags",
                                )
                            },
                            "id": "web-claim-" + candidate["id"],
                            "document_id": document_id,
                            "evidence_ids": [sentence_id],
                        }
                    )
                )
        if not documents:
            raise ValueError("At least one source needs policy text")
        known = {
            s["id"]
            for s in draft["sources"]
            if s["status"] not in {"failed", "empty", "url_only"}
        }
        if any(c["source_id"] not in known for c in draft["candidates"]):
            raise ValueError("Candidate references an unavailable source")
        # Reuse the full existing reference/quote/taxonomy validator before scanning.
        job = AnalysisJob(
            id="web-preflight",
            sample_id=draft["name"],
            input_mode="APK",
            source_origin="REAL_SCAN",
            state="INTAKE",
            ruleset_version=taxonomy()["version"],
            created_at=datetime.now(timezone.utc),
        )
        bundle = EvaluationInput(
            job=job,
            evidence=evidence,
            behaviors=[],
            policy_documents=documents,
            policy_claims=claims,
        )
        return [
            {
                "document": d,
                "evidence": [e for e in bundle.evidence if e.document_id == d.id],
                "claims": [c for c in bundle.policy_claims if c.document_id == d.id],
            }
            for d in bundle.policy_documents
        ]

    def save_candidates(self, draft_id, payload: CandidateInput):
        with self.data_store._transaction():
            draft = self._get(draft_id)
            if draft["revision"] != payload.revision or draft["jobs"]:
                raise ValueError("Input version changed or already started")
            if len({c.id for c in payload.candidates}) != len(payload.candidates):
                raise ValueError("Duplicate candidate IDs")
            draft["candidates"] = [c.model_dump() for c in payload.candidates]
            self.captures(draft, require_checked=False)
            draft["revision"] += 1
            return self._save(draft)

    def discover_sources(self, draft_id: str):
        with self._draft_activity(draft_id):
            with self.data_store._transaction():
                draft = self._get(draft_id)
                if draft["jobs"]:
                    raise ValueError("Draft already started; sources are immutable")
                revision = draft["revision"]
                directory = self.directory(draft_id)
                packages_dir = self._safe(directory / "packages")
                apk_files = (sorted(packages_dir.glob("*.apk")) if packages_dir.is_dir()
                             else [self._safe(directory / "input.apk")])
                apk_files = [self._safe(p) for p in apk_files if p.exists()]

            # Container I/O must not hold the lock shared by every draft.
            discovered_urls = []
            for apk_path in apk_files:
                metadata = inspect_package_isolated(apk_path)
                for url in metadata["policy_urls"]:
                    if url not in discovered_urls:
                        discovered_urls.append(url)

            with self.data_store._transaction():
                draft = self._get(draft_id)
                if draft["revision"] != revision or draft["jobs"]:
                    raise ValueError("Input changed during policy discovery")
                existing_urls = {s.get("url") for s in draft["sources"] if s.get("url")}
                new_sources = []
                for url in discovered_urls:
                    if url in existing_urls:
                        continue
                    if len(draft["sources"]) + len(new_sources) >= 8:
                        break
                    new_src = {
                        "id": f"src-auto-{uuid4().hex[:8]}",
                        "title": "Auto Discovered Policy",
                        "url": url,
                        "source_type": "IN_APP_POLICY",
                        "text": "",
                        "version": "UNKNOWN",
                        "region": "",
                        "product": "",
                        "package_name": draft.get("package_name") or "",
                        "version_code": draft.get("version_code"),
                        "status": "url_only",
                        "error_code": None,
                        "captured_at": None,
                        "sha256": None,
                        "final_url": None,
                        "provenance": "MANIFEST_METADATA",
                        "model_audit": {},
                    }
                    new_sources.append(new_src)
                    existing_urls.add(url)

                if new_sources:
                    draft["sources"].extend(new_sources)
                    draft["revision"] += 1
                    self._save(draft)

                return {"sources": draft["sources"]}

    def import_external(self, draft_id: str, payload: ExternalPolicyExportInput):
        with self.data_store._transaction():
            draft = self._get(draft_id)
            if draft["jobs"]:
                raise ValueError("Draft already started; cannot import external policy")
            if len(draft["sources"]) >= 8 or len(draft["candidates"]) + len(payload.claims) > 800:
                raise ValueError("Draft source or candidate quota reached")

            source_input = payload.source
            text = source_input.text or ""

            # Validate claim excerpts against source text
            for claim in payload.claims:
                if text.count(claim.excerpt) != 1:
                    raise ValueError(
                        f"Claim excerpt {claim.excerpt!r} is not contained in policy text"
                    )

            source_id = f"src-ext-{uuid4().hex[:8]}"
            status = source_input.status
            if status in ("url_only", "empty") or (not text.strip() and status != "failed"):
                status = "empty"
            elif status == "failed":
                status = "failed"
            elif not status:
                status = "manual" if text.strip() else "empty"

            model_audit = {}
            if payload.summary:
                model_audit["external_summary"] = payload.summary

            new_source = {
                "id": source_id,
                "title": source_input.title,
                "url": source_input.url or "",
                "source_type": "OFFICIAL_WEB_POLICY",
                "text": text,
                "version": source_input.version or "UNKNOWN",
                "region": source_input.region or "",
                "product": source_input.product or "",
                "package_name": source_input.package_name or draft.get("package_name") or "",
                "version_code": (
                    source_input.version_code
                    if source_input.version_code is not None
                    else draft.get("version_code")
                ),
                "status": status,
                "error_code": "SOURCE_UNAVAILABLE" if status == "failed" else None,
                "captured_at": now() if text.strip() else None,
                "sha256": hashlib.sha256(text.encode()).hexdigest() if text.strip() else None,
                "final_url": None,
                "provenance": "EXTERNAL_CHAT_EXPORT",
                "model_audit": model_audit,
            }

            new_candidates = []
            for claim in payload.claims:
                cand_id = f"cand-ext-{uuid4().hex[:8]}"
                pol = claim.polarity
                if pol == "POSITIVE":
                    pol = "AFFIRMATIVE"
                elif pol not in ("AFFIRMATIVE", "NEGATIVE", "UNKNOWN"):
                    pol = "UNKNOWN"
                cand = {
                    "id": cand_id,
                    "source_id": source_id,
                    "excerpt": claim.excerpt,
                    "data_type": claim.data_type,
                    "polarity": pol,
                    "subject": (
                        claim.subject
                        if claim.subject in ("HOST_APP", "THIRD_PARTY", "UNKNOWN")
                        else "HOST_APP"
                    ),
                    "action": claim.action if claim.action in ("ACCESS", "UNKNOWN") else "ACCESS",
                    "condition": claim.condition,
                    "declared_purpose": claim.declared_purpose,
                    "declared_recipient": claim.declared_recipient,
                    "ambiguity_flags": [],
                    "start_offset": text.index(claim.excerpt) if claim.excerpt in text else None,
                    "checked": False,
                }
                new_candidates.append(cand)

            draft["sources"].append(new_source)
            draft["candidates"].extend(new_candidates)
            draft["revision"] += 1
            return self._save(draft)


    def _job_unless_deleted(self, job_id):
        try:
            return self.store.get(job_id)
        except KeyError:
            if not self.store.is_tombstoned(job_id):
                raise
            return None

    def start_service(self):
        with self.data_store._transaction():
            if self.owner_fd is not None:
                return
            path = self._safe(self.root / "service.lock")
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                os.close(fd)
                raise ValueError("Another web intake process owns this store") from exc
            self.owner_fd = fd
            for directory in self._draft_directories():
                draft = self._get(directory.name)
                changed = False
                for p in directory.glob("upload.pending*"):
                    p.unlink(missing_ok=True)
                for p in directory.glob("packages.pending*"):
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
                # Recover a process killed between moving the input and
                # committing the draft; a missing revision is not authority.
                if not draft["uploaded"] and not draft["jobs"]:
                    self._safe(directory / "input.apk").unlink(missing_ok=True)
                    orphan = self._safe(directory / "packages")
                    if orphan.exists():
                        shutil.rmtree(orphan)
                for p in directory.glob("revision-*.json"):
                    if not self._document_exists(p):
                        p.unlink(missing_ok=True)
                for run in draft["jobs"]:
                    job = self._job_unless_deleted(run["job_id"])
                    if job is None:
                        continue
                    if job.state not in TERMINAL:
                        job.state = "FAILED"
                        job.error = json.dumps(
                            {"code": "SERVICE_INTERRUPTED", "message": "Retry creates a new job"}
                        )
                        self.store.save_job(job)
                        run["events"].append({"state": "FAILED", "at": now()})
                        changed = True
                # Recover event history without modifying immutable input revisions.
                if changed:
                    self._write_private(directory / "current.json", draft)

    def retry(self, job_id):
        """Retry only jobs with retained, immutable inputs owned by this intake."""
        self.start_service()
        self.store.get(job_id)  # Preserve missing/deleted job semantics.
        with self.data_store._transaction():
            for current in (directory / "current.json" for directory in self._draft_directories()):
                draft = self._read(current)
                run = next((r for r in draft["jobs"] if r["job_id"] == job_id), None)
                if run is not None:
                    draft_id = draft["id"]
                    revision = run["revision"]
                    break
            else:
                raise ValueError("RETRY_INPUT_UNAVAILABLE")
        return self.start(
            draft_id, StartInput(revision=revision, request_id=uuid4().hex), retry_of=job_id
        )

    def start(self, draft_id, payload: StartInput, *, retry_of=None):
        self.start_service()
        reservation = Future()
        try:
            job, draft, captures = self._register_start(
                draft_id, payload, reservation, retry_of=retry_of
            )
        except BaseException:
            reservation.cancel()
            raise
        if draft is None:
            reservation.cancel()
            return job
        try:
            # Submit only after the input and job records have committed.
            future = self.executor.submit(self._run, draft, job, captures)
        except RuntimeError:
            reservation.cancel()
            job.state = "FAILED"
            job.error = json.dumps({"code": "WEB_SUBMISSION_FAILED"})
            self.store.save_job(job)
            self._event(draft_id, job.id, "FAILED")
            raise ValueError("Web worker submission rejected") from None
        self.futures[job.id] = future
        return job

    def _register_start(self, draft_id, payload, reservation, *, retry_of=None):
        with self.data_store._transaction():
            draft = self._get(draft_id)
            for run in draft["jobs"]:
                if run["request_id"] == payload.request_id:
                    if run["revision"] != payload.revision:
                        raise ValueError("Submission ID reused with different input")
                    return self.store.get(run["job_id"]), None, None
            if draft["revision"] != payload.revision or not draft["uploaded"]:
                raise ValueError("Input changed or APK not uploaded")
            if retry_of is not None:
                if (
                    not any(r["job_id"] == retry_of for r in draft["jobs"])
                    or self.store.get(retry_of).state not in {"FAILED", "CANCELLED"}
                ):
                    raise ValueError("Only failed or cancelled jobs can be retried")
            for run in draft["jobs"]:
                previous = self._job_unless_deleted(run["job_id"])
                if previous is not None and previous.state not in TERMINAL:
                    raise ValueError("Draft already has a running job")
            if not re.fullmatch(r"[a-f0-9]{64}", draft.get("apk_sha256") or ""):
                raise ValueError("Registered APK digest is unavailable")
            if len(draft["jobs"]) >= 10 or sum(not f.done() for f in self.futures.values()) >= 4:
                raise ValueError("Local job quota reached")
            captures = self.captures(draft, require_checked=False)
            job = AnalysisJob(
                id=uuid4().hex,
                sample_id=draft["name"],
                input_mode="APK",
                source_origin="REAL_SCAN",
                state="QUEUED",
                ruleset_version=taxonomy()["version"],
                created_at=datetime.now(timezone.utc),
                retry_of=retry_of,
            )
            capability_path = self._safe(self.directory(draft_id) / "capability.json")
            token_digest = (
                self._read(capability_path)["token_digest"]
                if self._document_exists(capability_path) else None
            )
            if retry_of is not None:
                self.store.create_retry(job, token_digest=token_digest)
            else:
                self.store.create_if_absent(job, token_digest=token_digest)
            draft["jobs"].append({
                "job_id": job.id,
                "request_id": payload.request_id,
                "revision": draft["revision"],
                "events": [{"state": "QUEUED", "at": now()}],
            })
            self._write_private(self.directory(draft_id) / "current.json", draft)
            self.futures = {k: f for k, f in self.futures.items() if not f.done()}
            self.futures[job.id] = reservation
            return job, draft, captures

    def _event(self, draft_id, job_id, state):
        with self.data_store._transaction():
            draft = self._get(draft_id)
            run = next(r for r in draft["jobs"] if r["job_id"] == job_id)
            run["events"].append({"state": state, "at": now()})
            self._write_private(self.directory(draft_id) / "current.json", draft)

    def _run(self, draft, job, captures):
        source_receipts = [
            {
                k: s[k]
                for k in (
                    "id",
                    "title",
                    "url",
                    "final_url",
                    "source_type",
                    "status",
                    "error_code",
                    "captured_at",
                    "sha256",
                    "version",
                    "region",
                    "product",
                    "model_audit",
                )
            }
            for s in draft["sources"]
        ]
        for receipt in source_receipts:
            for field in ("url", "final_url"):
                if receipt[field]:
                    receipt[field + "_sha256"] = hashlib.sha256(receipt[field].encode()).hexdigest()
                    receipt[field] = display_url(receipt[field])
        try:
            pipeline.run(
                self.directory(draft["id"]) / "input.apk",
                None,
                draft["name"],
                store_dir=self.store.root,
                job_store=self.store,
                captured_policies=captures,
                expected_apk_sha256=draft["apk_sha256"],
                existing_job=job,
                on_stage=lambda stage: self._event(draft["id"], job.id, stage),
                extra_tools={
                    "web_input_revision": str(draft["revision"]),
                    "web_policy_sources": json.dumps(source_receipts, ensure_ascii=False),
                },
                package_set=draft.get("package_set"),
            )
        except Exception:
            # Do not expose raw policy text, local paths, response bodies or credentials.
            job.state = "FAILED"
            job.error = json.dumps(
                {"code": "WEB_JOB_FAILED", "message": "Check inputs and runtime"}
            )
            self.store.save_job(job)
        finally:
            current = self._job_unless_deleted(job.id)
            if current is not None:
                self._event(draft["id"], job.id, current.state)

    def close(self):
        # Cancel only jobs owned by this service; the existing scanner handles container cleanup.
        for job_id, future in self.futures.items():
            if not future.done():
                job = self._job_unless_deleted(job_id)
                if job is not None and job.state not in TERMINAL:
                    self.store.cancel(job_id)
        self.executor.shutdown(wait=True, cancel_futures=False)
        if self.owner_fd is not None:
            os.close(self.owner_fd)
            self.owner_fd = None
