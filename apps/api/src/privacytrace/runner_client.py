"""Control-plane client for a fixed authenticated runner; never imports Docker commands."""

import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from .runner_protocol import manifest
from .runtime_materials import RuntimeMaterials
from .runtime_tls import PrivateClient, RuntimeTLS, RuntimeUnavailable
from .scan_workspace import ScanError


class RunnerScanError(ScanError):
    def __init__(self, code, receipt, request_id):
        super().__init__(code, "Dedicated runner reported a bounded scan failure")
        self.runtime_receipt = receipt
        self.receipt = "runner:" + request_id if receipt else None

    def record(self):
        value = super().record()
        if self.runtime_receipt is not None:
            value.setdefault("tools", {})["runner_receipt"] = json.dumps(
                self.runtime_receipt, sort_keys=True
            )
        return value


class RunnerClient:
    def __init__(self, store, remote, image_id, materials):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise ValueError("Expected immutable runner image required")
        self.store, self.remote, self.image_id, self.materials = store, remote, image_id, materials

    @classmethod
    def from_env(cls, store):
        try:
            return cls(
                store,
                PrivateClient(
                    os.environ["PRIVACYTRACE_RUNNER_URL"],
                    RuntimeTLS.from_env("PRIVACYTRACE_CONTROL_TLS"),
                ),
                os.environ["PRIVACYTRACE_RUNNER_IMAGE_ID"],
                RuntimeMaterials.from_env(store),
            )
        except (KeyError, OSError, TypeError):
            raise ValueError("Private runtime runner configuration required") from None

    def _response(self, value):
        response = self.remote.json("/v1/run", data=manifest(value))
        try:
            if (
                type(response) is not dict
                or set(response) != {"version", "request_id", "result", "receipt", "error"}
                or type(response["version"]) is not int
                or response["version"] != 1
                or response["request_id"] != value["request_id"]
            ):
                raise ValueError
            error = response["error"]
            if error is not None:
                if type(error) is not str or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error):
                    raise ValueError
                if error == "RUNNER_UNAVAILABLE":
                    raise RuntimeUnavailable("Private runner unavailable")
                receipt = response["receipt"]
                if receipt is not None and (
                    type(receipt) is not dict or receipt.get("request_id") != value["request_id"]
                ):
                    raise ValueError
                raise RunnerScanError(error, receipt, value["request_id"])
            receipt, result = response["receipt"], response["result"]
            if type(receipt) is not dict or type(result) is not dict:
                raise ValueError
            isolation = receipt["isolation"]
            if (
                receipt["request_id"] != value["request_id"]
                or receipt["image_id"] != self.image_id
                or receipt["user"] != "65534:65534"
                or receipt["input_removed"] is not True
                or receipt["cleanup_verified"] is not True
                or isolation["NetworkMode"] != "none"
                or isolation["ReadonlyRootfs"] is not True
                or isolation["Privileged"] is not False
                or isolation["Memory"] != 1073741824
                or isolation["MemorySwap"] != 1073741824
                or isolation["NanoCpus"] != 1000000000
                or isolation["PidsLimit"] != 32
                or "ALL" not in [v.upper() for v in isolation["CapDrop"]]
                or isolation["CapAdd"]
                or isolation["SecurityOpt"] != ["no-new-privileges:true"]
                or receipt["mounts"] != [{"destination": "/input/sample.apk", "read_only": True}]
            ):
                raise ValueError
            if result["tools"].get("worker_image") != self.image_id:
                raise ValueError
            return result
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ScanError("WORKER_INVALID_OUTPUT", "Dedicated runner response rejected") from None

    def inspect_metadata(self, path, *, timeout=120):
        # Called only by trusted intake code with its server-created upload path.
        path = Path(path).absolute()
        draft_id = path.relative_to((self.store.root / "web").absolute()).parts[0]
        file = self.materials.register(path, draft_id=draft_id)
        value = {
            "version": 1,
            "operation": "inspect",
            "request_id": str(uuid4()),
            "instance_id": self.store.instance_id,
            "scope_id": draft_id,
            "owner": None,
            "fence": 0,
            "package_set": False,
            "files": [file],
        }
        try:
            result = self._response(value)
        except (RuntimeUnavailable, PermissionError):
            raise ScanError(
                "ISOLATION_UNAVAILABLE", "Dedicated metadata inspection unavailable"
            ) from None
        return result

    def scanner(self, draft, lease):
        def scan(path, *, timeout=120, cancelled=lambda: False):
            if cancelled():
                raise ScanError("CANCELLED", "Analysis cancelled")
            directory = self.store.root / "web" / draft["id"]
            if Path(path).absolute() not in {directory / "input.apk", directory / "packages"}:
                raise ValueError("Runtime scanner input identity changed")
            if draft.get("package_set") is None:
                files = [
                    self.materials.register(
                        directory / "input.apk",
                        draft_id=draft["id"],
                        lease=lease,
                        expected_sha256=draft["apk_sha256"],
                    )
                ]
            else:
                package = draft["package_set"]
                files = [
                    self.materials.register(
                        directory / "packages" / part["file_name"],
                        draft_id=draft["id"],
                        lease=lease,
                        expected_sha256=part["sha256"],
                    )
                    for part in [package["base"], *package["splits"]]
                ]
            value = {
                "version": 1,
                "operation": "scan",
                "request_id": str(
                    uuid5(
                        UUID(self.store.instance_id),
                        f"scan:{lease.job_id}:{lease.fence}:{lease.owner}",
                    )
                ),
                "instance_id": self.store.instance_id,
                "scope_id": lease.job_id,
                "owner": str(lease.owner),
                "fence": lease.fence,
                "package_set": draft.get("package_set") is not None,
                "files": files,
            }
            try:
                return self._response(value)
            except PermissionError:
                # The database remains the final arbiter after revocation.
                from .postgres_execution import LeaseLost

                raise LeaseLost("Execution material permit unavailable") from None

        return scan
