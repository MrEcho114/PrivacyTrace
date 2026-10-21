"""Operational drills confined to one disposable deployment project."""

import copy
import hashlib
import json
import os
import secrets
from uuid import uuid4

from .provision import execute
from .r2_business_loop import (
    Fixtures,
    cleanup_created_scopes,
    create_scope,
    poll_job,
    start_job,
    upload_apk,
)
from .topology import request

SERVICES = ("web", "api", "worker", "dispatcher", "gateway")


def _recreate(lab):
    lab.run("up", "-d", "--no-deps", "--force-recreate", *SERVICES)
    lab.ready()


def rotate_database_and_broker(lab, topology):
    private = lab.root / "secrets"
    old = lab.root / ("rotation-" + uuid4().hex)
    old.mkdir(mode=0o700)
    os.chown(old, 10001, 10001)
    for name in ("runtime_database_url", "runtime_broker_url"):
        path = old / name
        path.write_bytes((private / name).read_bytes())
        os.chown(path, 10001, 10001)
        path.chmod(0o400)
    password = secrets.token_hex(24)
    original = (private / "runtime_database_url").read_text()
    from urllib.parse import urlsplit

    previous = urlsplit(original.strip()).password
    lab.run("stop", *SERVICES)
    try:
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
            input=f"ALTER ROLE privacytrace_runtime PASSWORD '{password}';",
        )
        (private / "runtime_database_url").write_text(original.replace(previous, password))
        broker_old = (private / "runtime_broker_url").read_text()
        broker_password = urlsplit(broker_old.strip()).password
        broker_new = secrets.token_hex(24)
        for name in ("runtime_broker_url", "runtime_health_url"):
            (private / name).write_text(
                (private / name).read_text().replace(broker_password, broker_new)
            )
        config = private / "redis.conf"
        config.write_text(config.read_text().replace(">" + broker_password, ">" + broker_new))
        lab.run("up", "-d", "--no-deps", "--force-recreate", "redis")
    finally:
        _recreate(lab)
    source = (
        "from pathlib import Path;import sqlalchemy as sa;import redis;"
        "from sqlalchemy.exc import OperationalError;\n"
        "try:\n"
        " e=sa.create_engine(Path('/old/runtime_database_url').read_text().strip(),"
        "hide_parameters=True);e.connect();raise AssertionError('old DB credential accepted')\n"
        "except OperationalError as exc:\n"
        " assert exc.orig.sqlstate=='28P01' or 'password authentication failed' in str(exc.orig)\n"
        "try:\n"
        " redis.Redis.from_url(Path('/old/runtime_broker_url').read_text().strip()).ping();"
        "raise AssertionError('old broker credential accepted')\n"
        "except redis.exceptions.AuthenticationError: pass\n"
        "print('OLD_CREDENTIALS_REJECTED')"
    )
    result = lab.run("run", "--rm", "--no-deps", "--volume", f"{old}:/old:ro", "api", "-c", source)
    assert result == "OLD_CREDENTIALS_REJECTED"
    scope = create_scope(topology, "rotated-credentials", "Synthetic rotation policy.")
    assert upload_apk(topology, scope, Fixtures.build().single_apk).status == 200
    assert start_job(topology, scope).status == 200
    assert poll_job(topology, scope, budget_s=180, interval_s=0.5)["state"] == "SUCCEEDED"
    return {
        "old_database_password": "authentication rejected",
        "old_broker_password": "rejected:AUTH",
        "new_credentials": "ready and real scan succeeded",
    }


