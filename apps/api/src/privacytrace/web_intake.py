"""Single-host intake: private immutable input revisions and bounded scan workers."""

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4

from . import pipeline
from .isolated_scan import MAX_INPUT
from .job_store import JobStore
from .models import AnalysisJob, EvaluationInput, PolicyClaim, PolicyDocument
from .policy_fetch import FetchError, display_url, fetch_policy
from .policy_intake import build_llm_execution, read_safe
from .policy_llm_extractor import (
    LLMExtractorConfig,
    PolicyLLMExtractor,
    UrllibLLMClient,
    validate_and_normalize_api_base,
)
from .resources import taxonomy
from .web_models import CandidateInput, DraftInput, ModelSettings, StartInput, WebCandidate

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


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

    def __init__(self, store):
        self.store = store
        self.root = store.root / "web"
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="privacytrace-scan")
        self.futures = {}
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

    def _save(self, draft):
        directory = self.directory(draft["id"])
        revision = draft["revision"]
        if revision > self.MAX_REVISIONS:
            raise ValueError("Input revision limit reached; create a new draft")
        if sum(p.stat().st_size for p in directory.glob("revision-*.json")) > 128 * 1024 * 1024:
            raise ValueError("Input history quota reached; create a new draft")
        snapshot = self._safe(directory / f"revision-{revision}.json")
        if snapshot.exists():
            raise ValueError("Input revision already exists")
        write_private(snapshot, draft)
        write_private(self._safe(directory / "current.json"), draft)
        return draft

    def _get(self, draft_id):
        path = self.directory(draft_id) / "current.json"
        if not path.exists():
            raise KeyError(draft_id)
        return self._read(path)

    def get(self, draft_id):
        with self.data_store._transaction():
            return self._get(draft_id)

    def get_draft_token_digest(self, draft_id: str) -> str | None:
        with self.data_store._transaction():
            self._get(draft_id)
            path = self._safe(self.directory(draft_id) / "capability.json")
            if not path.exists():
                return None
            return self._read(path)["token_digest"]

    def create(self, payload: DraftInput, token_digest: str | None = None):
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
            if len(list(self.root.glob("*/current.json"))) >= self.MAX_DRAFTS:
                raise ValueError("Local draft quota reached")
            draft_id = uuid4().hex
            self.directory(draft_id).mkdir(mode=0o700)
            if token_digest is not None:
                write_private(self._safe(self.directory(draft_id) / "capability.json"), {"token_digest": token_digest})
            return self._save(
                {
                    "id": draft_id,
                    "revision": 1,
                    "name": payload.name,
                    "sources": sources,
                    "candidates": [],
                    "uploaded": False,
                    "apk_sha256": None,
                    "jobs": [],
                    "created_at": now(),
                }
            )

    async def upload(self, draft_id, request):
        directory = self.directory(draft_id)
        pending = self._safe(directory / "upload.pending")
        with self.data_store._transaction():
            draft = self._get(draft_id)
            if draft["uploaded"] or draft["jobs"]:
                raise ValueError("APK already uploaded; new materials require a new draft")
            fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        size = 0
        digest = hashlib.sha256()
        try:
            with os.fdopen(fd, "wb") as handle:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_INPUT:
                        raise ValueError("APK exceeds 150 MiB")
                    digest.update(chunk)
                    handle.write(chunk)
                if size == 0:
                    raise ValueError("APK is empty")
                handle.flush()
                os.fsync(handle.fileno())
            with self.data_store._transaction():
                draft = self._get(draft_id)
                os.replace(pending, self._safe(directory / "input.apk"))
                draft.update(
                    uploaded=True, apk_sha256=digest.hexdigest(), revision=draft["revision"] + 1
                )
                return self._save(draft)
        finally:
            pending.unlink(missing_ok=True)

    def _settings(self, private=False):
        path = self._safe(self.root / "model.json")
        config = (
            self._read(path)
            if path.exists()
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
            write_private(self._safe(self.root / "model.json"), config)
            return self._settings()

    def fetch_source(self, draft_id, source_id, revision):
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
            if source["status"] in {"failed", "empty"} or not source["text"].strip():
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
        known = {s["id"] for s in draft["sources"] if s["status"] not in {"failed", "empty"}}
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
            for directory in self.root.iterdir():
                if not directory.is_dir():
                    continue
                draft = self._get(directory.name)
                self._safe(directory / "upload.pending").unlink(missing_ok=True)
                for run in draft["jobs"]:
                    job = self.store.get(run["job_id"])
                    if job.state not in TERMINAL:
                        job.state = "FAILED"
                        job.error = json.dumps(
                            {"code": "SERVICE_INTERRUPTED", "message": "Retry creates a new job"}
                        )
                        self.store.save_job(job)
                        run["events"].append({"state": "FAILED", "at": now()})
                # Recover event history without modifying immutable input revisions.
                write_private(directory / "current.json", draft)

    def start(self, draft_id, payload: StartInput):
        self.start_service()
        with self.data_store._transaction():
            draft = self._get(draft_id)
            for run in draft["jobs"]:
                if run["request_id"] == payload.request_id:
                    if run["revision"] != payload.revision:
                        raise ValueError("Submission ID reused with different input")
                    return self.store.get(run["job_id"])
            if draft["revision"] != payload.revision or not draft["uploaded"]:
                raise ValueError("Input changed or APK not uploaded")
            if any(self.store.get(r["job_id"]).state not in TERMINAL for r in draft["jobs"]):
                raise ValueError("Draft already has a running job")
            if len(draft["jobs"]) >= 10 or sum(not f.done() for f in self.futures.values()) >= 4:
                raise ValueError("Local job quota reached")
            captures = self.captures(draft)
            job = AnalysisJob(
                id=uuid4().hex,
                sample_id=draft["name"],
                input_mode="APK",
                source_origin="REAL_SCAN",
                state="QUEUED",
                ruleset_version=taxonomy()["version"],
                created_at=datetime.now(timezone.utc),
            )
            self.store.create_if_absent(job, token_digest=self.get_draft_token_digest(draft_id))
            draft["jobs"].append(
                {
                    "job_id": job.id,
                    "request_id": payload.request_id,
                    "revision": draft["revision"],
                    "events": [{"state": "QUEUED", "at": now()}],
                }
            )
            write_private(self.directory(draft_id) / "current.json", draft)
            self.futures = {k: f for k, f in self.futures.items() if not f.done()}
            self.futures[job.id] = self.executor.submit(self._run, draft, job, captures)
            return job

    def _event(self, draft_id, job_id, state):
        with self.data_store._transaction():
            draft = self._get(draft_id)
            run = next(r for r in draft["jobs"] if r["job_id"] == job_id)
            run["events"].append({"state": state, "at": now()})
            write_private(self.directory(draft_id) / "current.json", draft)

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
                captured_policies=captures,
                existing_job=job,
                on_stage=lambda stage: self._event(draft["id"], job.id, stage),
                extra_tools={
                    "web_input_revision": str(draft["revision"]),
                    "web_policy_sources": json.dumps(source_receipts, ensure_ascii=False),
                },
            )
        except Exception:
            # Do not expose raw policy text, local paths, response bodies or credentials.
            job.state = "FAILED"
            job.error = json.dumps(
                {"code": "WEB_JOB_FAILED", "message": "Check inputs and runtime"}
            )
            self.store.save_job(job)
        finally:
            self._event(draft["id"], job.id, self.store.get(job.id).state)

    def close(self):
        # Cancel only jobs owned by this service; the existing scanner handles container cleanup.
        for job_id, future in self.futures.items():
            if not future.done() and self.store.get(job_id).state not in TERMINAL:
                self.store.cancel(job_id)
        self.executor.shutdown(wait=True, cancel_futures=False)
        if self.owner_fd is not None:
            os.close(self.owner_fd)
            self.owner_fd = None
