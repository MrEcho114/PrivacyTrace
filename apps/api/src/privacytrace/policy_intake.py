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


def preflight_capture(raw_path, source_url, output_dir, candidates=None, *,
                      version="preflight", package=None, version_code=None,
                      product_scope=None, regions=None):
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
    _build_document(
        raw, text, version, package, version_code, product_scope, regions,
        datetime.now(timezone.utc).isoformat(),
    )
    if candidates is not None:
        if not isinstance(candidates, list):
            raise ValueError("Candidates must be a JSON list")
        if len(candidates) > 1999:
            raise ValueError("Policy capture cannot exceed 1999 candidates")
        valid_data_types = {item["id"] for item in taxonomy()["data_types"]}
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("Each candidate must be an object")
            if set(candidate) - CANDIDATE_FIELDS:
                raise ValueError("Unsupported candidate fields")
            data_type = candidate.get("data_type")
            if not isinstance(data_type, str) or data_type not in valid_data_types:
                raise ValueError("Candidate data_type is not in the active taxonomy")
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



def _build_document(raw, text, version, package, version_code,
                    product_scope, regions, now):
    return PolicyDocument.model_validate(
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


# Candidate deduplication requires *semantic* equality, not merely matching evidence.
_SEMANTIC_FIELDS = (
    "polarity", "subject", "action", "condition",
    "declared_purpose", "declared_recipient", "ambiguity_flags",
)
_DEFAULT_SEMANTICS = {"polarity": "UNKNOWN", "subject": "UNKNOWN", "action": "UNKNOWN"}


def _candidate_identity(candidate, text):
    excerpt = candidate.get("excerpt")
    start, end = candidate.get("start_offset"), candidate.get("end_offset")
    if start is None and end is None:
        start = text.index(excerpt)  # The preflight has established uniqueness.
        end = start + len(excerpt)
    evidence = (start, end, candidate["data_type"])
    semantics = tuple(
        tuple(sorted(candidate.get(name) or [])) if name == "ambiguity_flags"
        else candidate.get(name, _DEFAULT_SEMANTICS.get(name))
        for name in _SEMANTIC_FIELDS
    )
    return evidence, semantics


def merge_llm_candidates(text, manual_candidates, llm_candidates, model,
                         actor="Codex-assisted candidate",
                         reason="Initial offline candidate capture",
                         max_claims=1999):
    """Keep distinct meanings and stable, trusted audit provenance."""
    candidates = [dict(item) for item in manual_candidates]
    sources = {}
    conflicts = []
    dropped = 0
    known = {}
    for index, candidate in enumerate(candidates):
        evidence, semantics = _candidate_identity(candidate, text)
        known.setdefault(evidence, []).append((semantics, index))
    for cand in llm_candidates:
        evidence, semantics = _candidate_identity(cand, text)
        matching = known.get(evidence, [])
        if any(previous == semantics for previous, _ in matching):
            continue
        if len(candidates) >= max_claims:
            dropped += 1
            continue
        new_index = len(candidates)
        candidates.append(dict(cand))
        sources[new_index] = (
            f"LLM-assisted candidate ({model})",
            "LLM-assisted candidate extraction with verbatim verification",
        )
        for existing_semantics, existing_index in matching:
            fields = [
                name for name, before, after in zip(
                    _SEMANTIC_FIELDS, existing_semantics, semantics, strict=True
                ) if before != after
            ]
            conflicts.append({
                "candidate_index": existing_index + 1,
                "other_candidate_index": new_index + 1,
                "fields": fields,
                "existing_polarity": existing_semantics[0],
                "llm_polarity": semantics[0],
                "requires_human_review": True,
            })
            old_actor, old_reason = sources.get(existing_index, (actor, reason))
            marker = "; conflicting LLM candidate requires human review"
            if marker not in old_reason:
                sources[existing_index] = (old_actor, old_reason + marker)
        known.setdefault(evidence, []).append((semantics, new_index))
    return candidates, sources, conflicts, dropped



# Audit schema v1 belongs to the optional v2 capture bundle.
_LLM_AUDIT_FIELDS = {
    "schema_version", "status", "model", "prompt_version", "ruleset_version",
    "prompt_sha256", "endpoint_identifier", "document_sha256", "duration_ms",
    "attempts", "prompt_tokens", "completion_tokens", "total_tokens",
    "cached_spans", "processed_spans", "failed_spans", "skipped_spans",
    "rejected_count", "extracted_candidates", "limited_candidates",
    "candidate_conflicts", "requires_human_review",
}
_LLM_FAILURE_CODES = {
    "TIME_BUDGET_EXHAUSTED", "REQUEST_BUDGET_EXHAUSTED",
    "SPAN_BUDGET_EXHAUSTED", "CANDIDATE_CAP_REACHED",
    "RESPONSE_TOO_LARGE", "CANDIDATE_RESPONSE_LIMIT",
    "LLM_TIMEOUT", "INVALID_LLM_RESPONSE", "LLM_REQUEST_FAILED",
}


def _error_code(errors):
    # A later budget failure must not overwrite the actual request failure.
    # Never persist arbitrary server-supplied error strings in an audit.
    message = " ".join(str(e) for e in errors)
    for code in (
        "RESPONSE_TOO_LARGE", "CANDIDATE_RESPONSE_LIMIT", "LLM_TIMEOUT",
        "INVALID_LLM_RESPONSE", "LLM_REQUEST_FAILED",
    ):
        if code in message:
            return code
    for code in sorted(_LLM_FAILURE_CODES):
        if code in message:
            return code
    return "LLM_REQUEST_FAILED"


def build_llm_execution(result, config, raw, conflicts):
    from .policy_llm_extractor import SYSTEM_PROMPT

    telemetry = result.telemetry
    return {
        "schema_version": 1,
        "status": result.status,
        "model": config.model,
        "prompt_version": config.prompt_version,
        "ruleset_version": config.ruleset_version,
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "endpoint_identifier": hashlib.sha256(config.api_base.encode("utf-8")).hexdigest(),
        "document_sha256": digest(raw),
        "duration_ms": telemetry.duration_ms,
        "attempts": telemetry.attempts,
        "prompt_tokens": telemetry.prompt_tokens,
        "completion_tokens": telemetry.completion_tokens,
        "total_tokens": telemetry.total_tokens,
        "cached_spans": telemetry.cached_spans,
        "processed_spans": telemetry.processed_spans,
        "failed_spans": [
            {"start": span["start"], "end": span["end"],
             "code": _error_code(span.get("errors", []))}
            for span in telemetry.failed_spans
        ],
        "skipped_spans": [
            {"start": span["start"], "end": span["end"],
             "code": span["reason"] if span.get("reason") in _LLM_FAILURE_CODES
             else "LLM_REQUEST_FAILED"}
            for span in telemetry.skipped_spans
        ],
        "rejected_count": telemetry.rejected_count,
        "extracted_candidates": len(result.candidates),
        "limited_candidates": telemetry.limited_candidates,
        "candidate_conflicts": conflicts,
        "requires_human_review": True,
    }


def _validate_llm_execution(entry, document, claims):
    if not isinstance(entry, dict) or set(entry) != _LLM_AUDIT_FIELDS:
        raise ValueError("Invalid LLM execution audit fields")
    if entry["schema_version"] != 1 or entry["status"] not in {
        "SUCCESS", "PARTIAL", "FAILED", "DISABLED"
    }:
        raise ValueError("Invalid LLM execution audit version or status")
    for name in ("model", "prompt_version", "ruleset_version"):
        if not isinstance(entry[name], str) or not 0 < len(entry[name]) <= 256:
            raise ValueError("Invalid LLM execution version identifier")
    for name in ("prompt_sha256", "endpoint_identifier", "document_sha256"):
        value = entry[name]
        if not isinstance(value, str) or len(value) != 64 or any(
            digit not in "0123456789abcdef" for digit in value
        ):
            raise ValueError("Invalid LLM audit digest")
    if entry["document_sha256"] != document["artifact"]["sha256"]:
        raise ValueError("LLM audit document digest mismatch")
    for name in (
        "duration_ms", "attempts", "prompt_tokens", "completion_tokens",
        "total_tokens", "cached_spans", "processed_spans",
        "rejected_count", "extracted_candidates", "limited_candidates",
    ):
        if type(entry[name]) is not int or entry[name] < 0:
            raise ValueError("Invalid LLM audit numeric field")
    if entry["total_tokens"] < max(entry["prompt_tokens"], entry["completion_tokens"]):
        raise ValueError("Invalid LLM token counts")
    if entry["cached_spans"] > entry["processed_spans"]:
        raise ValueError("Invalid LLM cached span count")
    if entry["requires_human_review"] is not True:
        raise ValueError("LLM claims must remain unreviewed")
    length = len(document["artifact"]["text"])
    for field in ("failed_spans", "skipped_spans"):
        spans = entry[field]
        if not isinstance(spans, list) or len(spans) > length:
            raise ValueError("Invalid LLM span list")
        for span in spans:
            if not isinstance(span, dict) or set(span) != {"start", "end", "code"}:
                raise ValueError("Invalid LLM failure record")
            if (
                type(span["start"]) is not int or type(span["end"]) is not int
                or not 0 <= span["start"] < span["end"] <= length
                or span["code"] not in _LLM_FAILURE_CODES
            ):
                raise ValueError("Invalid LLM span or failure code")
    if not isinstance(entry["candidate_conflicts"], list):
        raise ValueError("Invalid LLM candidate conflicts")
    for conflict in entry["candidate_conflicts"]:
        if not isinstance(conflict, dict) or set(conflict) != {
            "candidate_index", "other_candidate_index", "fields",
            "existing_polarity", "llm_polarity", "requires_human_review",
        }:
            raise ValueError("Invalid candidate conflict fields")
        if (
            type(conflict["candidate_index"]) is not int
            or type(conflict["other_candidate_index"]) is not int
            or not 1 <= conflict["candidate_index"] <= len(claims)
            or not 1 <= conflict["other_candidate_index"] <= len(claims)
            or conflict["candidate_index"] == conflict["other_candidate_index"]
            or conflict["requires_human_review"] is not True
            or not isinstance(conflict["fields"], list)
            or not conflict["fields"]
            or any(field not in _SEMANTIC_FIELDS for field in conflict["fields"])
            or conflict["existing_polarity"] not in {"AFFIRMATIVE", "NEGATIVE", "UNKNOWN"}
            or conflict["llm_polarity"] not in {"AFFIRMATIVE", "NEGATIVE", "UNKNOWN"}
        ):
            raise ValueError("Invalid candidate conflict content")


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
    llm_result=None,
    llm_config=None,
    candidate_conflicts=None,
):
    raw, text = preflight_capture(
        raw_path, source_url, output_dir, candidates, version=version,
        package=package, version_code=version_code,
        product_scope=product_scope, regions=regions,
    )
    sources = dict(candidate_provenance or {})
    conflicts = list(candidate_conflicts or [])
    dropped_candidates = 0
    if llm_extractor is not None and getattr(llm_extractor.config, "enabled", False):
        llm_config = llm_extractor.config
        llm_result = llm_extractor.extract_from_spans(
            text, split_spans(text),
            max_candidate_budget=max(0, 1999 - len(candidates or [])),
            existing_candidates=candidates or [],
        )
        candidates, sources, conflicts, dropped_candidates = merge_llm_candidates(
            text, candidates or [], llm_result.candidates, llm_config.model, actor, reason
        )
    if llm_result is not None and llm_config is None:
        raise ValueError("LLM execution result requires its configuration")
    if dropped_candidates:
        llm_result.telemetry.limited_candidates += dropped_candidates
        llm_result.status = "PARTIAL"
    now = datetime.now(timezone.utc).isoformat()
    document = _build_document(
        raw, text, version, package, version_code, product_scope, regions, now
    )
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
    execution_bytes = None
    if llm_result is not None:
        execution = build_llm_execution(
            llm_result, llm_config, raw, conflicts
        )
        _validate_llm_execution(execution, document, claims)
        execution_bytes = json.dumps(
            execution, ensure_ascii=False, indent=2
        ).encode("utf-8")
        record["schema_version"] = 2
        record["files"]["llm_execution"] = {
            "path": "policy.llm-execution.json",
            "sha256": digest(execution_bytes),
        }
    outputs = [
        ("policy.raw.txt", raw),
        ("policy.processed.txt", raw),
        ("policy.audits.json", audit_bytes),
        ("policy.capture.json", json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")),
    ]
    if execution_bytes is not None:
        outputs.append(("policy.llm-execution.json", execution_bytes))
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
        or type(record["schema_version"]) is not int
        or record["schema_version"] not in {1, 2}
    ):
        raise ValueError("Unsupported policy capture schema")
    if record["human_review_gate"] not in {"PENDING_HUMAN_AB", TEAM_REVIEW_GATE}:
        raise ValueError("Offline capture cannot assert human review")
    blobs = {}
    allowed_files = {"raw", "processed", "audits"}
    if record["schema_version"] == 2:
        allowed_files.add("llm_execution")
    if set(record["files"]) != allowed_files:
        raise ValueError("Capture has invalid file manifest for schema version")
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
    if record["schema_version"] == 2:
        _validate_llm_execution(
            json.loads(blobs["llm_execution"]), doc, record["claims"]
        )
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
    parser.add_argument("--llm-max-output-tokens", type=int, default=2048)
    parser.add_argument("--llm-max-response-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--llm-max-candidates-per-response", type=int, default=100)
    args = parser.parse_args()
    try:
        candidates = json.loads(read_safe(args.candidates)) if args.candidates else []
        if not isinstance(candidates, list):
            raise ValueError("Candidates must be a JSON list")
        # Validate user input and publication destination before external calls.
        preflight_capture(
            args.raw, args.source_url, args.output_dir, candidates,
            version=args.version, package=args.package,
            version_code=args.version_code, product_scope=args.product_scope,
            regions=args.region,
        )
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
                max_output_tokens=args.llm_max_output_tokens,
                max_response_bytes=args.llm_max_response_bytes,
                max_candidates_per_response=args.llm_max_candidates_per_response,
            )
            llm_extractor = PolicyLLMExtractor(config)
            raw = read_safe(args.raw, max_bytes=MAX_BYTES)
            text = raw.decode("utf-8")
            spans = split_spans(text)
            llm_res = llm_extractor.extract_from_spans(
                text, spans, max_candidate_budget=max(0, 1999 - len(candidates)),
                existing_candidates=candidates,
            )
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
            # One shared semantic merge implementation for CLI and API entrypoints.
            candidates, source_overrides, candidate_conflicts, dropped_candidates = (
                merge_llm_candidates(
                    text, candidates, llm_res.candidates, config.model, actor, reason
                )
            )
            if dropped_candidates:
                llm_res.telemetry.limited_candidates += dropped_candidates
                llm_res.status = "PARTIAL"
            llm_summary["conflicting_candidates"] = candidate_conflicts
            llm_summary["status"] = llm_res.status
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
            llm_result=llm_res if llm_enabled else None,
            llm_config=config if llm_enabled else None,
            candidate_conflicts=candidate_conflicts if llm_enabled else None,
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