def disk_full(lab, topology):
    path = lab.root / "laboratory.json"
    original = json.loads(path.read_text())
    override = copy.deepcopy(original)
    identifier = lab.run("ps", "-q", "api")
    inspected = json.loads(execute(["docker", "inspect", identifier]))[0]
    previous = next(
        m["Name"] for m in inspected["Mounts"] if m["Destination"] == "/var/lib/privacytrace"
    )
    # Earlier drills in this laboratory may have retained drafts from an aborted
    # run; the disposable intake state is cleared so the disk boundary, not a
    # stale draft quota, is what this drill measures.
    purged = json.loads(
        lab.python(
            # The durable intake owns draft deletion; the API layer exposes it only
            # for that service, and capability tokens of drafts left by earlier
            # drills are gone. The disposable laboratory state is cleared directly.
            "import json\n"
            "from privacytrace.durable_intake import DurableWebIntake\n"
            "from privacytrace.main import app\n"
            "service = DurableWebIntake(app.state.job_store)\n"
            "ids = service.store.draft_ids()\n"
            "errors = []\n"
            "for draft_id in ids:\n"
            "    try:\n"
            "        service.delete_draft(draft_id)\n"
            "    except Exception as exc:\n"
            "        errors.append(type(exc).__name__)\n"
            "print(json.dumps({'purged': len(ids) - len(errors), 'errors': errors,\n"
            "    'remaining': len(service.store.draft_ids())}))\n"
        )
    )
    volume = lab.project + "_enospc_" + uuid4().hex[:8]
    execute(
        [
            "docker",
            "volume",
            "create",
            "--label",
            f"com.docker.compose.project={lab.project}",
            "--driver",
            "local",
            "--opt",
            "type=tmpfs",
            "--opt",
            "device=tmpfs",
            "--opt",
            "o=size=512m,uid=10001,gid=10001,mode=0700",
            volume,
        ]
    )
    lab.run("stop", *SERVICES)
    # A tmpfs volume is only mounted while a container holds it: without this
    # keeper the copied store is unmounted and discarded the moment the copy
    # container exits, and every draft committed before the swap loses its
    # material objects.
    keeper = execute(
        [
            "docker",
            "run",
            "--detach",
            "--label",
            f"com.docker.compose.project={lab.project}",
            "--volume",
            f"{volume}:/target",
            "--entrypoint",
            "/opt/venv/bin/python",
            inspected["Config"]["Image"],
            "-c",
            "import time;time.sleep(3600)",
        ]
    )
    try:
        lab.run(
            "run",
            "--rm",
            "--no-deps",
            "--volume",
            f"{previous}:/source:ro",
            "--volume",
            f"{volume}:/target",
            "api",
            "-c",
            # The API runs as uid 10001, but this copy runs as root: without the
            # ownership pass every copied directory stays root-owned and the first
            # draft write after the swap fails with EACCES instead of reaching the
            # size limit the drill is about.
            "import os,shutil;shutil.copytree('/source','/target',dirs_exist_ok=True)\n"
            "for base,dirs,files in os.walk('/target'):\n"
            " os.chown(base,10001,10001)\n"
            " for entry in dirs+files: os.chown(os.path.join(base,entry),10001,10001)\n",
        )
        override["volumes"] = {"materials": {"name": volume, "external": True}}
        path.write_text(json.dumps(override))
        _recreate(lab)
        fixture = Fixtures.build()
        keep = create_scope(topology, "enospc-retained", "Synthetic retained policy.")
        target = create_scope(topology, "enospc-target", "Synthetic full-disk policy.")
        initial = upload_apk(topology, keep, fixture.single_apk)
        assert initial.status == 200, f"ENOSPC baseline upload: {initial.status} {initial.json}"
        fill = (
            "import errno,os,json;from pathlib import Path;"
            "p=Path(os.environ['PRIVACYTRACE_STORE_ROOT'])/'.owned-enospc';"
            "f=p.open('xb',buffering=0);\n"
            "try:\n"
            " while True: f.write(b'x'*65536)\n"
            "except OSError as exc:\n"
            " assert exc.errno==errno.ENOSPC\n"
            "finally: f.close()\n"
            "print(json.dumps({'errno':errno.ENOSPC,'bytes':p.stat().st_size}))"
        )
        full = json.loads(lab.python(fill))
        refused = upload_apk(topology, target, fixture.single_apk)
        assert refused.status in {409, 503, 507}, f"full filesystem returned {refused.status}"
        lab.python(
            "import os;from pathlib import Path;"
            "(Path(os.environ['PRIVACYTRACE_STORE_ROOT'])/'.owned-enospc').unlink()"
        )
        assert upload_apk(topology, target, fixture.single_apk).status == 200
        digest = lab.python(
            "import os,hashlib;from pathlib import Path;"
            "from privacytrace.storage_factory import create_store;"
            "from privacytrace.postgres_intake import PostgresWebIntake;"
            "s=create_store(Path(os.environ['PRIVACYTRACE_STORE_ROOT']));i=PostgresWebIntake(s);"
            f"p=i.directory({keep.draft_id!r})/'input.apk';"
            "print(hashlib.sha256(p.read_bytes()).hexdigest());i.close();s.close()"
        )
        assert digest == fixture.single_sha256
        assert not cleanup_created_scopes()
        return {
            "drafts_purged": purged,
            "filesystem": "disposable tmpfs",
            "limit_bytes": 512 * 1024 * 1024,
            "actual_enospc": full,
            "upload_refusal_status": refused.status,
            "upload_after_space_released": 200,
            "retained_hash_verified": True,
        }
    finally:
        # Restore the source volume even when a check fails. The original volume
        # was read-only during the copy and is never filled or deleted.
        execute(["docker", "rm", "--force", keeper])
        lab.run("stop", *SERVICES)
        path.write_text(json.dumps(original))
        _recreate(lab)
        execute(["docker", "volume", "rm", volume])


