"""Read-only persistent-state observation with one-way aliases.

Executed inside the owned API container with the runtime's normal RLS
transaction. It never writes, never exports job/scope ids, capability tokens or
raw material references; report content hashes are one-way evidence only.
"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from privacytrace.storage_factory import create_store


def alias(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def journal_snapshot():
    base = Path(os.environ.get("PRIVACYTRACE_DELETION_JOURNAL_ROOT", ""))
    path = base / store.instance_id / "deletions.jsonl"
    entries, error = [], None
    if path.is_file():
        try:
            lines = path.read_bytes().splitlines()
            for line in lines[-64:]:
                value = json.loads(line)
                entries.append(
                    {
                        "sequence": value.get("sequence"),
                        "kind": value.get("kind"),
                        "scope_alias": alias(str(value.get("scope_id", ""))),
                        "at": value.get("at"),
                    }
                )
        except (ValueError, OSError) as exc:
            error = type(exc).__name__
    return {"path_present": path.is_file(), "entries_tail": entries, "error": error}


def draft_dir_snapshot(web_root, draft_id):
    directory = web_root / draft_id
    snapshot = {"exists": directory.is_dir(), "files": [], "file_count": 0}
    if not snapshot["exists"]:
        return snapshot
    names = []
    for item in sorted(directory.rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(directory).as_posix()
        relative = re.sub(
            r"(run-)([a-f0-9]{32})(\.json)",
            lambda match: match.group(1) + alias(match.group(2)) + match.group(3),
            relative,
        )
        names.append(relative)
    snapshot.update({"files": names, "file_count": len(names)})
    return snapshot


store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
try:
    with store._transaction() as connection:
        parameters = {"instance": store.instance_id}
        jobs = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT j.job_id, j.record->'job'->>'state' AS state,
                        j.record->'job'->>'retry_of' AS retry_of,
                        j.record->'job'->'error' AS error,
                        (j.record->'bundle' IS NOT NULL
                         AND j.record->'bundle' <> 'null'::jsonb) AS has_report,
                        e.state AS execution_state, e.fence, e.attempt,
                        e.last_error_code, e.result_sha256,
                        (e.owner IS NOT NULL) AS has_owner
                    FROM privacytrace.jobs j
                    LEFT JOIN privacytrace.job_executions e USING(instance_id,job_id)
                    WHERE j.instance_id=:instance ORDER BY j.job_id
                """),
                parameters,
            ).mappings()
        ]
        scopes = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT scope_id, kind, tombstone,
                        (token_digest IS NOT NULL) AS has_token_digest
                    FROM privacytrace.analysis_scopes
                    WHERE instance_id=:instance ORDER BY created_at
                """),
                parameters,
            ).mappings()
        ]
        outbox = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT job_id, event_id, state, attempts, last_error_code,
                        (delivered_at IS NOT NULL) AS delivered
                    FROM privacytrace.outbox_events
                    WHERE instance_id=:instance ORDER BY created_at
                """),
                parameters,
            ).mappings()
        ]
        audit = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT scope_id, action, count(*) AS count,
                        min(created_at) AS first_at, max(created_at) AS last_at
                    FROM privacytrace.audit_events
                    WHERE instance_id=:instance GROUP BY scope_id, action
                    ORDER BY scope_id, action
                """),
                parameters,
            ).mappings()
        ]
        documents = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT scope_id, count(*) AS count,
                        coalesce(sum(byte_count), 0) AS bytes
                    FROM privacytrace.intake_documents
                    WHERE instance_id=:instance GROUP BY scope_id
                """),
                parameters,
            ).mappings()
        ]
        document_files = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT document_key, material_ref, byte_count
                    FROM privacytrace.intake_documents
                    WHERE instance_id=:instance
                """),
                parameters,
            ).mappings()
        ]
        runtime_inputs = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT job_id, draft_id, document_key
                    FROM privacytrace.runtime_inputs WHERE instance_id=:instance
                """),
                parameters,
            ).mappings()
        ]
        runner_materials = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT scope_id, draft_id, count(*) AS count, mode
                    FROM privacytrace.runner_materials
                    WHERE instance_id=:instance GROUP BY scope_id, draft_id, mode
                """),
                parameters,
            ).mappings()
        ]
        uploads = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT draft_id, (expires_at > clock_timestamp()) AS live
                    FROM privacytrace.upload_reservations WHERE instance_id=:instance
                """),
                parameters,
            ).mappings()
        ]
        deletions = [
            dict(row)
            for row in connection.execute(
                sa.text("""
                    SELECT kind, scope_id, sequence
                    FROM privacytrace.deletion_intents WHERE instance_id=:instance
                    ORDER BY sequence
                """),
                parameters,
            ).mappings()
        ]

        web_root = store.root / "web"
        objects = web_root / ".objects"
        object_count = 0
        object_bytes = 0
        object_names = set()
        if objects.is_dir():
            for item in objects.iterdir():
                if item.is_file():
                    object_count += 1
                    object_bytes += item.stat().st_size
                    object_names.add(item.name)

        reports = []
        for job in jobs:
            if not job["has_report"]:
                continue
            try:
                report = store.report(job["job_id"])
            except (KeyError, ValueError, OSError) as exc:
                reports.append({"job_alias": alias(job["job_id"]), "error": type(exc).__name__})
                continue
            core = report.model_dump(mode="json", exclude={"reviews"})
            encoded = json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode()
            receipts = report.tools.get("runner_receipt") if report.tools else None
            reports.append(
                {
                    "job_alias": alias(job["job_id"]),
                    "report_content_sha256": hashlib.sha256(encoded).hexdigest(),
                    "evidence_count": len(report.evidence),
                    "behavior_count": len(report.behaviors),
                    "issue_count": len(report.result.issues),
                    "apk_sha256": report.sample.apk_sha256,
                    "delivery_mode": report.delivery_mode.value,
                    "has_runner_receipt": bool(receipts),
                }
            )

        drafts = {}
        for scope in scopes:
            if scope["kind"] == "DRAFT":
                drafts[alias(scope["scope_id"])] = draft_dir_snapshot(web_root, scope["scope_id"])

        def clean(value):
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            return value

        result = {
            "jobs": [
                {
                    "job_alias": alias(job["job_id"]),
                    "state": job["state"],
                    "retry_of_alias": alias(job["retry_of"]) if job["retry_of"] else None,
                    "error_code": (json.loads(job["error"]) or {}).get("code")
                    if isinstance(job["error"], str)
                    else (job["error"] or {}).get("code")
                    if isinstance(job["error"], dict)
                    else None,
                    "has_report": bool(job["has_report"]),
                    "execution_state": job["execution_state"],
                    "fence": job["fence"],
                    "attempt": job["attempt"],
                    "execution_error_code": job["last_error_code"],
                    "result_sha256": job["result_sha256"],
                }
                for job in jobs
            ],
            "scopes": [
                {
                    "scope_alias": alias(scope["scope_id"]),
                    "kind": scope["kind"],
                    "tombstone": bool(scope["tombstone"]),
                    "has_token_digest": bool(scope["has_token_digest"]),
                }
                for scope in scopes
            ],
            "outbox": [
                {
                    "job_alias": alias(item["job_id"]),
                    "event_alias": alias(str(item["event_id"])),
                    "state": item["state"],
                    "attempts": item["attempts"],
                    "error_code": item["last_error_code"],
                    "delivered": bool(item["delivered"]),
                }
                for item in outbox
            ],
            "audit": [
                {
                    "scope_alias": alias(item["scope_id"]),
                    "action": item["action"],
                    "count": item["count"],
                    "first_at": iso(item["first_at"]),
                    "last_at": iso(item["last_at"]),
                }
                for item in audit
            ],
            "documents": [
                {
                    "scope_alias": alias(item["scope_id"]) if item["scope_id"] else None,
                    "count": item["count"],
                    "bytes": item["bytes"],
                }
                for item in documents
            ],
            "runtime_inputs": [
                {
                    "job_alias": alias(item["job_id"]),
                    "draft_alias": alias(item["draft_id"]),
                    "document_key": re.sub(
                        r"([a-f0-9]{32})/",
                        lambda match: alias(match.group(1)) + "/",
                        item["document_key"],
                    ),
                }
                for item in runtime_inputs
            ],
            "runner_materials": [
                {
                    "scope_alias": alias(item["scope_id"]),
                    "draft_alias": alias(item["draft_id"]),
                    "mode": item["mode"],
                    "count": item["count"],
                }
                for item in runner_materials
            ],
            "uploads": [
                {"draft_alias": alias(item["draft_id"]), "live": bool(item["live"])}
                for item in uploads
            ],
            "deletions": [
                {
                    "kind": item["kind"],
                    "scope_alias": alias(item["scope_id"]),
                    "sequence": item["sequence"],
                }
                for item in deletions
            ],
            "journal": journal_snapshot(),
            "objects": {
                "count": object_count,
                "bytes": object_bytes,
                "referenced_missing": sum(
                    1 for item in document_files if item["material_ref"] not in object_names
                ),
            },
            "drafts": drafts,
            "reports": reports,
            "counts": {
                name: connection.execute(
                    sa.text(
                        "SELECT count(*) FROM privacytrace." + name + " WHERE instance_id=:instance"
                    ),
                    parameters,
                ).scalar()
                for name in (
                    "intake_documents",
                    "outbox_events",
                    "runner_materials",
                    "deletion_intents",
                    "upload_reservations",
                    "runtime_inputs",
                    "analysis_scopes",
                    "jobs",
                )
            },
            "material_files": sum(1 for item in store.root.rglob("*") if item.is_file()),
        }
        print(json.dumps(clean(result), default=str, sort_keys=True))
finally:
    store.close()
