"""Offline, lossless policy capture. Candidates are not human verification."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from .models import AnalysisJob, EvaluationInput, PolicyClaim, PolicyDocument
from .resources import taxonomy

TEAM_REVIEW_GATE = "NOT_REQUIRED_BY_WORKFLOW"

MAX_BYTES = 800000
MAX_JSON_BYTES = 32 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_safe(path, root=None, max_bytes=MAX_JSON_BYTES):
    path = Path(path).absolute()
    if any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)
    ):
        raise ValueError("Symlink paths are not allowed")
    if root and not path.is_relative_to(Path(root).absolute()):
        raise ValueError("File path escapes capture directory")
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Input missing or exceeds capture byte limit")
    return path.read_bytes()


def split_spans(text):
    """Retain every codepoint, including separators; bound excerpts to 10000."""
    spans, start = [], 0
    for end, char in enumerate(text, 1):
        if char in "。！？.!?\n" or end - start == 10000:
            spans.append({"start": start, "end": end, "text": text[start:end]})
            start = end
    if start < len(text):
        spans.append({"start": start, "end": len(text), "text": text[start:]})
    return spans


def capture(
    raw_path,
    source_url,
    version,
    output_dir,
    candidates=None,
    package=None,
    version_code=None,
    product_scope=None,
    regions=None,
    actor="Codex-assisted candidate",
    reason="Initial offline candidate capture",
    llm_extractor=None,
):
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Policy source must be HTTPS without credentials")
    raw = read_safe(raw_path, max_bytes=MAX_BYTES)
    text = raw.decode("utf-8")  # No newline, BOM, or Unicode normalization.
    if not text or len(text) > 200000:
        raise ValueError("Policy text must contain 1 to 200000 Unicode codepoints")
    if llm_extractor is not None and getattr(llm_extractor.config, "enabled", False):
        spans = split_spans(text)
        llm_res = llm_extractor.extract_from_spans(text, spans)
        candidates = list(candidates or [])
        existing_keys = {
            (c.get("excerpt"), c.get("start_offset"), c.get("end_offset"), c.get("data_type"))
            for c in candidates
        }
        for cand in llm_res.candidates:
            key = (
                cand.get("excerpt"),
                cand.get("start_offset"),
                cand.get("end_offset"),
                cand.get("data_type"),
            )
            if key not in existing_keys:
                existing_keys.add(key)
                candidates.append(cand)
        if actor == "Codex-assisted candidate" and llm_res.candidates:
            actor = f"LLM-assisted candidate ({llm_extractor.config.model})"
            reason = "LLM-assisted candidate extraction with verbatim verification"
    now = datetime.now(timezone.utc).isoformat()
    document = PolicyDocument.model_validate(
        {
            "id": "policy-official",
            "source_type": "OFFICIAL_WEB_POLICY",
            "title": "Captured official policy",
            "version": version,
            "captured_at": now,
            "artifact": {"text": text, "sha256": digest(raw), "normalization": "NONE"},
            "completeness": "COMPLETE",
            "extraction_status": "PARTIAL",
            "review_status": "UNREVIEWED",
            "attachments_status": "NOT_CHECKED",
            "applicability": {
                "package_name": package,
                "version_codes": [] if version_code is None else [version_code],
                "regions": regions or [],
                "product_scope": product_scope,
            },
            "evidence_id": "policy-snapshot",
        }
    ).model_dump(mode="json")
    evidence = [
        {
            "id": "policy-snapshot",
            "kind": "POLICY_DOCUMENT",
            "status": "DECLARED",
            "source": source_url,
            "locator": "Full captured UTF-8 artifact",
            "document_id": document["id"],
            "artifact_sha256": digest(raw),
        }
    ]
    claims, audits = [], []
    for index, candidate in enumerate(candidates or [], 1):
        if not isinstance(candidate, dict):
            raise ValueError("Each candidate must be an object")
        allowed = {
            "excerpt",
            "start_offset",
            "end_offset",
            "data_type",
            "polarity",
            "condition",
            "subject",
            "action",
            "declared_purpose",
            "declared_recipient",
        }
        if set(candidate) - allowed:
            raise ValueError("Unsupported candidate fields")
        start, end = candidate.get("start_offset"), candidate.get("end_offset")
        if start is None and end is None:
            excerpt = candidate.get("excerpt", "")
            if not excerpt or text.count(excerpt) != 1:
                raise ValueError("Candidate excerpt must occur exactly once, or supply offsets")
            start, end = text.index(excerpt), text.index(excerpt) + len(excerpt)
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError("Invalid candidate codepoint span")
        excerpt = text[start:end]
        if candidate.get("excerpt", excerpt) != excerpt:
            raise ValueError("Candidate excerpt does not match span")
        ref = f"policy-sentence-{index}"
        evidence.append(
            {
                "id": ref,
                "kind": "POLICY_SENTENCE",
                "status": "DECLARED",
                "source": source_url,
                "locator": f"codepoints [{start},{end})",
                "excerpt": excerpt,
                "document_id": document["id"],
                "start_offset": start,
                "end_offset": end,
            }
        )
        value = {
            k: v for k, v in candidate.items() if k not in {"excerpt", "start_offset", "end_offset"}
        }
        # Unknown is intentional: intake does not assert host/affirmative interpretation.
        value.setdefault("action", "UNKNOWN")
        claim = PolicyClaim.model_validate(
            {
                **value,
                "id": f"policy-claim-{index}",
                "document_id": document["id"],
                "evidence_ids": [ref],
            }
        ).model_dump(mode="json")
        claims.append(claim)
        audits.append(
            {
                "claim_id": claim["id"],
                "old": None,
                "new": claim,
                "actor": actor,
                "reason": reason,
                "timestamp": now,
                "artifact_sha256": digest(raw),
                "evidence_ids": [ref],
                "authority": "UNAUTHENTICATED_INITIAL_CANDIDATE",
            }
        )
    out = Path(output_dir).absolute()
    if any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (out, *out.parents)
    ):
        raise ValueError("Symlink output directory is not allowed")
    if out.exists():
        raise ValueError("Capture output already exists; choose a new directory")
    audit_bytes = json.dumps(audits, ensure_ascii=False, indent=2).encode("utf-8")
    record = {
        "schema_version": 1,
        "document": document,
        "evidence": evidence,
        "claims": claims,
        "chunks": split_spans(text),
        "human_review_gate": TEAM_REVIEW_GATE,
        "files": {
            "raw": {"path": "policy.raw.txt", "sha256": digest(raw)},
            "processed": {"path": "policy.processed.txt", "sha256": digest(raw)},
            "audits": {"path": "policy.audits.json", "sha256": digest(audit_bytes)},
        },
    }
    validate_bundle(record)
    outputs = [
        ("policy.raw.txt", raw),
        ("policy.processed.txt", raw),
        ("policy.audits.json", audit_bytes),
        ("policy.capture.json", json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")),
    ]
    # Preflight the complete serialization before any output directory is created.
    for name, content in outputs:
        maximum = MAX_BYTES if name.endswith(".txt") else MAX_JSON_BYTES
        if len(content) > maximum:
            raise ValueError("Capture serialization exceeds the file byte limit")
    out.parent.mkdir(parents=True, exist_ok=True)
    parent = out.parent.resolve(strict=True)
    stage = parent / (".policy-capture-" + uuid4().hex)
    stage.mkdir()  # Only this invocation's new directory is eligible for cleanup.
    try:
        for name, content in outputs:
            with (stage / name).open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        # Validate actual on-disk bytes, references and audits before publication.
        load_policy(stage / "policy.capture.json")
        if out.exists() or out.is_symlink():
            raise ValueError("Capture output already exists; choose a new directory")
        stage.rename(out)  # Same-filesystem atomic directory publication.
    finally:
        if stage.exists():
            # No recursive deletion. Revalidate the resolved, privately-created directory
            # and remove only the four known files written above, never arbitrary children.
            if stage.is_symlink() or stage.resolve().parent != parent:
                raise ValueError("Unsafe capture staging cleanup path")
            for name, _ in outputs:
                child = stage / name
                if child.exists():
                    if child.is_symlink() or child.resolve().parent != stage.resolve():
                        raise ValueError("Unsafe capture staging file cleanup path")
                    child.unlink()
            stage.rmdir()
    return out / "policy.capture.json"


def validate_bundle(record):
    document = record["document"]
    EvaluationInput.model_validate(
        {
            "job": AnalysisJob(
                id="policy-validation",
                sample_id="policy-only",
                input_mode="APK",
                source_origin="CONTROLLED",
                state="POLICY_PARSING",
                ruleset_version=taxonomy()["version"],
                created_at=datetime.now(timezone.utc),
            ),
            "evidence": record["evidence"],
            "behaviors": [],
            "policy_documents": [document],
            "policy_claims": record["claims"],
        }
    )


def load_policy(path):
    """Untrusted capture boundary: fail without exposing source text or parser internals."""
    try:
        return _load_policy(path)
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        StopIteration,
        IndexError,
        RecursionError,
    ) as exc:
        raise ValueError("Policy capture failed validation") from exc


def _load_policy(path):
    path = Path(path).absolute()
    record = json.loads(read_safe(path))
    if (
        set(record)
        != {
            "schema_version",
            "document",
            "evidence",
            "claims",
            "chunks",
            "human_review_gate",
            "files",
        }
        or record["schema_version"] != 1
    ):
        raise ValueError("Unsupported policy capture schema")
    if record["human_review_gate"] not in {"PENDING_HUMAN_AB", TEAM_REVIEW_GATE}:
        raise ValueError("Offline capture cannot assert human review")
    blobs = {}
    if set(record["files"]) != {"raw", "processed", "audits"}:
        raise ValueError("Capture must retain raw, processed, and audit files")
    for name, info in record["files"].items():
        relative = Path(info["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Capture file path escapes directory")
        data = read_safe(
            path.parent / relative,
            path.parent,
            MAX_BYTES if name in {"raw", "processed"} else MAX_JSON_BYTES,
        )
        if digest(data) != info["sha256"]:
            raise ValueError("Captured file hash mismatch")
        blobs[name] = data
    text = blobs["processed"].decode("utf-8")
    if blobs["raw"] != blobs["processed"] or record["document"]["artifact"]["text"] != text:
        raise ValueError("Identity transform must preserve original bytes and text")
    if record["chunks"] != split_spans(text):
        raise ValueError("Lossless codepoint chunks do not match original")
    doc = record["document"]
    if (
        doc["review_status"] != "UNREVIEWED"
        or doc["extraction_status"] != "PARTIAL"
        or doc["attachments_status"] != "NOT_CHECKED"
        or doc["completeness"] != "COMPLETE"
    ):
        raise ValueError("Initial capture states cannot assert completed review or extraction")
    for item in record["evidence"]:
        parsed = urlparse(item["source"])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Policy source must be HTTPS without credentials")
    snapshot = next(item for item in record["evidence"] if item["id"] == doc["evidence_id"])
    if any(item["source"] != snapshot["source"] for item in record["evidence"]):
        raise ValueError("Initial capture evidence must use one source URL")
    validate_bundle(record)
    audits = json.loads(blobs["audits"])
    if len(audits) != len(record["claims"]):
        raise ValueError("Every initial claim requires an audit")
    for audit, claim in zip(audits, record["claims"], strict=True):
        timestamp = datetime.fromisoformat(audit["timestamp"])
        if (
            audit["old"] is not None
            or audit["new"] != claim
            or audit["claim_id"] != claim["id"]
            or audit["artifact_sha256"] != doc["artifact"]["sha256"]
            or audit["evidence_ids"] != claim["evidence_ids"]
            or not audit["actor"].strip()
            or not audit["reason"].strip()
            or timestamp.tzinfo is None
            or audit["authority"] != "UNAUTHENTICATED_INITIAL_CANDIDATE"
        ):
            raise ValueError("Initial claim audit does not match capture")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--package")
    parser.add_argument("--version-code", type=int)
    parser.add_argument("--product-scope")
    parser.add_argument("--region", action="append", default=[])
    parser.add_argument(
        "--enable-llm",
        action="store_true",
        help="Enable optional LLM-assisted policy claim extraction plugin",
    )
    parser.add_argument("--llm-model", default="gpt-4o-mini", help="LLM model name")
    parser.add_argument("--llm-cache-dir", type=Path, help="Cache directory for LLM extraction")
    parser.add_argument(
        "--llm-api-base", default="https://api.openai.com/v1", help="API base URL for LLM"
    )
    args = parser.parse_args()
    try:
        candidates = json.loads(read_safe(args.candidates)) if args.candidates else []
        if not isinstance(candidates, list):
            raise ValueError("Candidates must be a JSON list")
        llm_summary = None
        actor = "Codex-assisted candidate"
        reason = "Initial offline candidate capture"
        if args.enable_llm:
            from .policy_llm_extractor import LLMExtractorConfig, PolicyLLMExtractor
            config = LLMExtractorConfig(
                enabled=True,
                model=args.llm_model,
                cache_dir=args.llm_cache_dir,
            )
            llm_extractor = PolicyLLMExtractor(config)
            raw = read_safe(args.raw, max_bytes=MAX_BYTES)
            text = raw.decode("utf-8")
            spans = split_spans(text)
            llm_res = llm_extractor.extract_from_spans(text, spans)
            llm_summary = {
                "status": llm_res.status,
                "extracted_claims": len(llm_res.candidates),
                "rejected_claims": len(llm_res.rejected_candidates),
                "duration_ms": llm_res.telemetry.duration_ms,
                "cached": llm_res.telemetry.cached,
                "total_tokens": llm_res.telemetry.total_tokens,
            }
            existing_keys = {
                (c.get("excerpt"), c.get("start_offset"), c.get("end_offset"), c.get("data_type"))
                for c in candidates
            }
            for cand in llm_res.candidates:
                key = (
                    cand.get("excerpt"),
                    cand.get("start_offset"),
                    cand.get("end_offset"),
                    cand.get("data_type"),
                )
                if key not in existing_keys:
                    existing_keys.add(key)
                    candidates.append(cand)
            if llm_res.candidates:
                actor = f"LLM-assisted candidate ({args.llm_model})"
                reason = "LLM-assisted candidate extraction with verbatim verification"
        result = capture(
            args.raw,
            args.source_url,
            args.version,
            args.output_dir,
            candidates,
            args.package,
            args.version_code,
            args.product_scope,
            args.region,
            actor=actor,
            reason=reason,
        )
        out_summary = {
            "status": "CAPTURED_UNREVIEWED",
            "capture_path": str(result),
            "claims": len(candidates),
            "human_review_gate": TEAM_REVIEW_GATE,
        }
        if llm_summary is not None:
            out_summary["llm_extraction"] = llm_summary
        print(json.dumps(out_summary))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(
            json.dumps(
                {
                    "errors": [
                        {
                            "code": "POLICY_INPUT_INVALID",
                            "message": "Policy capture input failed validation",
                        }
                    ]
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
