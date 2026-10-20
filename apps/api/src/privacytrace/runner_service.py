"""Dedicated scan-host service. Only this service has the local Docker socket.

The fixed scanner and container policy are the existing isolated_scan module.
Requests contain validated identifiers, digests and temporary transfer permits.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore

from .isolated_scan import command, docker_prefix, scan_isolated
from .runner_protocol import canonical_uuid, manifest
from .runtime_materials import ticket_claims
from .runtime_tls import (
    PrivateClient,
    PrivateHandler,
    PrivateServer,
    RuntimeTLS,
    RuntimeUnavailable,
    json_value,
)
from .scan_workspace import AUDIT_BUDGET, ScanError, disk_usage, safe_path

MAX_DISK = 1024 * 1024 * 1024
MAX_RESULTS = 32 * 1024 * 1024
MAX_TRANSFER_SECONDS = 60


@dataclass(frozen=True)
class RunnerConfig:
    instance_id: str
    image_id: str
    root: Path
    timeout: int = 120

    def __post_init__(self):
        canonical_uuid(self.instance_id)
        if (
            type(self.image_id) is not str
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", self.image_id)
            or type(self.timeout) is not int
            or not 1 <= self.timeout <= 180
        ):
            raise ValueError("Fixed immutable runner image and bounded timeout required")


class Runner:
    def __init__(self, config, gateway):
        if os.name != "posix":
            raise ValueError("Dedicated Linux runner required")
        import fcntl

        self.config, self.gateway = config, gateway
        self.root = Path(config.root).absolute()
        safe_path(self.root)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077:
            raise ValueError("Private runner directory required")
        self.lock = (self.root / ".runner.lock").open("a+b")
        try:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise ValueError("Runner directory already owned by another process") from None
        try:
            self._initialize(config)
        except Exception:
            self.close()
            raise

    def _initialize(self, config):
        self.slots = BoundedSemaphore(1)
        self.faulted = False
        self.operations = self.root / "operations"
        self.operations.mkdir(mode=0o700, exist_ok=True)
        self.client_config = self.root / "docker-client"
        self.client_config.mkdir(mode=0o700, exist_ok=True)
        self.docker = [*docker_prefix(), "--config", str(self.client_config)]
        image = command([*self.docker, "image", "inspect", config.image_id, "--format", "{{.Id}}"])
        if image.strip() != config.image_id:
            self.close()
            raise ValueError("Configured runner image is unavailable")
        self.database = self.root / "requests.sqlite"
        safe_path(self.database)
        with self._database() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, digest TEXT NOT NULL, "
                "state TEXT NOT NULL, result BLOB, expires INTEGER NOT NULL)"
            )
        self.database.chmod(0o600)
        self._recover()

    @contextmanager
    def _database(self):
        conn = sqlite3.connect(self.database, timeout=5)
        try:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA secure_delete=ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def close(self):
        if not self.lock.closed:
            self.lock.close()

    def prune(self):
        with self._database() as conn:
            conn.execute(
                "DELETE FROM operations WHERE state <> 'RUNNING' AND expires < ?",
                (int(time.time()),),
            )

    def _recover(self):
        # This root is exclusively locked. Only UUID operations present in its
        # own ledger, with exact workspace label/image/mount proof, may be reaped.
        with self._database() as conn:
            known = {row[0]: row[1] for row in conn.execute("SELECT id,state FROM operations")}
            for operation in self.operations.iterdir():
                safe_path(operation)
                canonical_uuid(operation.name)
                if operation.name not in known or not operation.is_dir():
                    raise ValueError("Unknown runner residue requires operator inspection")
                scans = operation / "scans"
                if scans.exists():
                    for workspace in scans.iterdir():
                        safe_path(workspace)
                        if not workspace.is_dir():
                            continue
                        if not re.fullmatch(r"[a-f0-9]{32}", workspace.name):
                            raise ValueError("Unknown scan workspace requires inspection")
                        name = "privacytrace-" + workspace.name
                        exists = command(
                            [
                                *self.docker,
                                "ps",
                                "-aq",
                                "--filter",
                                "name=^/" + name + "$",
                            ]
                        ).strip()
                        if exists:
                            inspected = json_value(command([*self.docker, "inspect", name]))[0]
                            mounts = inspected["Mounts"]
                            if (
                                inspected["Image"] != self.config.image_id
                                or inspected["Config"]["Labels"].get("privacytrace.run")
                                != workspace.name
                                or len(mounts) != 1
                                or mounts[0]["Type"] != "bind"
                                or mounts[0]["Destination"] != "/input/sample.apk"
                                or mounts[0]["RW"] is not False
                                or Path(mounts[0]["Source"]).absolute() != workspace / "input.apk"
                            ):
                                raise ValueError("Unproven orphan container requires inspection")
                            command([*self.docker, "rm", "--force", name])
                # No other process can own these operation directories. This
                # clears charged reservations only after stopping owned containers.
                shutil.rmtree(operation)
            conn.execute("UPDATE operations SET state='ABORTED',result=NULL WHERE state='RUNNING'")
            conn.execute("DELETE FROM operations WHERE expires < ?", (int(time.time()),))

    def _permitted(self, value):
        for item in value["files"]:
            claims = ticket_claims(item["ticket"])
            for field in ("instance_id", "scope_id", "owner", "fence"):
                if claims[field] != value[field]:
                    raise PermissionError("Runner material binding rejected")
            if claims["mode"] != value["operation"]:
                raise PermissionError("Runner material operation rejected")
            reply = self.gateway.json("/v1/permit", ticket=item["ticket"])
            if reply != {"version": 1, "permitted": True}:
                raise PermissionError("Runner material permit unavailable")

    def run(self, value):
        value = manifest(value)
        if self.faulted:
            raise RuntimeUnavailable("Runner cleanup requires recovery")
        if value["instance_id"] != self.config.instance_id:
            raise PermissionError("Runner instance rejected")
        self._permitted(value)
        if not self.slots.acquire(blocking=False):
            raise RuntimeUnavailable("Runner capacity busy")
        try:
            return self._run_owned(value)
        finally:
            self.slots.release()

    def _receipt(self, path, operation, request_id):
        if path is None:
            return None
        path = Path(path).absolute()
        if not path.is_relative_to(operation / "scans"):
            raise ValueError("Unexpected scan receipt")
        safe_path(path)
        if not path.is_file() or path.stat().st_size > AUDIT_BUDGET:
            return None
        proof = json_value(path.read_bytes())
        host = proof.get("host_config") or {}
        return {
            "version": 1,
            "request_id": request_id,
            "image_id": proof.get("image_id"),
            "container": proof.get("container"),
            "container_created": proof.get("container_created", False),
            "input_removed": proof.get("input_removed", False),
            "cleanup_verified": proof.get("cleanup_verified", False),
            "user": proof.get("user"),
            "exit_state": proof.get("exit_state"),
            "isolation": {
                key: host[key]
                for key in (
                    "NetworkMode",
                    "ReadonlyRootfs",
                    "Memory",
                    "MemorySwap",
                    "NanoCpus",
                    "PidsLimit",
                    "CapDrop",
                    "CapAdd",
                    "SecurityOpt",
                    "Privileged",
                )
                if key in host
            },
            "mounts": [
                {"destination": m["Destination"], "read_only": not m["RW"]}
                for m in proof.get("mounts", [])
            ],
        }

    def _run_owned(self, value):
        request_id = value["request_id"]
        digest = hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with self._database() as conn:
            conn.execute(
                "DELETE FROM operations WHERE state <> 'RUNNING' AND expires < ?",
                (int(time.time()),),
            )
            previous = conn.execute(
                "SELECT digest,state,result FROM operations WHERE id=?", (request_id,)
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise PermissionError("Runner operation identity changed")
                if previous[1] == "DONE":
                    return json_value(previous[2])
                raise RuntimeUnavailable("Runner operation interrupted")
            size, count = conn.execute(
                "SELECT coalesce(sum(length(result)),0),count(*) FROM operations"
            ).fetchone()
            needed = (
                2 * sum(item["size"] for item in value["files"]) + AUDIT_BUDGET + 16 * 1024 * 1024
            )
            if (
                count >= 128
                or size > MAX_RESULTS - 8 * 1024 * 1024
                or disk_usage(self.root) + needed > MAX_DISK
                or shutil.disk_usage(self.root).free < needed
            ):
                raise RuntimeUnavailable("Runner storage capacity unavailable")
            conn.execute(
                "INSERT INTO operations VALUES (?,?, 'RUNNING',NULL,?)",
                (request_id, digest, int(time.time()) + 360),
            )
        operation = self.operations / request_id
        safe_path(operation)
        operation.mkdir(mode=0o700)
        inputs = operation / "inputs"
        inputs.mkdir(mode=0o700)
        try:
            transfer_deadline = time.monotonic() + MAX_TRANSFER_SECONDS
            for item in value["files"]:
                target = inputs / item["name"]
                size, sha = 0, hashlib.sha256()
                with (
                    self.gateway.open("/v1/material", ticket=item["ticket"]) as source,
                    target.open("xb") as output,
                ):
                    target.chmod(0o600)
                    # read1 returns available TLS bytes instead of waiting for
                    # a full megabyte from a slowly interrupted connection.
                    while chunk := source.read1(65536):
                        if time.monotonic() >= transfer_deadline:
                            raise RuntimeUnavailable("Runner material transfer timed out")
                        size += len(chunk)
                        if size > item["size"]:
                            raise ValueError("Runner input exceeds registered size")
                        sha.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if size != item["size"] or sha.hexdigest() != item["sha256"]:
                    raise ValueError("Runner input digest mismatch")
            self._permitted(value)
            last_check, revoked = [0.0], [False]

            def cancelled():
                if time.monotonic() - last_check[0] >= 1:
                    last_check[0] = time.monotonic()
                    try:
                        self._permitted({**value, "files": value["files"][:1]})
                    except (PermissionError, RuntimeUnavailable, ValueError):
                        revoked[0] = True
                return revoked[0]

            path = inputs if value["package_set"] else next(inputs.iterdir())
            scanned = scan_isolated(
                path,
                image=self.config.image_id,
                timeout=self.config.timeout,
                metadata=value["operation"] == "inspect",
                cancelled=cancelled,
                run_root=operation / "scans",
                quota_bytes=MAX_DISK,
            )
            receipt = self._receipt(scanned["tools"]["isolation_receipt"], operation, request_id)
            if (
                not receipt["input_removed"]
                or not receipt["cleanup_verified"]
                or receipt["image_id"] != self.config.image_id
            ):
                raise ValueError("Runner cleanup receipt rejected")
            scanned["tools"]["isolation_receipt"] = "runner:" + request_id
            scanned["tools"]["runner_receipt"] = json.dumps(receipt, sort_keys=True)
            self._permitted(value)
            result = {
                "version": 1,
                "request_id": request_id,
                "result": scanned,
                "receipt": receipt,
                "error": None,
            }
        except ScanError as exc:
            if exc.cleanup_errors:
                self.faulted = True
            code = exc.code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", exc.code) else "SCAN_FAILED"
            result = {
                "version": 1,
                "request_id": request_id,
                "result": None,
                "receipt": self._receipt(exc.receipt, operation, request_id),
                "error": code,
            }
        except PermissionError:
            result = {
                "version": 1,
                "request_id": request_id,
                "result": None,
                "receipt": None,
                "error": "CANCELLED",
            }
        except RuntimeUnavailable:
            result = {
                "version": 1,
                "request_id": request_id,
                "result": None,
                "receipt": None,
                "error": "RUNNER_UNAVAILABLE",
            }
        except (ValueError, OSError):
            result = {
                "version": 1,
                "request_id": request_id,
                "result": None,
                "receipt": None,
                "error": "RUNNER_INPUT_REJECTED",
            }
        finally:
            # The isolated scanner has stopped its container before returning.
            # If cleanup is unproven it retains the workspace reservation and
            # Runner refuses reuse; startup recovery validates/stops its residue.
            if inputs.exists():
                try:
                    shutil.rmtree(inputs)
                except OSError:
                    self.faulted = True
                    raise RuntimeUnavailable("Runner input cleanup requires recovery") from None
        raw = json.dumps(result, separators=(",", ":"), allow_nan=False).encode()
        if len(raw) > 8 * 1024 * 1024:
            raise RuntimeUnavailable("Runner output exceeds limit")
        if self.faulted:
            raise RuntimeUnavailable("Runner cleanup requires recovery")
        scans = operation / "scans"
        if scans.exists() and any(scans.glob("*/reservation.json")):
            self.faulted = True
            raise RuntimeUnavailable("Runner reservation requires recovery")
        with self._database() as conn:
            conn.execute(
                "UPDATE operations SET state='DONE',result=? WHERE id=?", (raw, request_id)
            )
        shutil.rmtree(operation)
        return result


class RunnerHandler(PrivateHandler):
    def do_GET(self):
        if self.path != "/v1/health" or not self.authorized():
            self.reply(403, {"error": "RUNNER_REQUEST_REJECTED"})
            return
        if self.server.runner.faulted:
            self.reply(503, {"error": "RUNNER_UNAVAILABLE"})
            return
        # A healthy scanner without a functioning material gateway cannot
        # admit new work. Probe using the runner's own mTLS identity, not API
        # credentials, and keep the downstream check within the API budget.
        try:
            gateway = self.server.runner.gateway.json("/v1/health", timeout=0.7)
            if gateway != {"version": 1, "status": "ready"}:
                raise RuntimeUnavailable("Material gateway is unavailable")
        except (RuntimeUnavailable, PermissionError, OSError, ValueError, TypeError):
            self.reply(503, {"error": "RUNNER_UNAVAILABLE"})
            return
        self.reply(
            200,
            {"version": 1, "status": "ready", "image_id": self.server.runner.config.image_id},
        )

    def do_POST(self):
        try:
            if self.path != "/v1/run":
                self.reply(404, {"error": "UNKNOWN_RUNTIME_OPERATION"})
                return
            result = self.server.runner.run(self.body())
            self.reply(200, result)
        except PermissionError:
            self.reply(410, {"error": "RUNNER_PERMIT_UNAVAILABLE"})
        except (ValueError, TypeError, KeyError):
            self.reply(422, {"error": "RUNNER_MANIFEST_REJECTED"})
        except (RuntimeUnavailable, OSError, ScanError):
            self.reply(503, {"error": "RUNNER_UNAVAILABLE"})


class RunnerServer(PrivateServer):
    def service_actions(self):
        if time.monotonic() - self.last_prune < 30:
            return
        self.last_prune = time.monotonic()
        try:
            self.runner.prune()
        except (sqlite3.Error, OSError):
            # Stop admitting scans if retention cannot be maintained. Never
            # print private database paths or silently leave unbounded residue.
            self.runner.faulted = True


def create_runner_server(runner, address, tls, peers):
    server = RunnerServer(address, RunnerHandler, tls, peers)
    server.runner = runner
    server.last_prune = 0.0
    return server


def main():
    runner = server = None
    try:
        config = RunnerConfig(
            os.environ["PRIVACYTRACE_INSTANCE_ID"],
            os.environ["PRIVACYTRACE_RUNNER_IMAGE_ID"],
            Path(os.environ["PRIVACYTRACE_RUNNER_ROOT"]),
            int(os.environ.get("PRIVACYTRACE_RUNNER_TIMEOUT", "120")),
        )
        gateway = PrivateClient(
            os.environ["PRIVACYTRACE_GATEWAY_URL"],
            RuntimeTLS.from_env("PRIVACYTRACE_RUNNER_GATEWAY_TLS"),
            timeout=15,
        )
        runner = Runner(config, gateway)
        server = create_runner_server(
            runner,
            (os.environ["PRIVACYTRACE_RUNNER_BIND"], int(os.environ["PRIVACYTRACE_RUNNER_PORT"])),
            RuntimeTLS.from_env("PRIVACYTRACE_RUNNER_TLS"),
            os.environ["PRIVACYTRACE_RUNNER_PEERS"].split(","),
        )
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    except (ValueError, KeyError, OSError, ScanError):
        print('{"error":"RUNNER_UNAVAILABLE"}')
        return 1
    finally:
        if server:
            server.server_close()
        if runner:
            runner.close()


if __name__ == "__main__":
    raise SystemExit(main())
