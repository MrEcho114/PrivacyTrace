"""Deployment-level RuntimeBackup drill; only provision.py-owned resources."""

import hashlib
import json
import os
from uuid import uuid4

from .provision import execute
from .r2_business_loop import Fixtures, create_scope, upload_apk
from .topology import request


def drill(lab, topology):
    fixture = Fixtures.build()
    keep = create_scope(topology, "backup-retained", "Synthetic retained policy.")
    dead = create_scope(topology, "backup-deleted", "Synthetic deleted policy.")
    for scope in (keep, dead):
        if upload_apk(topology, scope, fixture.single_apk).status != 200:
            raise RuntimeError("backup canary upload rejected")
    destination = lab.root / ("backup-" + uuid4().hex)
    destination.mkdir(mode=0o700)
    os.chown(destination, 10001, 10001)
    snapshot = destination / "snapshot.ptbackup"
    services = ("web", "api", "worker", "dispatcher", "gateway")
    lab.run("stop", *services)
    try:
        summary = json.loads(
            lab.run(
                "run",
                "--rm",
                "--no-deps",
                "--volume",
                f"{destination}:/backup",
                "api",
                "-m",
                "privacytrace.runtime_backup",
                "backup",
                "/backup/snapshot.ptbackup",
            )
        )
        assert snapshot.is_file() and summary.get("files", 0) >= 2
    finally:
        lab.run("start", *services)
        lab.ready()
    deleted = request(
        topology, f"/api/v1/web/drafts/{dead.draft_id}", method="DELETE", token=dead.token
    )
    assert deleted.status == 200, "post-snapshot deletion rejected"
    database = "pt81_restore_" + uuid4().hex[:12] + "_test"
    lab.run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "privacytrace_bootstrap",
        "-d",
        "privacytrace",
        input=f"CREATE DATABASE {database} OWNER privacytrace_migrator;\n"
        f"REVOKE ALL ON DATABASE {database} FROM PUBLIC;\n"
        f"GRANT CONNECT ON DATABASE {database} TO privacytrace_migrator,privacytrace_runtime;",
    )
    mounts = []
    for role in ("migration", "runtime"):
        path = destination / (role + "_url")
        original = (lab.root / "secrets" / (role + "_database_url")).read_text().strip()
        path.write_text(original.rsplit("/", 1)[0] + "/" + database)
        os.chown(path, 10001, 10001)
        path.chmod(0o400)
        mounts += ["--volume", f"{path}:/run/secrets/restore_{role}_url:ro"]
    lab.run(
        "--profile",
        "migration",
        "run",
        "--rm",
        "--no-deps",
        *mounts,
        "-e",
        "PRIVACYTRACE_MIGRATION_DATABASE_URL_FILE=/run/secrets/restore_migration_url",
        "migrate",
    )
    volume = lab.project + "_restore_" + uuid4().hex[:8]
    execute(
        [
            "docker",
            "volume",
            "create",
            "--label",
            f"com.docker.compose.project={lab.project}",
            volume,
        ]
    )
    args = [
        "run",
        "--rm",
        "--no-deps",
        *mounts,
        "--volume",
        f"{volume}:/var/lib/privacytrace",
        "--volume",
        f"{destination}:/backup:ro",
        "-e",
        "PRIVACYTRACE_DATABASE_URL_FILE=/run/secrets/restore_runtime_url",
        "api",
    ]
    lab.run("stop", *services)
    try:
        restored = json.loads(
            lab.run(
                *args, "-m", "privacytrace.runtime_backup", "restore", "/backup/snapshot.ptbackup"
            )
        )
        assert restored.get("restored") is True and restored.get("deletions", 0) >= 1
        source = (
            "import os,json,hashlib;from pathlib import Path;"
            "from privacytrace.storage_factory import create_store;"
            "from privacytrace.postgres_intake import PostgresWebIntake;"
            "s=create_store(Path(os.environ['PRIVACYTRACE_STORE_ROOT']));i=PostgresWebIntake(s);"
            f"assert i.get({keep.draft_id!r})['uploaded'];"
            f"p=i.directory({keep.draft_id!r})/'input.apk';"
            f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={fixture.single_sha256!r};"
            f"assert not i.directory({dead.draft_id!r}).exists();"
            "print(json.dumps({'retained_hash_verified':True,'deleted_material_absent':True}));"
            "i.close();s.close()"
        )
        verified = json.loads(lab.run(*args, "-c", source))
        return {
            "backup_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "backup_bytes": snapshot.stat().st_size,
            "manifest": summary,
            "restore": restored,
            "readback": verified,
            "fresh_database": True,
            "separate_material_volume": True,
            "independent_deletion_journal": True,
        }
    finally:
        lab.run("start", *services)
        lab.ready()
        execute(["docker", "volume", "rm", volume])