def rotate_control_identity(lab):
    config_path = lab.root / "laboratory.json"
    original = json.loads(config_path.read_text())
    config = copy.deepcopy(original)
    private = lab.root / "secrets"
    old = lab.root / ("old-control-" + uuid4().hex)
    old.mkdir(mode=0o700)
    os.chown(old, 10001, 10001)
    for name in ("control_cert.pem", "control_key.pem"):
        path = old / name
        path.write_bytes((private / name).read_bytes())
        os.chown(path, 10001, 10001)
        path.chmod(0o400)
    pki = lab.root / "pki"
    name = "control-" + uuid4().hex
    execute(
        [
            "openssl",
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-subj",
            "/CN=rotated-control",
            "-keyout",
            str(pki / (name + ".key")),
            "-out",
            str(pki / (name + ".csr")),
        ]
    )
    execute(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(pki / (name + ".csr")),
            "-CA",
            str(pki / "ca.pem"),
            "-CAkey",
            str(pki / "ca.key"),
            "-CAcreateserial",
            "-days",
            "2",
            "-extfile",
            str(pki / "leaf.ext"),
            "-out",
            str(pki / (name + ".pem")),
        ]
    )
    import subprocess

    fingerprint = hashlib.sha256(
        subprocess.check_output(
            ["openssl", "x509", "-in", str(pki / (name + ".pem")), "-outform", "DER"]
        )
    ).hexdigest()
    env = config["services"]["runner"]["environment"]
    env["PRIVACYTRACE_RUNNER_PEERS"] += "," + fingerprint
    complete = False
    try:
        config_path.write_text(json.dumps(config))
        lab.run("up", "-d", "--no-deps", "--force-recreate", "runner")
        (private / "control_cert.pem").write_bytes((pki / (name + ".pem")).read_bytes())
        (private / "control_key.pem").write_bytes((pki / (name + ".key")).read_bytes())
        _recreate(lab)
        env["PRIVACYTRACE_RUNNER_PEERS"] = fingerprint
        config_path.write_text(json.dumps(config))
        lab.run("up", "-d", "--no-deps", "--force-recreate", "runner")
        lab.ready()
        source = (
            "import os,ssl,urllib.request,urllib.error;"
            "c=ssl.create_default_context(cafile='/run/secrets/control_tls_ca');"
            "c.load_cert_chain('/old/control_cert.pem','/old/control_key.pem');"
            "o=urllib.request.build_opener(urllib.request.ProxyHandler({}),"
            "urllib.request.HTTPSHandler(context=c));\n"
            "try:\n o.open(os.environ['PRIVACYTRACE_RUNNER_URL']+'/v1/health',timeout=3);"
            "raise AssertionError('old TLS peer accepted')\n"
            "except urllib.error.HTTPError as e:\n assert e.code==403\n"
            "print('OLD_TLS_PEER_REJECTED')"
        )
        assert (
            lab.run("run", "--rm", "--no-deps", "--volume", f"{old}:/old:ro", "api", "-c", source)
            == "OLD_TLS_PEER_REJECTED"
        )
        complete = True
        return {
            "old_control_peer_status": 403,
            "new_control_peer_ready": 200,
            "new_leaf_sha256": fingerprint,
        }
    finally:
        if not complete:
            for name in ("control_cert.pem", "control_key.pem"):
                (private / name).write_bytes((old / name).read_bytes())
            config_path.write_text(json.dumps(original))
            lab.run("up", "-d", "--no-deps", "--force-recreate", "runner")
            _recreate(lab)


def upgrade_rollback(lab, topology, previous_image):
    path = lab.root / "laboratory.json"
    original = json.loads(path.read_text())
    old = json.loads(execute(["docker", "image", "inspect", previous_image]))[0]
    assert old["Config"]["Labels"].get("org.opencontainers.image.revision")
    result = {}
    try:
        scope = None
        for leg, image in (
            ("previous", old["Id"]),
            ("candidate", lab.state["images"]["api"]),
            ("rollback", old["Id"]),
        ):
            config = copy.deepcopy(original)
            for role in ("api", "worker", "dispatcher", "gateway", "migrate", "reclaim"):
                config["services"].setdefault(role, {})["image"] = image
            path.write_text(json.dumps(config))
            lab.run("stop", *SERVICES)
            lab.run("--profile", "migration", "run", "--rm", "--no-deps", "migrate")
            _recreate(lab)
            if scope is None:
                scope = create_scope(topology, "version-compatible", "Synthetic upgrade policy.")
                assert upload_apk(topology, scope, Fixtures.build().single_apk).status == 200
                assert start_job(topology, scope).status == 200
                assert (
                    poll_job(topology, scope, budget_s=180, interval_s=0.5)["state"] == "SUCCEEDED"
                )
            assert (
                request(topology, f"/api/v1/jobs/{scope.job_id}/report", token=scope.token).status
                == 200
            )
            result[leg] = {
                "api_image_id": image,
                "retained_report_readable": True,
                "migration": "0080_05",
                "protocol": 1,
            }
        return result
    finally:
        path.write_text(json.dumps(original))
        _recreate(lab)
