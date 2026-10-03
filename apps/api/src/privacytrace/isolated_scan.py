"""Host orchestrator. APK parsing is only allowed inside an inspected container."""

import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[4]
MAX_INPUT = 150 * 1024 * 1024
MAX_STREAM = 4 * 1024 * 1024


class ScanError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.receipt = None


def validate_input(path: Path) -> Path:
    if not path.exists():
        raise ScanError("INPUT_NOT_FOUND", "APK input does not exist")
    if not path.is_file() or any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)()
        for p in (path.absolute(), *path.absolute().parents)
    ):
        raise ScanError("UNSAFE_INPUT", "Input must be a regular file, not a link")
    if path.stat().st_size > MAX_INPUT:
        raise ScanError("INPUT_TOO_LARGE", "APK input exceeds 150 MiB")
    return path.absolute()


def docker_prefix():
    # A user config or environment must not redirect APKs to a remote daemon.
    local = ["env", "-u", "DOCKER_HOST", "-u", "DOCKER_CONTEXT", "-u", "DOCKER_TLS_VERIFY",
             "-u", "DOCKER_CERT_PATH", "-u", "DOCKER_CONFIG", "docker",
             "--host=unix:///var/run/docker.sock"]
    return ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", *local] if os.name == "nt" else local


def command(args, timeout=30):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanError(
            "ISOLATION_UNAVAILABLE", "Container runtime unavailable or timed out"
        ) from exc
    if result.returncode:
        raise ScanError("CONTAINER_ERROR", result.stderr.decode("utf-8", errors="replace")[:2000])
    return result.stdout.decode("utf-8")


