"""Bounded sampling of this laboratory's scanner cgroups and private volumes."""

import json
import threading
from pathlib import Path

from .provision import execute


def disk_bytes(root):
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())


class Sampler:
    def __init__(self, lab):
        self.lab = lab
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.samples = 0
        self.scanner_peak = 0
        self.workspace_peak = 0
        self.material_peak = 0
        self.scanner_concurrency = 0
        self.failures = 0
        identifier = lab.run("ps", "-q", "api")
        item = json.loads(execute(["docker", "inspect", identifier]))[0]
        self.materials = Path(
            next(m["Source"] for m in item["Mounts"] if m["Destination"] == "/var/lib/privacytrace")
        )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise RuntimeError("capacity sampler did not stop")

    def _loop(self):
        while not self.stop.is_set():
            try:
                self.workspace_peak = max(self.workspace_peak, disk_bytes(self.lab.root / "runner"))
                self.material_peak = max(self.material_peak, disk_bytes(self.materials))
                ids = execute(
                    ["docker", "ps", "-q", "--filter", "label=privacytrace.run"], timeout=10
                ).splitlines()
                owned = 0
                if ids:
                    for item in json.loads(execute(["docker", "inspect", *ids], timeout=10)):
                        mounts = item["Mounts"]
                        if len(mounts) != 1 or not Path(mounts[0]["Source"]).is_relative_to(
                            self.lab.root / "runner"
                        ):
                            continue
                        owned += 1
                        pid = item["State"]["Pid"]
                        if not pid:
                            continue
                        for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
                            if line.startswith("0::"):
                                root = Path("/sys/fs/cgroup")
                                path = (root / line.split("::", 1)[1].lstrip("/")).resolve()
                                if path.is_relative_to(root):
                                    peak = int((path / "memory.peak").read_text().strip())
                                    self.scanner_peak = max(self.scanner_peak, peak)
                self.scanner_concurrency = max(self.scanner_concurrency, owned)
                self.samples += 1
            except (OSError, ValueError, RuntimeError):
                self.failures += 1
            self.stop.wait(0.1)

    def result(self):
        return {
            "sampling_interval_s": 0.1,
            "samples": self.samples,
            "transient_sampling_failures": self.failures,
            "scanner_sampled_peak_memory_bytes": self.scanner_peak or None,
            "scanner_sampled_peak_concurrency": self.scanner_concurrency,
            "runner_sampled_peak_disk_bytes": self.workspace_peak,
            "materials_sampled_peak_disk_bytes": self.material_peak,
        }
