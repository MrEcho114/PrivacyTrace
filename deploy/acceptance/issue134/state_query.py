"""Read-only persistent-state observation; the output belongs in private storage."""

import hashlib
import json
import os
from pathlib import Path

import sqlalchemy as sa
from privacytrace.storage_factory import create_store

store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
try:
    with store._transaction() as connection:
        params = {"instance": store.instance_id}
        result = {}
        for name, query in {
            "jobs": "SELECT j.job_id,j.record->'job'->>'state' AS state, "
            "j.record->'bundle' IS NOT NULL AND j.record->'bundle'<>'null'::jsonb AS has_report, "
            "e.state AS execution_state,e.fence,e.attempt "
            "FROM privacytrace.jobs j LEFT JOIN privacytrace.job_executions e "
            "USING(instance_id,job_id) WHERE j.instance_id=:instance ORDER BY j.job_id",
            "outbox": "SELECT event_id,job_id,state,attempts FROM privacytrace.outbox_events "
            "WHERE instance_id=:instance ORDER BY created_at",
            "scopes": "SELECT scope_id,kind,tombstone FROM privacytrace.analysis_scopes "
            "WHERE instance_id=:instance ORDER BY created_at",
        }.items():
            result[name] = [
                dict(row) for row in connection.execute(sa.text(query), params).mappings()
            ]
        result["counts"] = {
            name: connection.scalar(
                sa.text(
                    "SELECT count(*) FROM privacytrace." + name + " WHERE instance_id=:instance"
                ),
                params,
            )
            for name in (
                "intake_documents",
                "runner_materials",
                "runtime_inputs",
                "upload_reservations",
            )
        }
        result["source"] = "INTERNAL_OBSERVER_NOT_ANDROID"
        result["reports"] = []
        for job in result["jobs"]:
            if not job["has_report"]:
                continue
            report = store.report(job["job_id"])
            raw = json.dumps(report.model_dump(mode="json"), sort_keys=True).encode()
            receipt = json.loads(report.tools["runner_receipt"])
            result["reports"].append(
                {
                    "job_alias": hashlib.sha256(job["job_id"].encode()).hexdigest(),
                    "report_sha256": hashlib.sha256(raw).hexdigest(),
                    "apk_sha256": report.sample.apk_sha256,
                    "behaviors": len(report.behaviors),
                    "evidence": len(report.evidence),
                    "comparisons": len(report.result.issues),
                    "expected_invoke_present": any(
                        e.api_call
                        and e.api_call.target_descriptor
                        == "Landroid/telephony/TelephonyManager;->getDeviceId()Ljava/lang/String;"
                        for e in report.evidence
                    ),
                    "expected_quote_present": any(
                        e.kind == "POLICY_SENTENCE"
                        and e.excerpt == "This controlled fixture may access device identifiers."
                        for e in report.evidence
                    ),
                    "unreviewed_retained": b"UNREVIEWED" in raw,
                    "runner_receipt": receipt,
                }
            )
        print(json.dumps(result, default=str))
finally:
    store.close()