def scan_isolated(path: Path, timeout=120, cancelled=lambda: False,
                  image="privacytrace-worker:s1", probe=False, inventory=False):
    """Copy bytes, inspect effective isolation, then parse with bounded stdout/stderr.

    No shell interpretation; the only mount is an immutable input copy. No output
    bind or Docker log file: writes are limited to memory-accounted temporary FS.
    Container cleanup targets only this invocation's unique name.
    """
    path = validate_input(path)
    if not 1 <= timeout <= 180:
        raise ScanError("INVALID_TIMEOUT", "Timeout must be between 1 and 180 seconds")
    run_dir = ROOT / "tmp" / "apk-runs" / uuid4().hex
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
           for p in (run_dir, *run_dir.parents)):
        raise ScanError("UNSAFE_WORKSPACE", "Isolation input directory cannot contain links")
    run_dir.mkdir(parents=True)
    copied = run_dir / "input.apk"
    with path.open("rb") as src, copied.open("xb") as dst:
        total = 0
        while chunk := src.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_INPUT:
                raise ScanError("INPUT_TOO_LARGE", "Input grew beyond the maximum while copying")
            dst.write(chunk)
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()
    copied.chmod(0o444)
    mount = str(copied)
    if os.name == "nt":
        mount = command(["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-u", mount]).strip()
    if "," in mount:
        raise ScanError("UNSAFE_WORKSPACE", "Docker mount path cannot contain a comma")
    docker = docker_prefix()
    # Do not load the user's Docker config (auth, proxies, extra contexts).
    client_config = run_dir / "docker-client"
    client_config.mkdir()
    config_mount = str(client_config)
    if os.name == "nt":
        config_mount = command(
            ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-u", config_mount]
        ).strip()
    docker += ["--config", config_mount]
    # Resolve the built image once; tag changes cannot affect this invocation.
    image_id = command([*docker, "image", "inspect", image, "--format", "{{.Id}}"]).strip()
    if not image_id.startswith("sha256:"):
        raise ScanError("UNPINNED_IMAGE", "Worker must resolve to an immutable local image ID")
    name = "privacytrace-" + uuid4().hex
    isolation = None
    process = None
    created = False
    overflow = threading.Event()
    streams = {"stdout": bytearray(), "stderr": bytearray()}

    def collect(stream, target):
        try:
            while chunk := stream.read(65536):
                remaining = MAX_STREAM - len(target)
                target.extend(chunk[:max(0, remaining)])
                if len(chunk) > remaining:
                    overflow.set()
        finally:
            stream.close()

    try:
        command([*docker, "create", "--pull=never", "--name", name,
                 "--network=none", "--read-only", "--user=65534:65534", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges:true", "--memory=1g", "--memory-swap=1g",
                 "--cpus=1", "--pids-limit=32", "--log-driver=none", "--shm-size=8m",
                 "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,nr_inodes=4096",
                 "--mount", f"type=bind,source={mount},target=/input/sample.apk,readonly",
                 image_id, "/input/sample.apk",
                 *(["--probe"] if probe else ["--jadx", "jadx"]),
                 *(["--inventory"] if inventory and not probe else [])])
        created = True
        isolation = json.loads(command([*docker, "inspect", name]))[0]
        config, host = isolation["Config"], isolation["HostConfig"]
        mounts = isolation["Mounts"]
        if not (
            config["User"] == "65534:65534" and host["NetworkMode"] == "none"
            and host["ReadonlyRootfs"] and host["Memory"] == 1073741824
            and host["MemorySwap"] == 1073741824 and host["NanoCpus"] == 1000000000
            and host["PidsLimit"] == 32 and host["LogConfig"]["Type"] == "none"
            and "ALL" in [v.upper() for v in host["CapDrop"]]
            and host["SecurityOpt"] == ["no-new-privileges:true"]
            and host["Privileged"] is False and not host["CapAdd"]
            and not host["Devices"] and not host["DeviceRequests"]
            and not host["DeviceCgroupRules"] and not host["VolumesFrom"]
            and host["PidMode"] == "" and host["IpcMode"] == "private"
            and host["CgroupnsMode"] == "private"
            and host["ShmSize"] == 8388608
            and host["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,nodev,size=16m,nr_inodes=4096"}
            and len(mounts) == 1 and mounts[0]["Destination"] == "/input/sample.apk"
            and mounts[0]["RW"] is False and mounts[0]["Source"] == mount
            and mounts[0]["Propagation"] == "rprivate"
        ):
            raise ScanError("ISOLATION_REJECTED", "Effective container settings failed inspection")
        proof = {"container": name, "image_id": image_id, "apk_sha256": digest,
                 "host_config": host, "user": config["User"], "mounts": mounts,
                 "timeout_seconds": timeout, "output_byte_limit_per_stream": MAX_STREAM,
                 "cleanup_verified": False}
        proof_path = run_dir / "isolation.json"
        proof_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
        process = subprocess.Popen([*docker, "start", "--attach", name],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threads = [threading.Thread(target=collect, args=(stream, streams[key]), daemon=True)
                   for key, stream in (("stdout", process.stdout), ("stderr", process.stderr))]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            if cancelled():
                raise ScanError("CANCELLED", "Analysis cancelled by user")
            if overflow.is_set():
                raise ScanError("OUTPUT_LIMIT", "Worker output exceeded the bounded capture limit")
            if time.monotonic() >= deadline:
                raise ScanError("TIMEOUT", "Isolated scan exceeded its wall-clock time limit")
            time.sleep(0.1)
        for thread in threads:
            thread.join(timeout=5)
        if overflow.is_set():
            raise ScanError("OUTPUT_LIMIT", "Worker output exceeded the bounded capture limit")
        raw = bytes(streams["stdout"])
        (run_dir / "stdout.json").write_bytes(raw)
        (run_dir / "stderr.log").write_bytes(streams["stderr"])
        try:
            output = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ScanError(
                "WORKER_INVALID_OUTPUT", "Worker did not produce a JSON record"
            ) from exc
        if not isinstance(output, dict):
            raise ScanError("WORKER_INVALID_OUTPUT", "Worker JSON must be an object")
        errors = output.get("errors", [])
        if not isinstance(errors, list) or any(
            not isinstance(error, dict)
            or not isinstance(error.get("code"), str)
            or not isinstance(error.get("message"), str)
            for error in errors
        ):
            raise ScanError("WORKER_INVALID_OUTPUT", "Worker errors have invalid structure")
        if process.returncode:
            errors = errors or [{"code": "WORKER_FAILED", "message": "Worker exited"}]
            raise ScanError(errors[0]["code"], errors[0]["message"])
        if (not isinstance(output.get("apk_sha256"), str)
                or not isinstance(output.get("tools"), dict)
                or any(not isinstance(key, str) or not isinstance(value, str)
                       for key, value in output["tools"].items())):
            raise ScanError("WORKER_INVALID_OUTPUT", "Worker hash or tools have invalid structure")
        if (hashlib.sha256(copied.read_bytes()).hexdigest() != digest
                or output["apk_sha256"] != digest):
            raise ScanError("INPUT_CHANGED", "Worker output hash differs from immutable input copy")
        output["tools"]["worker_image"] = image_id
        output["tools"]["isolation_receipt"] = str(run_dir.relative_to(ROOT) / "isolation.json")
        return output
    except KeyboardInterrupt as exc:
        error = ScanError("CANCELLED", "Analysis cancelled by user")
        if isolation is not None and 'proof_path' in locals():
            error.receipt = str(proof_path.relative_to(ROOT))
        raise error from exc
    except ScanError as exc:
        if isolation is not None and 'proof_path' in locals():
            exc.receipt = str(proof_path.relative_to(ROOT))
        raise
    finally:
        # Never operate on other containers or stop/change the Docker daemon.
        try:
            if created:
                command([*docker, "rm", "--force", name])
                if isolation is not None and 'proof' in locals():
                    try:
                        gone = subprocess.run(
                            [*docker, "inspect", name], capture_output=True, timeout=10
                        )
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        error = ScanError("CLEANUP_UNVERIFIED", "Cannot verify worker removal")
                        error.receipt = str(proof_path.relative_to(ROOT))
                        raise error from exc
                    absent = (b"no such object" in gone.stderr.lower()
                              or b"no such container" in gone.stderr.lower())
                    if gone.returncode == 0 or not absent or name.encode() not in gone.stderr:
                        raise ScanError("CLEANUP_UNVERIFIED", "Cannot verify worker removal")
                    proof["cleanup_verified"] = True
                    proof_path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--image", default="privacytrace-worker:s1")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--inventory", action="store_true")
    args = parser.parse_args()
    try:
        output = scan_isolated(args.apk, timeout=args.timeout, image=args.image,
                               probe=args.probe, inventory=args.inventory)
        print(json.dumps(output, ensure_ascii=True))
        return 0
    except ScanError as error:
        record = {"errors": [{"code": error.code, "message": str(error)}]}
        if error.receipt:
            record["tools"] = {"isolation_receipt": error.receipt}
        print(json.dumps(record))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"errors": [{"code": "CANCELLED", "message": "Analysis cancelled"}]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
