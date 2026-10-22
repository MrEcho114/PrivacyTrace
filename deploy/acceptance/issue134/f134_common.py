"""Shared fault-injection harness for Issue #134 (F01-F04, F07).

Every mutation is scoped by the random Compose project persisted in the
laboratory's ``owner.json``. This module never issues a global prune, never
stops the shared daemon, and never touches another project's resources.

The harness is the executor, not the product: it drives the real HTTP entry,
the real PostgreSQL outbox/execution ledger, the real broker and the real
Runner. Observations are written to private evidence files (no tokens, no
credentials, no private absolute paths).
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

SOURCE = Path(os.environ.get("PT_F_SOURCE", str(Path(__file__).resolve().parents[3]))).resolve()
LAB_STATE = (
    Path(os.environ["PT_F_LAB_STATE"]).resolve() if os.environ.get("PT_F_LAB_STATE") else None
)
CA_FILE = Path(
    os.environ.get(
        "PT_F_CA",
        str(SOURCE / "tmp/issue73-local-env/tls/ca.crt"),
    )
)
EVIDENCE = Path(
    os.environ.get(
        "PT_F_EVIDENCE",
        str(SOURCE / ".scratch/issue134-evidence"),
    )
)
QUEUE_PREFIX = "pt80:"


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_json(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(raw)


def run(argv, *, input=None, timeout=180, check=True):
    result = subprocess.run(argv, input=input, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        error = RuntimeError(f"command failed ({result.returncode}): {argv[0]}")
        error.stdout = result.stdout
        error.stderr = result.stderr
        raise error
    return result


def wait_for(description, predicate, *, timeout=90, interval=0.2):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise TimeoutError(f"timed out waiting for {description}")


def wait_absent(description, predicate, *, timeout=90, interval=0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not predicate():
            return True
        time.sleep(interval)
    raise TimeoutError(f"timed out waiting until absent: {description}")


class Lab:
    """One previously provisioned, Lead-owned laboratory."""

    ROLES = (
        "web",
        "api",
        "postgres",
        "redis",
        "dispatcher",
        "worker",
        "gateway",
        "runner",
    )

    def __init__(self, state=LAB_STATE):
        if state is None:
            raise SystemExit("PT_F_LAB_STATE or an explicit state path is required")
        self.root = Path(state).resolve()
        owner = json.loads((self.root / "owner.json").read_text())
        self.owner = owner
        self.project = owner["project"]
        self.instance = owner["instance_id"]
        self.port = int(owner["https_port"])
        if self.root.name != self.project or not re.fullmatch(r"pt81-[0-9a-f]{12}", self.project):
            raise ValueError("laboratory ownership mismatch")
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            str(self.root / "deployment.env"),
            "-f",
            str(SOURCE / "deploy/compose.yaml"),
            "-f",
            str(self.root / "ports.yaml"),
            "-f",
            str(self.root / "laboratory.json"),
        ]

    # -- process helpers -------------------------------------------------
    def compose_run(self, *args, timeout=240, input=None, check=True):
        result = run([*self.compose, *args], timeout=timeout, input=input, check=check)
        return result

    def docker(self, *args, timeout=120, check=True):
        return run(["docker", *args], timeout=timeout, check=check)

    def role_id(self, role):
        result = self.compose_run("ps", "-q", "-a", role)
        return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""

    def role_ids(self):
        result = self.compose_run("ps", "-q", "-a")
        return [line for line in result.stdout.splitlines() if line.strip()]

    def inspect(self, identifier):
        return json.loads(self.docker("inspect", identifier).stdout)[0]

    def running_roles(self):
        output = self.compose_run("ps", "--format", "json").stdout
        result = {}
        for line in output.splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            result[record.get("Service", "")] = {
                "state": record.get("State", ""),
                "health": record.get("Health", ""),
                "id": record.get("ID", ""),
            }
        return result

    def python(self, source, service="api"):
        return self.compose_run(
            "exec", "-T", service, "/opt/venv/bin/python", "-c", source
        ).stdout.strip()

    def psql(self, sql):
        return self.compose_run(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "privacytrace_bootstrap",
            "-d",
            "privacytrace",
            "-v",
            "ON_ERROR_STOP=1",
            "-qtAX",
            "-c",
            sql,
        ).stdout.strip()

    def db(self, sql):
        output = self.psql(sql)
        return [json.loads(line) for line in output.splitlines() if line.strip()]

    def logs(self, role, tail=400):
        identifier = self.role_id(role)
        if not identifier:
            return ""
        result = self.docker("logs", "--tail", str(tail), identifier, check=False)
        return (result.stdout or "") + (result.stderr or "")

    # -- lifecycle -------------------------------------------------------
    def health(self, timeout=5):
        try:
            result = self.compose_run(
                "exec",
                "-T",
                "api",
                "/opt/venv/bin/python",
                "-c",
                "import urllib.request,urllib.error;"
                "print(urllib.request.urlopen('http://127.0.0.1:8000/_health/ready',"
                f"timeout={timeout}).status)",
                timeout=30,
            )
            return result.stdout.strip() == "200"
        except (RuntimeError, subprocess.TimeoutExpired):
            return False

    def ready(self, timeout=120):
        wait_for("api health", self.health, timeout=timeout)

    def stop(self, *roles):
        self.compose_run("stop", *roles)

    def start(self, *roles):
        self.compose_run("start", *roles)

    def pause(self, role):
        identifier = self.role_id(role)
        if not identifier:
            raise RuntimeError(f"no container for role {role}")
        self.docker("pause", identifier)
        return identifier

    def resume(self, role):
        identifier = self.role_id(role)
        if not identifier:
            raise RuntimeError(f"no container for role {role}")
        self.docker("unpause", identifier)
        return identifier

    def kill(self, role, signal="SIGKILL"):
        identifier = self.role_id(role)
        if not identifier:
            raise RuntimeError(f"no container for role {role}")
        self.docker("kill", "--signal", signal, identifier)
        return identifier

    def ensure_role_up(self, role, timeout=60):
        identifier = self.role_id(role)
        wait_for(
            f"{role} running",
            lambda: self.inspect(identifier)["State"]["Running"] is True,
            timeout=timeout,
        )

    def wait_healthy(self, role, timeout=120):
        def healthy():
            identifier = self.role_id(role)
            if not identifier:
                return False
            state = self.inspect(identifier)["State"]
            return state.get("Running") is True and (
                state.get("Health", {}).get("Status") in {None, "healthy"}
            )

        return wait_for(f"{role} healthy", healthy, timeout=timeout)

    def run_second_worker(self):
        """A second consumer via ``compose run``; never rebuilds the paused one."""
        name = "f134-worker-2-" + self.project[-6:]
        self.docker("rm", "--force", name, check=False)
        self.compose_run("run", "-d", "--no-deps", "--name", name, "worker")
        return name

    def second_worker_running(self, name):
        try:
            return self.inspect(name)["State"]["Running"] is True
        except RuntimeError:
            return False

    def remove_second_worker(self, name):
        self.docker("rm", "--force", name, check=False)

    # -- derived images --------------------------------------------------
    def commit_image(self, tag, base_id, entrypoint, timeout=120):
        """Derive a controlled image from a local immutable image without a build.

        The laboratory daemon has no registry access, so ``docker build`` cannot
        resolve ``FROM sha256:...``; committing an unstarted container keeps the
        derivation local and reproducible.
        """
        name = "f134-commit-" + uuid4().hex[:12]
        self.docker("create", "--name", name, base_id, check=True)
        try:
            arguments = ["commit"]
            for change in (
                "USER 65534:65534",
                "ENTRYPOINT " + json.dumps(entrypoint),
                "HEALTHCHECK NONE",
            ):
                arguments += ["--change", change]
            arguments += [name, tag]
            self.docker(*arguments, timeout=timeout)
        finally:
            self.docker("rm", "--force", name, check=False)
        return self.docker("image", "inspect", tag, "--format", "{{.Id}}").stdout.strip()

    # -- compose override ------------------------------------------------
    def override(self):
        return ComposeOverride(self)

    # -- database observations ------------------------------------------
    def outbox(self, job_id=None):
        condition = f" AND job_id='{job_id}'" if job_id else ""
        rows = self.db(
            "SELECT json_build_object("
            "'event_id',event_id,'job_id',job_id,'state',state,'attempts',attempts,"
            "'last_error_code',last_error_code,'created_at',created_at,"
            "'claimed_until',claimed_until,'delivered_at',delivered_at)"
            " FROM privacytrace.outbox_events WHERE instance_id="
            f"'{self.instance}'{condition} ORDER BY created_at"
        )
        return rows

    def executions(self, job_id=None):
        condition = f" AND job_id='{job_id}'" if job_id else ""
        rows = self.db(
            "SELECT json_build_object("
            "'job_id',job_id,'state',state,'attempt',attempt,'fence',fence,"
            "'owner',owner,'event_id',event_id,'leased_until',leased_until,"
            "'started_at',started_at,'last_error_code',last_error_code,"
            "'result_sha256',result_sha256)"
            " FROM privacytrace.job_executions WHERE instance_id="
            f"'{self.instance}'{condition} ORDER BY job_id"
        )
        return rows

    def jobs(self):
        return self.db(
            "SELECT json_build_object('job_id',job_id,'state',"
            "record->'job'->>'state','error',record->'job'->>'error',"
            "'has_bundle',(record->'bundle' IS NOT NULL AND record->'bundle'<>'null'::jsonb))"
            " FROM privacytrace.jobs WHERE instance_id="
            f"'{self.instance}' ORDER BY job_id"
        )

    def counts(self):
        names = (
            "intake_documents",
            "runner_materials",
            "runtime_inputs",
            "upload_reservations",
        )
        values = {}
        for name in names:
            values[name] = int(
                self.psql(
                    "SELECT count(*) FROM privacytrace."
                    + name
                    + f" WHERE instance_id='{self.instance}'"
                )
                or 0
            )
        values["jobs"] = len(self.jobs())
        return values

    def draft_events(self, draft_id):
        # The durable intake stores the authoritative draft document in
        # PostgreSQL; current.json is only an existence marker on disk.
        source = (
            "import json,os;from pathlib import Path;"
            "from privacytrace.storage_factory import create_store;"
            "from privacytrace.postgres_intake import PostgresWebIntake;"
            "store=create_store(Path(os.environ['PRIVACYTRACE_STORE_ROOT']));"
            "intake=PostgresWebIntake(store);"
            f"draft=intake._get({draft_id!r});"
            "intake.close();store.close();"
            "print(json.dumps([{'job_id':r['job_id'],'request_id':r.get('request_id'),"
            "'events':r['events']} for r in draft['jobs']]))"
        )
        return json.loads(self.python(source))

    def audit(self, job_id=None, limit=100):
        condition = f" AND scope_id='{job_id}'" if job_id else ""
        return self.db(
            "SELECT json_build_object('action',action,'at',created_at) "
            "FROM privacytrace.audit_events WHERE instance_id="
            f"'{self.instance}'{condition} ORDER BY created_at DESC LIMIT {int(limit)}"
        )

    def state(self):
        """SQL-only ledger view; works while any application role is stopped."""
        jobs = self.jobs()
        executions = {row["job_id"]: row for row in self.executions()}
        outbox = self.outbox()
        result = {
            "jobs": [],
            "outbox": [],
            "counts": self.counts(),
            "source": "INTERNAL_SQL_OBSERVER_NOT_CLIENT",
        }
        for job in jobs:
            execution = executions.get(job["job_id"], {})
            result["jobs"].append(
                {
                    "job_id": job["job_id"],
                    "state": job["state"],
                    "has_report": job["has_bundle"],
                    "execution_state": execution.get("state"),
                    "fence": execution.get("fence"),
                    "attempt": execution.get("attempt"),
                }
            )
        for row in outbox:
            result["outbox"].append(
                {
                    "job_id": row["job_id"],
                    "state": row["state"],
                    "attempts": row["attempts"],
                    "last_error_code": row["last_error_code"],
                }
            )
        return result

    # -- broker ----------------------------------------------------------
    def broker_url(self):
        return (self.root / "secrets" / "runtime_broker_url").read_text().strip()

    def redis_auth(self):
        from urllib.parse import urlsplit

        return urlsplit(self.broker_url()).password or ""

    def redis_cli(self, *args):
        result = self.compose_run(
            "exec",
            "-T",
            "redis",
            "redis-cli",
            "--user",
            "app",
            "--pass",
            self.redis_auth(),
            "--no-auth-warning",
            *args,
            check=False,
        )
        return (result.stdout or "").strip()

    def queue_key(self):
        return QUEUE_PREFIX + self.instance + ":privacytrace." + self.instance

    def queue_depth(self):
        value = self.redis_cli("LLEN", self.queue_key())
        return int(value) if value.isdigit() else -1

    def publish_duplicate(self, job_id, times=2):
        """Publish the exact outbox message again through the product publisher."""
        source = "\n".join(
            [
                "import json, os",
                "from pathlib import Path",
                "import sqlalchemy as sa",
                "from privacytrace.storage_factory import create_store, resolve_redis_url",
                "from privacytrace.postgres_schema import outbox",
                "from privacytrace.postgres_outbox import EVENT_TYPE",
                "from privacytrace.queue_runtime import BrokerConfig, CeleryPublisher",
                "store = create_store(Path(os.environ['PRIVACYTRACE_STORE_ROOT']))",
                "with store._transaction() as conn:",
                "    row = conn.execute(sa.select(outbox).where(",
                "        outbox.c.instance_id == store.instance_id,",
                f"        outbox.c.job_id == {job_id!r})).mappings().one()",
                "message = {'version': 1, 'event_type': EVENT_TYPE,",
                "           'instance_id': store.instance_id,",
                "           'job_id': row['job_id'], 'event_id': str(row['event_id'])}",
                "config = BrokerConfig(resolve_redis_url(), store.instance_id)",
                "publisher = CeleryPublisher(config)",
                f"for _ in range({int(times)}):",
                "    publisher.publish(message)",
                "publisher.close()",
                "store.close()",
                "print(json.dumps({'published': True}))",
            ]
        )
        return json.loads(self.python(source, service="worker"))

    # -- runner scanner containers --------------------------------------
    def scanner_containers(self):
        """Only scan containers whose bind source lives under this lab's runner root.

        A label filter alone would also match another ticket's/old laboratory's
        containers on the shared daemon; ownership is proven through the mount.
        """
        identifiers = [
            item
            for item in self.docker(
                "ps", "-aq", "--filter", "label=privacytrace.run"
            ).stdout.splitlines()
            if item.strip()
        ]
        if not identifiers:
            return []
        try:
            inspected = json.loads(self.docker("inspect", *identifiers).stdout)
        except RuntimeError as error:
            stderr = (getattr(error, "stderr", "") or "").lower()
            if "no such object" not in stderr:
                raise
            inspected = []
        owned = []
        for item in inspected:
            for mount in item["Mounts"]:
                if mount["Type"] == "bind" and Path(mount["Source"]).is_relative_to(
                    self.root / "runner"
                ):
                    owned.append(item["Id"])
                    break
        return owned

    def inspect_scanner(self, identifier):
        raw = self.inspect(identifier)
        host = raw["HostConfig"]
        return {
            "container": raw["Id"][:12],
            "image_id": raw["Image"],
            "user": raw["Config"]["User"],
            "env_keys": sorted(raw["Config"].get("Env") or []),
            "network_mode": host["NetworkMode"],
            "read_only": host["ReadonlyRootfs"],
            "privileged": host["Privileged"],
            "cap_drop": host["CapDrop"],
            "cap_add": host["CapAdd"],
            "security_opt": host["SecurityOpt"],
            "memory": host["Memory"],
            "memory_swap": host["MemorySwap"],
            "nano_cpus": host["NanoCpus"],
            "pids_limit": host["PidsLimit"],
            "mounts": [
                {
                    "destination": item["Destination"],
                    "read_only": not item["RW"],
                    "type": item["Type"],
                }
                for item in raw["Mounts"]
            ],
            "labels": {
                key: value
                for key, value in (raw["Config"].get("Labels") or {}).items()
                if key.startswith("privacytrace.")
            },
            "has_docker_socket": any(
                item["Destination"] == "/var/run/docker.sock" for item in raw["Mounts"]
            ),
        }

    def role_isolation(self):
        """Independent inspect of every long-lived role (not the product receipt)."""
        result = {}
        for role in self.ROLES:
            identifier = self.role_id(role)
            if not identifier:
                continue
            raw = self.inspect(identifier)
            host = raw["HostConfig"]
            mounts = raw["Mounts"]
            result[role] = {
                "user": raw["Config"]["User"],
                "read_only": host["ReadonlyRootfs"],
                "cap_drop": host["CapDrop"],
                "cap_add": host["CapAdd"] or [],
                "privileged": host["Privileged"],
                "security_opt": host["SecurityOpt"],
                "pids_limit": host["PidsLimit"],
                "has_docker_socket": any(
                    item["Destination"] == "/var/run/docker.sock" for item in mounts
                ),
                "host_binds": [
                    item["Destination"]
                    for item in mounts
                    if item["Type"] == "bind"
                    and not item["Destination"].startswith("/run/secrets/")
                    and item["Destination"] != "/var/run/docker.sock"
                ],
            }
        return result

    # -- logs of interest -------------------------------------------------
    def warning_lines(self, role, tail=4000):
        """Lines emitted by the fixed diagnostic logger.

        The Celery worker log format in the product does not include
        ``%(message)s``, so the diagnostic code itself is not readable from the
        container log; the warning line count still shows that a diagnostic was
        emitted. This is recorded, never used to fake a verdict.
        """
        text = self.logs(role, tail=tail)
        return sum(1 for line in text.splitlines() if "[privacytrace runtime WARNING]" in line)

    def diagnostic_codes(self, role, tail=2000):
        text = self.logs(role, tail=tail)
        return sorted(set(re.findall(r"privacytrace\.worker\.([A-Z_]+)", text)))


class ComposeOverride:
    """Temporary, reverted laboratory.json edits for lease/timeout variants."""

    def __init__(self, lab):
        self.lab = lab
        self.path = lab.root / "laboratory.json"
        self.original = json.loads(self.path.read_text())
        self.current = json.loads(self.path.read_text())

    def env(self, service, key, value):
        self.current.setdefault("services", {}).setdefault(service, {}).setdefault(
            "environment", {}
        )[key] = value
        return self

    def write(self):
        self.path.write_text(json.dumps(self.current))

    def apply(self, *roles):
        self.write()
        self.lab.compose_run("up", "-d", "--no-deps", "--force-recreate", *roles)
        self.lab.ready()
        return self

    def restore(self, *roles):
        self.path.write_text(json.dumps(self.original))
        if roles:
            self.lab.compose_run("up", "-d", "--no-deps", "--force-recreate", *roles)
            self.lab.ready()


class Client:
    """Raw HTTPS client to the real web entry (Caddy -> API)."""

    def __init__(self, lab, ca_file=CA_FILE, host="localhost"):
        self.lab = lab
        self.base = f"https://localhost:{lab.port}"
        self.host = host
        self.ca_file = Path(ca_file)

    def _opener(self):
        context = ssl.create_default_context(cafile=str(self.ca_file))
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)
        )

    def request(
        self,
        path,
        *,
        method="GET",
        json_body=None,
        raw_body=None,
        token="",
        timeout=30,
    ):
        url = self.base + path
        payload = raw_body
        headers = {"Host": self.host}
        if raw_body is None and json_body is not None:
            payload = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        if payload is not None:
            headers["Content-Length"] = str(len(payload))
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        started = time.monotonic()
        try:
            with self._opener().open(request, timeout=timeout) as response:
                body = response.read()
                return {
                    "method": method,
                    "path": path,
                    "status": response.status,
                    "bytes": len(body),
                    "body": body,
                    "json": _maybe_json(body),
                    "duration_s": round(time.monotonic() - started, 3),
                }
        except urllib.error.HTTPError as error:
            body = error.read()
            return {
                "method": method,
                "path": path,
                "status": error.code,
                "bytes": len(body),
                "body": body,
                "json": _maybe_json(body),
                "duration_s": round(time.monotonic() - started, 3),
            }
        except (urllib.error.URLError, OSError, ssl.SSLError) as error:
            return {
                "method": method,
                "path": path,
                "status": 0,
                "bytes": 0,
                "body": b"",
                "json": None,
                "error": type(error).__name__,
                "duration_s": round(time.monotonic() - started, 3),
            }

    def health(self):
        result = self.request("/api/v1/health")
        return result["status"] == 200


def _maybe_json(body):
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def client_unconfirmed_post(port, path, body, token, ca_file):
    """Send one complete HTTPS POST and close before reading the response.

    The server receives and persists the request; the client never observes
    the response. That is the exact shape of an unconfirmed receipt, and it is
    the client side of F01's idempotent retry contract.
    """
    context = ssl.create_default_context(cafile=str(ca_file))
    connection = http.client.HTTPSConnection("localhost", port, context=context, timeout=30)
    try:
        connection.putrequest("POST", path, skip_host=True)
        connection.putheader("Host", "localhost")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(body)))
        connection.putheader("Authorization", "Bearer " + token)
        connection.endheaders()
        connection.send(body)
        return {"sent": True, "response_read": False, "at_utc": utc()}
    finally:
        connection.close()


class Business:
    """The real draft -> upload -> start -> poll path used by the product."""

    def __init__(self, lab, client):
        self.lab = lab
        self.client = client
        self.tokens = {}
        self.fixed = None
        self.last_purge = None

    def fixtures(self):
        if str(SOURCE / "apps/api/tests") not in sys.path:
            sys.path.insert(0, str(SOURCE / "apps/api/tests"))
        import apk_fixture_builder  # noqa: PLC0415

        package = "org.privacytrace.acceptance.single"
        single = apk_fixture_builder.apk_bytes(
            package_name=package,
            version_code="101",
            permission="android.permission.CAMERA",
            camera=True,
        )
        self.fixed = {
            "apk": single,
            "sha256": sha256_bytes(single),
            "package": package,
        }
        return self.fixed

    def purge_drafts(self):
        """Test-environment recovery: remove leftover drafts of this instance.

        Only used to free the client draft quota that earlier aborted variants
        left behind; it goes through the product intake's own deletion path and
        is recorded as environment preparation, never as a case result.
        """
        source = (
            "import json;from privacytrace.durable_intake import DurableWebIntake;"
            "from privacytrace.main import app;"
            "service=DurableWebIntake(app.state.job_store);"
            "ids=service.store.draft_ids();errors=[]\n"
            "for draft in ids:\n"
            " try: service.delete_draft(draft)\n"
            " except Exception as exc: errors.append(type(exc).__name__)\n"
            "print(json.dumps({'purged':len(ids)-len(errors),'errors':errors,"
            "'remaining':len(service.store.draft_ids())}))"
        )
        return json.loads(self.lab.python(source))

    def create(self, name, policy_text="This controlled fixture may access device identifiers."):
        body = {
            "name": name,
            "sources": [
                {
                    "id": "policy",
                    "title": "Synthetic acceptance policy",
                    "text": policy_text,
                    "url": "",
                    "source_type": "OFFICIAL_WEB_POLICY",
                }
            ],
        }
        for attempt in range(3):
            result = self.client.request("/api/v1/web/drafts", method="POST", json_body=body)
            if result["status"] == 200:
                payload = result["json"]
                token = payload.get("capability_token") or payload.get("token") or ""
                if not token:
                    raise RuntimeError("draft creation returned no capability token")
                return {
                    "id": str(payload["id"]),
                    "token": token,
                    "revision": int(payload.get("revision", 1)),
                }
            detail = ""
            if isinstance(result["json"], dict):
                detail = str(result["json"].get("detail", ""))
            if result["status"] == 429 and detail == "CLIENT_DRAFT_QUOTA_REACHED" and attempt < 2:
                self.last_purge = self.purge_drafts()
                continue
            if result["status"] == 429 and attempt < 2:
                time.sleep(62)
                continue
            raise RuntimeError(f"draft creation returned {result['status']}: {detail}")

    def upload(self, scope):
        fixture = self.fixed or self.fixtures()
        result = self.client.request(
            f"/api/v1/web/drafts/{scope['id']}/apk",
            method="POST",
            raw_body=fixture["apk"],
            token=scope["token"],
            timeout=300,
        )
        if result["status"] == 200 and isinstance(result["json"], dict):
            scope["revision"] = int(result["json"].get("revision", scope["revision"] + 1))
        return result

    def start(self, scope, request_id=None):
        request_id = request_id or uuid4().hex
        result = self.client.request(
            f"/api/v1/web/drafts/{scope['id']}/start",
            method="POST",
            json_body={"revision": scope["revision"], "request_id": request_id},
            token=scope["token"],
        )
        if result["status"] == 200 and isinstance(result["json"], dict):
            payload = result["json"]
            scope["job_id"] = str(payload.get("id") or payload.get("job_id") or "")
        scope["request_id"] = request_id
        return result

    def job(self, scope):
        return self.client.request(f"/api/v1/jobs/{scope['job_id']}", token=scope["token"])

    def report(self, scope):
        return self.client.request(f"/api/v1/jobs/{scope['job_id']}/report", token=scope["token"])

    def wait_terminal(self, scope, timeout=180, interval=1.0):
        def poll():
            result = self.job(scope)
            if result["status"] == 200 and isinstance(result["json"], dict):
                state = result["json"].get("state")
                if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                    return result["json"]
            return None

        return wait_for("job terminal", poll, timeout=timeout, interval=interval)

    def wait_execution(self, job_id, states, timeout=90, interval=0.15):
        wanted = set(states)

        def poll():
            rows = self.lab.executions(job_id)
            if rows and rows[0]["state"] in wanted:
                return rows[0]
            return None

        return wait_for(f"execution {sorted(wanted)}", poll, timeout=timeout, interval=interval)

    def cleanup_scope(self, scope):
        # Only this scope's own capability may delete it.
        result = self.client.request(
            f"/api/v1/web/drafts/{scope['id']}",
            method="DELETE",
            token=scope["token"],
        )
        if result["status"] == 429:
            time.sleep(62)
            result = self.client.request(
                f"/api/v1/web/drafts/{scope['id']}",
                method="DELETE",
                token=scope["token"],
            )
        return result["status"]


class Case:
    """One measurable variant with a private, self-describing evidence file."""

    def __init__(self, case, variant, purpose):
        self.case = case
        self.variant = variant
        self.purpose = purpose
        self.started = utc()
        self.steps = []
        self.checks = []
        self.probes = []
        self.artifacts = {}
        self.error = ""
        self.finished = ""
        self.result_override = ""

    def block(self, reason, detail=""):
        self.result_override = "BLOCKED"
        self.note("BLOCKED", reason, detail)
        return self

    def note(self, name, expected, actual, **evidence):
        self.steps.append(
            {
                "step": name,
                "at_utc": utc(),
                "expected": expected,
                "actual": actual,
                "evidence": evidence,
            }
        )
        return actual

    def check(self, name, passed, detail=""):
        self.checks.append({"check": name, "passed": bool(passed), "detail": detail})
        return bool(passed)

    def probe(self, name, observed, detail=""):
        """Non-blocking extra observation; never changes the case verdict."""
        self.probes.append({"probe": name, "observed": bool(observed), "detail": detail})
        return bool(observed)

    def artifact(self, name, value):
        self.artifacts[name] = value

    def finish(self, error=""):
        self.finished = utc()
        self.error = error
        result = self.result_override or (
            "PASSED" if not error and all(item["passed"] for item in self.checks) else "FAILED"
        )
        payload = {
            "case": self.case,
            "variant": self.variant,
            "purpose": self.purpose,
            "started_utc": self.started,
            "finished_utc": self.finished,
            "result": result,
            "error": error,
            "checks": self.checks,
            "probes": self.probes,
            "steps": self.steps,
            "artifacts": self.artifacts,
            "harness": "issue134-f134",
        }
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        path = EVIDENCE / f"{self.case}-{self.variant}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return path, result


def lab_and_business():
    lab = Lab()
    client = Client(lab)
    return lab, client, Business(lab, client)


def main_guard(case_factory):
    """CLI: ``python -m deploy.acceptance.issue134.<drill> --variant A [--keep]``."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", action="append", default=[])
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--lab-state", default=str(LAB_STATE))
    args = parser.parse_args()
    variants = args.variant or list(case_factory.variants)
    exit_code = 0
    for variant in variants:
        case = Case(case_factory.case, variant, case_factory.purposes[variant])
        try:
            case_factory.run(variant, case, keep=args.keep)
        except Exception as error:  # noqa: BLE001 - the evidence file records it
            import traceback

            tail = traceback.format_exc().strip().splitlines()[-30:]
            case.note(
                "unhandled exception",
                "no exception",
                {"type": type(error).__name__, "tail": tail},
            )
            case.check("no unhandled exception", False, type(error).__name__)
            path, result = case.finish(error=type(error).__name__)
            print(
                json.dumps(
                    {"case": case.case, "variant": variant, "result": result, "evidence": str(path)}
                )
            )
            exit_code = 1
            continue
        path, result = case.finish()
        print(
            json.dumps(
                {"case": case.case, "variant": variant, "result": result, "evidence": str(path)}
            )
        )
        if result != "PASSED":
            exit_code = 1
    return exit_code


def guard_env(lab):
    """Refuse to run against anything that is not the expected ownership marker."""
    if lab.project != lab.root.name:
        raise ValueError("ownership mismatch")
    if (
        os.environ.get("PT_F_LAB_STATE")
        and Path(os.environ["PT_F_LAB_STATE"]).resolve() != lab.root
    ):
        raise ValueError("unexpected laboratory")
    health = lab.health()
    if not health:
        raise RuntimeError("laboratory API is not healthy")
    return lab
