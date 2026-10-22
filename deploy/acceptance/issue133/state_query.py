"""Read-only observer executed inside the owned API with its normal RLS transaction."""

import json
import os
from pathlib import Path

import sqlalchemy as sa
from privacytrace.storage_factory import create_store

store = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
with store._transaction() as connection:
    parameters = {"instance": store.instance_id}
    jobs = [
        dict(row)
        for row in connection.execute(
            sa.text("""
                SELECT j.job_id, j.record->'job'->>'state' AS state,
                    j.record->'bundle' IS NOT NULL
                        AND j.record->'bundle' <> 'null'::jsonb AS has_report,
                    e.state AS execution_state, e.fence, e.attempt
                FROM privacytrace.jobs j
                LEFT JOIN privacytrace.job_executions e USING(instance_id,job_id)
                WHERE j.instance_id=:instance ORDER BY j.job_id
            """),
            parameters,
        ).mappings()
    ]
    counts = {
        name: connection.execute(
            sa.text("SELECT count(*) FROM privacytrace." + name + " WHERE instance_id=:instance"),
            parameters,
        ).scalar()
        for name in (
            "intake_documents",
            "outbox_events",
            "runner_materials",
            "deletion_intents",
            "upload_reservations",
            "runtime_inputs",
        )
    }
    scopes = [
        dict(row)
        for row in connection.execute(
            sa.text("""
                SELECT scope_id,kind,tombstone FROM privacytrace.analysis_scopes
                WHERE instance_id=:instance ORDER BY created_at
            """),
            parameters,
        ).mappings()
    ]
print(
    json.dumps(
        {
            "jobs": jobs,
            "counts": counts,
            "scopes": scopes,
            "material_files": sum(1 for item in store.root.rglob("*") if item.is_file()),
        }
    )
)
store.close()
