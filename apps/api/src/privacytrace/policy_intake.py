"""Offline, lossless policy capture. Candidates are not human verification."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from .models import AnalysisJob, EvaluationInput, PolicyClaim, PolicyDocument
from .resources import taxonomy

TEAM_REVIEW_GATE = "NOT_REQUIRED_BY_WORKFLOW"

MAX_BYTES = 800000
MAX_JSON_BYTES = 32 * 1024 * 1024


def parse_bool_env(env_var_name: str, default: bool = False) -> bool:
    val = os.environ.get(env_var_name)
    if val is None:
        return default
    val_clean = val.strip().lower()
    if val_clean in {"1", "true", "yes", "on", "t"}:
        return True
    if val_clean in {"0", "false", "no", "off", "f", ""}:
        return False
    raise ValueError(f"Invalid boolean value for environment variable {env_var_name}: {val!r}")


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


# Untrusted candidate JSON must never specify provenance; internal callers use
# a separate, trusted candidate_provenance mapping indexed by candidate position.
CANDIDATE_FIELDS = {
    "excerpt", "start_offset", "end_offset", "data_type", "polarity",
    "condition", "subject", "action", "declared_purpose",
    "declared_recipient", "ambiguity_flags",
}


def preflight_capture(raw_path, source_url, output_dir, candidates=None):
    """Reject invalid work before any optional external LLM request."""
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Policy source must be HTTPS without credentials")
    raw = read_safe(raw_path, max_bytes=MAX_BYTES)
    text = raw.decode("utf-8")
    if not text or len(text) > 200000:
        raise ValueError("Policy text must contain 1 to 200000 Unicode codepoints")
    out = Path(output_dir).absolute()
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
           for p in (out, *out.parents)):
        raise ValueError("Symlink output directory is not allowed")
    if out.exists():
        raise ValueError("Capture output already exists; choose a new directory")
    if candidates is not None:
        if not isinstance(candidates, list):
            raise ValueError("Candidates must be a JSON list")
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("Each candidate must be an object")
            if set(candidate) - CANDIDATE_FIELDS:
                raise ValueError("Unsupported candidate fields")
            start, end = candidate.get("start_offset"), candidate.get("end_offset")
            if start is None and end is None:
                excerpt = candidate.get("excerpt", "")
                if not isinstance(excerpt, str) or not excerpt or text.count(excerpt) != 1:
                    raise ValueError("Candidate excerpt must occur exactly once, or supply offsets")
                start = text.index(excerpt)
                end = start + len(excerpt)
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                raise ValueError("Invalid candidate codepoint span")
            if candidate.get("excerpt", text[start:end]) != text[start:end]:
                raise ValueError("Candidate excerpt does not match span")
            PolicyClaim.model_validate({
                **{k: v for k, v in candidate.items()
                   if k not in {"excerpt", "start_offset", "end_offset"}},
                "id": "preflight-claim",
                "document_id": "policy-official",
                "evidence_ids": ["preflight-evidence"],
            })
    return raw, text


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
    candidate_provenance=None,
):
    raw, text = preflight_capture(raw_path, source_url, output_dir, candidates)
    sources = dict(candidate_provenance or {})
    if llm_extractor is not None and getattr(llm_extractor.config, "enabled", False):
        spans = split_spans(text)
        llm_res = llm_extractor.extract_from_spans(text, spans)
        candidates = list(candidates or [])
        existing_keys = set()
        for c in candidates:
            if not isinstance(c, dict):
                continue
            existing_keys.add(
                (c.get("excerpt"), c.get("start_offset"), c.get("end_offset"), c.get("data_type"))
            )
            if c.get("start_offset") is None and c.get("end_offset") is None:
                existing_keys.add((c.get("excerpt"), c.get("data_type")))

        for cand in llm_res.candidates:
            key_with_offsets = (
                cand.get("excerpt"),
                cand.get("start_offset"),
                cand.get("end_offset"),
                cand.get("data_type"),
            )
            key_by_excerpt = (cand.get("excerpt"), cand.get("data_type"))
            if key_with_offsets in existing_keys or key_by_excerpt in existing_keys:
                for position, existing in enumerate(candidates):
                    if (existing.get("excerpt"), existing.get("data_type")) == key_by_excerpt:
                        if existing.get("polarity", "UNKNOWN") != cand.get("polarity", "UNKNOWN"):
                            old_actor, old_reason = sources.get(position, (actor, reason))
                            sources[position] = (
                                old_actor,
                                old_reason + "; conflicting LLM polarity requires human review",
                            )
                        break
                continue
            if key_with_offsets not in existing_keys and key_by_excerpt not in existing_keys:
                existing_keys.add(key_with_offsets)
                sources[len(candidates)] = (
                    f"LLM-assisted candidate ({llm_extractor.config.model})",
                    "LLM-assisted candidate extraction with verbatim verification",
                )
                candidates.append(dict(cand))
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
        if set(candidate) - CANDIDATE_FIELDS:
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
            k: v
            for k, v in candidate.items()
            if k not in {"excerpt", "start_offset", "end_offset"}
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
        cand_actor, cand_reason = sources.get(index - 1, (actor, reason))
        audits.append(
            {
                "claim_id": claim["id"],
                "old": None,
                "new": claim,
                "actor": cand_actor,
                "reason": cand_reason,
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


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default handler echoes rejected command-line values,
        # which may contain secrets mistakenly passed as --llm-api-key.
        self.print_usage(sys.stderr)
        self.exit(2, "error: invalid command-line arguments\n")


def main():
    parser = _SafeArgumentParser(description=__doc__)
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
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable optional LLM-assisted policy claim extraction plugin",
    )
    parser.add_argument(
        "--llm-model",
        default=os.environ.get("PRIVACYTRACE_LLM_MODEL", "gpt-4o-mini"),
        help="LLM model name",
    )
    parser.add_argument(
        "--llm-cache-dir",
        type=Path,
        default=Path(os.environ["PRIVACYTRACE_LLM_CACHE_DIR"])
        if "PRIVACYTRACE_LLM_CACHE_DIR" in os.environ
        else None,
        help="Cache directory for LLM extraction",
    )
    parser.add_argument(
        "--llm-api-base",
        default=os.environ.get("PRIVACYTRACE_LLM_API_BASE", "https://api.openai.com/v1"),
        help="API base URL for LLM",
    )
    parser.add_argument("--llm-max-spans", type=int, default=64)
    parser.add_argument("--llm-max-requests", type=int, default=96)
    parser.add_argument("--llm-max-elapsed-seconds", type=float, default=120.0)
    args = parser.parse_args()
    try:
        candidates = json.loads(read_safe(args.candidates)) if args.candidates else []
        if not isinstance(candidates, list):
            raise ValueError("Candidates must be a JSON list")
        # Validate user input and publication destination before external calls.
        preflight_capture(args.raw, args.source_url, args.output_dir, candidates)
        llm_summary = None
        source_overrides = {}
        actor = "Codex-assisted candidate"
        reason = "Initial offline candidate capture"
        if args.enable_llm is not None:
            llm_enabled = args.enable_llm
        else:
            llm_enabled = parse_bool_env("PRIVACYTRACE_LLM_ENABLED", default=False)
        if llm_enabled:
            from .policy_llm_extractor import LLMExtractorConfig, PolicyLLMExtractor

            config = LLMExtractorConfig(
                enabled=True,
                model=args.llm_model,
                api_base=args.llm_api_base,
                cache_dir=args.llm_cache_dir,
                max_spans=args.llm_max_spans,
                max_requests=args.llm_max_requests,
                max_elapsed_seconds=args.llm_max_elapsed_seconds,
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
                "failed_spans": len(llm_res.telemetry.failed_spans),
                "skipped_spans": len(llm_res.telemetry.skipped_spans),
                "duration_ms": llm_res.telemetry.duration_ms,
                "cached": llm_res.telemetry.cached,
                "total_tokens": llm_res.telemetry.total_tokens,
            }
            if llm_res.telemetry.failed_spans:
                llm_summary["failed_span_details"] = [
                    {
                        "start": s["start"],
                        "end": s["end"],
                        "errors": s["errors"],
                    }
                    for s in llm_res.telemetry.failed_spans
                ]
            if llm_res.telemetry.skipped_spans:
                llm_summary["skipped_span_details"] = list(llm_res.telemetry.skipped_spans)
            existing_keys = set()
            for c in candidates:
                existing_keys.add(
                    (
                        c.get("excerpt"),
                        c.get("start_offset"),
                        c.get("end_offset"),
                        c.get("data_type"),
                    )
                )
                if c.get("start_offset") is None and c.get("end_offset") is None:
                    existing_keys.add((c.get("excerpt"), c.get("data_type")))

            llm_summary["conflicting_candidates"] = []
            for cand in llm_res.candidates:
                key_with_offsets = (
                    cand.get("excerpt"),
                    cand.get("start_offset"),
                    cand.get("end_offset"),
                    cand.get("data_type"),
                )
                key_by_excerpt = (cand.get("excerpt"), cand.get("data_type"))
                if key_with_offsets in existing_keys or key_by_excerpt in existing_keys:
                    for position, existing in enumerate(candidates):
                        if (existing.get("excerpt"), existing.get("data_type")) == key_by_excerpt:
                            old_polarity = existing.get("polarity", "UNKNOWN")
                            new_polarity = cand.get("polarity", "UNKNOWN")
                            if old_polarity != new_polarity:
                                llm_summary["conflicting_candidates"].append({
                                    "candidate_index": position + 1,
                                    "data_type": cand.get("data_type"),
                                    "existing_polarity": old_polarity,
                                    "llm_polarity": new_polarity,
                                    "requires_human_review": True,
                                })
                                old_actor, old_reason = source_overrides.get(
                                    position, (actor, reason)
                                )
                                source_overrides[position] = (
                                    old_actor,
                                    old_reason + "; conflicting LLM polarity requires human review",
                                )
                            break
                    continue
                if key_with_offsets not in existing_keys and key_by_excerpt not in existing_keys:
                    existing_keys.add(key_with_offsets)
                    source_overrides[len(candidates)] = (
                        f"LLM-assisted candidate ({args.llm_model})",
                        "LLM-assisted candidate extraction with verbatim verification",
                    )
                    candidates.append(dict(cand))
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
            candidate_provenance=source_overrides,
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
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
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
