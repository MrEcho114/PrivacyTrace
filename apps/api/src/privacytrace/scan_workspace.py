"""Owned per-run input lifecycle and cross-process cumulative disk budget.

No historical run is deleted automatically. Active reservations include room for
the final receipt; stale reservations after a hard crash remain charged.
"""

import json
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

DEFAULT_QUOTA = 1024 * 1024 * 1024
AUDIT_BUDGET = 256 * 1024


class ScanError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.receipt = None
        self.cleanup_errors = []
        self.cleanup_only = False

    def record(self):
        primary = None if self.cleanup_only else {"code": self.code, "message": str(self)}
        record = {
            "errors": ([primary] if primary else []) + self.cleanup_errors,
            "primary_error": primary,
            "cleanup_errors": self.cleanup_errors,
        }
        if self.receipt:
            record["tools"] = {"isolation_receipt": self.receipt}
        return record


def safe_path(path):
    if any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)
    ):
        raise ScanError("UNSAFE_WORKSPACE", "Run storage cannot contain links")


@contextmanager
def storage_lock(root):
    safe_path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        if root.stat().st_uid != os.getuid():
            raise ScanError("UNSAFE_WORKSPACE", "Run storage must be owned by the current user")
        root.chmod(0o700)
    path = root / ".quota.lock"
    safe_path(path)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    locked = False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ScanError("UNSAFE_WORKSPACE", "Run storage lock must be a regular file")
        deadline = time.monotonic() + 5
        while not locked:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise ScanError("STORAGE_BUSY", "Run storage lock timed out") from exc
                time.sleep(0.02)
        if info.st_size == 0:
            os.write(fd, b"0")
        safe_path(path)
        current = path.stat(follow_symlinks=False)
        if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
            raise ScanError("UNSAFE_WORKSPACE", "Run storage lock changed")
        yield
    finally:
        if locked:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def disk_usage(root):
    total = 0
    for child in root.iterdir():
        safe_path(child)
        if child.is_dir():
            actual = 0
            for path in child.rglob("*"):
                safe_path(path)
                if path.is_file():
                    actual += path.stat().st_size
                elif not path.is_dir():
                    raise ScanError("UNSAFE_WORKSPACE", "Unsupported run storage entry")
            reservation = child / "reservation.json"
            if reservation.exists():
                try:
                    reserved = json.loads(reservation.read_text(encoding="utf-8"))["bytes"]
                    if type(reserved) is not int or reserved < 0:
                        raise ValueError
                except (ValueError, KeyError, TypeError) as exc:
                    raise ScanError("UNSAFE_WORKSPACE", "Invalid disk reservation") from exc
                actual = max(actual, reserved)
            total += actual
        elif child.is_file():
            total += child.stat().st_size
        else:
            raise ScanError("UNSAFE_WORKSPACE", "Unsupported run storage entry")
    return total


class ScanWorkspace:
    def __init__(self, root, quota, input_size):
        self.root = Path(root).absolute()
        self.run_id = uuid4().hex
        self.path = self.root / self.run_id
        with storage_lock(self.root):
            if disk_usage(self.root) + input_size + AUDIT_BUDGET > quota:
                raise ScanError("STORAGE_QUOTA_EXCEEDED", "Cumulative run storage budget exceeded")
            self.path.mkdir(mode=0o700)
            self.reservation = self.path / "reservation.json"
            pending = self.path / ".reservation.tmp"
            try:
                with pending.open("xb") as file:
                    file.write(json.dumps({"bytes": input_size + AUDIT_BUDGET}).encode("utf-8"))
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(pending, self.reservation)
            except OSError as exc:
                error = ScanError("STORAGE_PREPARATION_FAILED", "Cannot reserve run storage")
                try:
                    pending.unlink(missing_ok=True)
                    self.path.rmdir()  # Only this invocation's new, empty directory.
                except OSError:
                    error.cleanup_errors.append(
                        {
                            "code": "RESERVATION_CLEANUP_FAILED",
                            "message": "Cannot remove incomplete reservation",
                        }
                    )
                raise error from exc
        self.input = self.path / "input.apk"
        self.receipt = self.path / "isolation.json"

    def remove_input(self):
        safe_path(self.input)
        if self.input.exists():
            self.input.chmod(0o600)  # Clear Windows read-only attribute before unlink.
            self.input.unlink()
        return not self.input.exists()

    def write_receipt(self, proof):
        data = json.dumps(proof, indent=2).encode("utf-8")
        if len(data) > AUDIT_BUDGET:
            raise ScanError("RECEIPT_TOO_LARGE", "Audit receipt exceeds reserved size")
        safe_path(self.receipt)
        self.receipt.write_bytes(data)
        self.receipt.chmod(0o600)

    def release(self):
        # Only release after input removal and receipt publication. A crash or a
        # cleanup failure keeps the reservation charged rather than hiding usage.
        with storage_lock(self.root):
            safe_path(self.reservation)
            self.reservation.unlink()
