"""Explicit offline JSON report import, issuing new IDs and private capabilities.

Original JSON bytes and their evidence/provenance remain intact. This operation
does not import active executions, material paths, old credentials or schedules.
"""

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

from .auth import generate_capability_token
from .deletion_journal import fsync_directory
from .job_store import JobStore
from .runtime_models import StoredJob


def import_records(source, target, job_ids, mapping_path):
    if (
        not getattr(target, "uses_postgres", False)
        or not 1 <= len(job_ids) <= JobStore.MAX_RECORDS
        or len(set(job_ids)) != len(job_ids)
        or source.root == target.root
    ):
        raise ValueError("Explicit distinct JSON source and PostgreSQL target required")
    output = Path(mapping_path).absolute()
    JobStore(output.parent)._safe_root()
    if output.is_relative_to(source.root) or output.is_relative_to(target.root):
        raise ValueError("Credential mapping must be stored separately")
    with source._transaction():
        records, total = [], 0
        for job_id in job_ids:
            original = source._load(job_id).model_copy(deep=True)
            total += len(original.model_dump_json().encode())
            if total > 256 * 1024 * 1024:
                raise ValueError("Import batch capacity exceeded")
            if original.job.state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                raise ValueError("Active local jobs cannot be imported as runnable tasks")
            records.append(original)
        mapping = {record.job.id: uuid4().hex for record in records}
        credentials, imported = [], []
        for record in records:
            old_id = record.job.id
            token, digest = generate_capability_token()
            record.job.id = mapping[old_id]
            record.job.retry_of = mapping.get(record.job.retry_of)
            if record.bundle is not None:
                record.bundle.job = record.job.model_copy(deep=True)
            record.token_digest = digest
            # These are archived facts. No tool locator is opened or considered
            # proof of a scan in the new runtime; provenance is never upgraded.
            record.tools["storage_import"] = "EXPLICIT_JSON_ARCHIVE_WITH_NEW_CAPABILITY"
            imported.append(StoredJob.model_validate(record.model_dump()))
            credentials.append({"source_job_id": old_id, "job_id": record.job.id, "token": token})
        # Prepare the private receipt before COMMIT. If COMMIT is uncertain,
        # IDs/digests can be read back without losing the only new credentials.
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(
                json.dumps(
                    {"version": 1, "instance_id": target.instance_id, "jobs": credentials}
                ).encode()
            )
            handle.flush()
            os.fsync(handle.fileno())
        fsync_directory(output.parent)
        with target._transaction():
            for record in imported:
                if target._scope(record.job.id) is not None:
                    raise ValueError("Imported job ID already exists")
                target._write(record)
    return {"imported": len(imported), "mapping_prepared": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("job_ids", nargs="+")
    parser.add_argument("--mapping", required=True, type=Path)
    args = parser.parse_args()
    target = None
    try:
        from .storage_factory import create_store

        target = create_store(Path(os.environ["PRIVACYTRACE_STORE_ROOT"]))
        print(
            json.dumps(
                import_records(JobStore(args.source_root), target, args.job_ids, args.mapping)
            )
        )
        return 0
    except (ValueError, KeyError, OSError):
        print('{"error":"EXPLICIT_IMPORT_REJECTED"}')
        return 1
    finally:
        if target:
            target.close()


if __name__ == "__main__":
    raise SystemExit(main())
