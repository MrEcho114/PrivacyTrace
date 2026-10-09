"""Host orchestrator. APK parsing is only allowed inside an inspected container."""

import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from .scan_workspace import DEFAULT_QUOTA, ScanError, ScanWorkspace

ROOT = Path(__file__).resolve().parents[4]
MAX_INPUT = 150 * 1024 * 1024
MAX_STREAM = 4 * 1024 * 1024


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
    local = [
        "env",
        "-u",
        "DOCKER_HOST",
        "-u",
        "DOCKER_CONTEXT",
        "-u",
        "DOCKER_TLS_VERIFY",
        "-u",
        "DOCKER_CERT_PATH",
        "-u",
        "DOCKER_CONFIG",
        "docker",
        "--host=unix:///var/run/docker.sock",
    ]
    return ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", *local] if os.name == "nt" else local


def command(args, timeout=30):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanError(
            "ISOLATION_UNAVAILABLE", "Container runtime unavailable or timed out"
        ) from exc
    if result.returncode:
        raise ScanError("CONTAINER_ERROR", "Local container command failed")
    return result.stdout.decode("utf-8")


def scan_isolated(
    path: Path,
    timeout=120,
    cancelled=lambda: False,
    image="privacytrace-worker:s1",
    probe=False,
    inventory=False,
    run_root=None,
    quota_bytes=None,
):
    """Only the owned immutable copy is mounted; default retention is zero.

    Reserve cumulative space before copying; keep a bounded audit receipt but no
    APK or raw worker logs after a normal exit. Hard crashes require manual repair.
    """
    path = validate_input(path)
    if not 1 <= timeout <= 180:
        raise ScanError("INVALID_TIMEOUT", "Timeout must be between 1 and 180 seconds")
    try:
        quota = int(
            quota_bytes
            if quota_bytes is not None
            else os.getenv("PRIVACYTRACE_APK_RUN_QUOTA_BYTES", DEFAULT_QUOTA)
        )
        if quota <= 0:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise ScanError("INVALID_QUOTA", "Run storage budget must be a positive integer") from exc
    root = run_root or os.getenv("PRIVACYTRACE_APK_RUN_ROOT") or ROOT / "tmp/apk-runs"
    workspace = None
    process = None
    threads = []
    docker = None
    name = None
    created = False
    attempted = False
    primary = None
    cleanup_errors = []
    output = None
    phase = "PREPARING"
    proof = {
        "apk_sha256": None,
        "input_retention": "DELETE_ON_EXIT",
        "input_removed": False,
        "container_created": False,
        "cleanup_verified": True,
        "primary_error": None,
        "cleanup_errors": [],
        "quota_bytes": quota,
        "timeout_seconds": timeout,
    }
    overflow = threading.Event()
    streams = {"stdout": bytearray(), "stderr": bytearray()}

    def collect(stream, target):
        try:
            while chunk := stream.read(65536):
                remaining = MAX_STREAM - len(target)
                target.extend(chunk[: max(0, remaining)])
                if len(chunk) > remaining:
                    overflow.set()
        finally:
            stream.close()

    def cleanup_error(error, fallback):
        cleanup_errors.append(
            {
                "code": getattr(error, "code", fallback),
                "message": str(error)
                if isinstance(error, ScanError)
                else "Owned run cleanup failed",
            }
        )

    try:
        original = path.stat()
        workspace = ScanWorkspace(root, quota, original.st_size)
        run_dir, copied = workspace.path, workspace.input
        phase = "COPYING"
        digest_builder = hashlib.sha256()
        with path.open("rb") as src, copied.open("xb") as dst:
            total = 0
            while chunk := src.read(1024 * 1024):
                if cancelled():
                    raise ScanError("CANCELLED", "Analysis cancelled by user")
                total += len(chunk)
                if total > MAX_INPUT:
                    raise ScanError("INPUT_TOO_LARGE", "Input grew beyond maximum while copying")
                if total > original.st_size:
                    raise ScanError("INPUT_CHANGED", "Input changed while copying")
                dst.write(chunk)
                digest_builder.update(chunk)
        current = path.stat()
        if (
            total != original.st_size
            or current.st_size != original.st_size
            or current.st_mtime_ns != original.st_mtime_ns
        ):
            raise ScanError("INPUT_CHANGED", "Input changed while copying")
        digest = digest_builder.hexdigest()
        proof["apk_sha256"] = digest
        copied.chmod(0o444)
        if cancelled():
            raise ScanError("CANCELLED", "Analysis cancelled by user")
        phase = "PREFLIGHT"
        mount = str(copied)
        if os.name == "nt":
            mount = command(
                ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-u", mount]
            ).strip()
        if "," in mount:
            raise ScanError("UNSAFE_WORKSPACE", "Docker mount path cannot contain a comma")
        docker = docker_prefix()
        client_config = run_dir / "docker-client"
        client_config.mkdir(mode=0o700)
        config_mount = str(client_config)
        if os.name == "nt":
            config_mount = command(
                ["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-u", config_mount]
            ).strip()
        docker += ["--config", config_mount]
        image_id = command([*docker, "image", "inspect", image, "--format", "{{.Id}}"]).strip()
        if not image_id.startswith("sha256:"):
            raise ScanError("UNPINNED_IMAGE", "Worker must resolve to an immutable local image ID")
        name = "privacytrace-" + workspace.run_id
        proof.update(container=name, image_id=image_id, cleanup_verified=False)
        attempted = True
        phase = "RUNNING"
        command(
            [
                *docker,
                "create",
                "--pull=never",
                "--name",
                name,
                "--label",
                "privacytrace.run=" + workspace.run_id,
                "--network=none",
                "--read-only",
                "--user=65534:65534",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--memory=1g",
                "--memory-swap=1g",
                "--cpus=1",
                "--pids-limit=32",
                "--log-driver=none",
                "--shm-size=8m",
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,nr_inodes=4096",
                "--mount",
                f"type=bind,source={mount},target=/input/sample.apk,readonly",
                image_id,
                "/input/sample.apk",
                *(["--probe"] if probe else ["--jadx", "jadx"]),
                *(["--inventory"] if inventory and not probe else []),
            ]
        )
        created = True
        proof["container_created"] = True
        isolation = json.loads(command([*docker, "inspect", name]))[0]
        config, host = isolation["Config"], isolation["HostConfig"]
        mounts = isolation["Mounts"]
        if not (
            config["User"] == "65534:65534"
            and host["NetworkMode"] == "none"
            and host["ReadonlyRootfs"]
            and host["Memory"] == 1073741824
            and host["MemorySwap"] == 1073741824
            and host["NanoCpus"] == 1000000000
            and host["PidsLimit"] == 32
            and host["LogConfig"]["Type"] == "none"
            and "ALL" in [v.upper() for v in host["CapDrop"]]
            and host["SecurityOpt"] == ["no-new-privileges:true"]
            and host["Privileged"] is False
            and not host["CapAdd"]
            and not host["Devices"]
            and not host["DeviceRequests"]
            and not host["DeviceCgroupRules"]
            and not host["VolumesFrom"]
            and host["PidMode"] == ""
            and host["IpcMode"] == "private"
            and host["CgroupnsMode"] == "private"
            and host["ShmSize"] == 8388608
            and host["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,nodev,size=16m,nr_inodes=4096"}
            and len(mounts) == 1
            and mounts[0]["Destination"] == "/input/sample.apk"
            and mounts[0]["RW"] is False
            and mounts[0]["Source"] == mount
            and mounts[0]["Propagation"] == "rprivate"
        ):
            raise ScanError("ISOLATION_REJECTED", "Effective container settings failed inspection")
        proof.update(
            {
                "container": name,
                "image_id": image_id,
                "apk_sha256": digest,
                "host_config": host,
                "user": config["User"],
                "mounts": mounts,
                "timeout_seconds": timeout,
                "output_byte_limit_per_stream": MAX_STREAM,
                "cleanup_verified": False,
            }
        )
        workspace.write_receipt(proof)
        process = subprocess.Popen(
            [*docker, "start", "--attach", name], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        threads = [
            threading.Thread(target=collect, args=(stream, streams[key]), daemon=True)
            for key, stream in (("stdout", process.stdout), ("stderr", process.stderr))
        ]
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
            raise ScanError(errors[0]["code"], "Worker reported a structured failure")
        if (
            not isinstance(output.get("apk_sha256"), str)
            or not isinstance(output.get("tools"), dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in output["tools"].items()
            )
        ):
            raise ScanError("WORKER_INVALID_OUTPUT", "Worker hash or tools have invalid structure")
        if (
            hashlib.sha256(copied.read_bytes()).hexdigest() != digest
            or output["apk_sha256"] != digest
        ):
            raise ScanError("INPUT_CHANGED", "Worker output hash differs from immutable input copy")
        output["tools"]["worker_image"] = image_id
        output["tools"]["isolation_receipt"] = str(workspace.receipt)

    except KeyboardInterrupt:
        primary = ScanError("CANCELLED", "Analysis cancelled by user")
    except ScanError as exc:
        primary = exc
        cleanup_errors.extend(exc.cleanup_errors)
    except Exception:
        primary = ScanError(
            "COPY_FAILED" if phase == "COPYING" else "ISOLATION_UNAVAILABLE",
            "Input copy failed" if phase == "COPYING" else "Isolation operation failed",
        )
    finally:
        # Cleanup is independent of primary diagnostics, including preflight faults.
        if process and process.poll() is None:
            try:
                process.kill()
                process.wait(timeout=10)
            except Exception as exc:
                cleanup_error(exc, "PROCESS_CLEANUP_FAILED")
        for thread in threads:
            thread.join(timeout=5)
        if attempted:
            try:
                if not created:
                    # create may have succeeded before the CLI transport failed.
                    # Inspect ownership before deleting anything with this name.
                    check = subprocess.run(
                        [*docker, "inspect", name], capture_output=True, timeout=10
                    )
                    absent = (
                        b"no such object" in check.stderr.lower()
                        or b"no such container" in check.stderr.lower()
                    )
                    if check.returncode and absent and name.encode() in check.stderr:
                        proof["cleanup_verified"] = True
                    elif check.returncode == 0:
                        info = json.loads(check.stdout)[0]
                        if (
                            info["Config"].get("Labels", {}).get("privacytrace.run")
                            != workspace.run_id
                        ):
                            raise ScanError(
                                "CLEANUP_UNVERIFIED", "Container ownership could not be verified"
                            )
                        created = True
                    else:
                        raise ScanError(
                            "CLEANUP_UNVERIFIED", "Cannot determine whether worker was created"
                        )
                if created:
                    command([*docker, "rm", "--force", name])
                    gone = subprocess.run(
                        [*docker, "inspect", name], capture_output=True, timeout=10
                    )
                    absent = (
                        b"no such object" in gone.stderr.lower()
                        or b"no such container" in gone.stderr.lower()
                    )
                    if gone.returncode == 0 or not absent or name.encode() not in gone.stderr:
                        raise ScanError("CLEANUP_UNVERIFIED", "Cannot verify worker removal")
                    proof["cleanup_verified"] = True
            except Exception as exc:
                cleanup_error(exc, "CLEANUP_UNVERIFIED")
        if workspace is not None:
            try:
                proof["input_removed"] = workspace.remove_input()
            except Exception as exc:
                cleanup_error(exc, "INPUT_CLEANUP_FAILED")
            proof["primary_error"] = (
                {"code": primary.code, "message": str(primary)} if primary else None
            )
            proof["cleanup_errors"] = cleanup_errors
            receipt_saved = False
            try:
                workspace.write_receipt(proof)
                receipt_saved = True
            except Exception as exc:
                cleanup_error(exc, "RECEIPT_WRITE_FAILED")
            if (
                receipt_saved
                and proof["input_removed"]
                and proof["cleanup_verified"]
                and not cleanup_errors
            ):
                try:
                    workspace.release()
                except Exception as exc:
                    cleanup_error(exc, "RESERVATION_RELEASE_FAILED")
            if cleanup_errors:
                # Late cleanup faults must be visible in the persisted receipt too.
                proof["cleanup_errors"] = cleanup_errors
                try:
                    workspace.write_receipt(proof)
                except Exception:
                    pass  # The structured CLI result still contains this failure.
    if primary or cleanup_errors:
        error = primary or ScanError(cleanup_errors[0]["code"], cleanup_errors[0]["message"])
        error.cleanup_errors = cleanup_errors
        error.cleanup_only = primary is None
        if workspace is not None:
            error.receipt = str(workspace.receipt)
        raise error
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--image", default="privacytrace-worker:s1")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--quota-bytes", type=int)
    parser.add_argument("--cancel-file", type=Path, help="Local cancellation sentinel")
    args = parser.parse_args()
    try:
        output = scan_isolated(
            args.apk,
            timeout=args.timeout,
            image=args.image,
            probe=args.probe,
            inventory=args.inventory,
            run_root=args.run_root,
            quota_bytes=args.quota_bytes,
            cancelled=lambda: args.cancel_file is not None and args.cancel_file.exists(),
        )
        print(json.dumps(output, ensure_ascii=True))
        return 0
    except ScanError as error:
        print(json.dumps(error.record()))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"errors": [{"code": "CANCELLED", "message": "Analysis cancelled"}]}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
