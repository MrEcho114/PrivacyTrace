"""Acceptance in a fresh test container with --network=none; no repository mount."""

import hashlib
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def main():
    package = Path("/package")
    assert sorted(path.name for path in Path("/sys/class/net").iterdir()) == ["lo"]
    connection = socket.socket()
    connection.settimeout(1)
    try:
        connection.connect(("1.1.1.1", 443))
    except OSError:
        external_network_blocked = True
    else:
        raise AssertionError("External network must be unavailable")
    finally:
        connection.close()
    viewer = subprocess.Popen(
        ["python", "-B", str(package / "viewer.py"), "--port", "8765"]
    )
    try:
        for attempt in range(100):
            try:
                with urllib.request.urlopen(
                    "http://127.0.0.1:8765/api/v1/jobs"
                ) as response:
                    jobs = json.load(response)["jobs"]
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("Independent viewer did not start")
        assert len(jobs) == 6
        for job in jobs:
            with urllib.request.urlopen(
                "http://127.0.0.1:8765/api/v1/jobs/" + job["id"] + "/report"
            ) as response:
                report = json.load(response)
            assert report["job"]["input_mode"] == "CONTROLLED_APK"
            assert report["tools"]["presentation_mode"] == "OFFLINE_REPLAY"
            assert report["tools"]["offline_package_built_at"]
        process = subprocess.run(
            ["node", "/offline-browser.cjs"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if process.returncode:
            raise RuntimeError(process.stderr[-3000:])
        browser_proof = json.loads(process.stdout)
        dom = Path("/output/offline-dom.html").read_bytes()
        proof = {
            "passed": True,
            "external_network_blocked": external_network_blocked,
            "interfaces": ["lo"],
            "six_reports_http": True,
            "real_browser_vue_loaded": True,
            "runtime": "Fresh Python 3.12.13-slim container with prepared browser runtime "
            "libraries; stdlib-only viewer; Chromium mounted read-only, no repository",
            **browser_proof,
            "dom_sha256": hashlib.sha256(dom).hexdigest(),
            "package_manifest_sha256": hashlib.sha256(
                (package / "manifest.json").read_bytes()
            ).hexdigest(),
        }
        Path("/output/offline-proof.json").write_text(json.dumps(proof, indent=2))
        print(json.dumps(proof))
    finally:
        viewer.terminate()
        viewer.wait(timeout=10)


if __name__ == "__main__":
    main()
