"""Actual role startup, image/source identity and packaged resources."""

import hashlib
import json
import os

from .laboratory import inspect_roles
from .provision import ROOT, Laboratory, execute
from .receipt import CheckRecorder, Receipt, read_source_sha
from .topology import Topology, request


def run():
    receipt = Receipt(scope="r1-full-deployment", source_sha=read_source_sha(ROOT))
    check = CheckRecorder(
        "r1.full_topology", "inspect roles, readiness and HTTPS resources", ticket="R1"
    )
    state = os.environ.get("PT_ACCEPTANCE_LAB_STATE")
    if not state:
        receipt.checks.append(check.skip("an owned running deployment is required"))
        return receipt
    lab = Laboratory(state)
    lab.ready()
    roles = inspect_roles(lab)
    for name in ("web", "api", "worker", "dispatcher", "gateway", "runner"):
        assert roles[name]["source_revision"] == receipt.source_sha
    scanner = json.loads(execute(["docker", "image", "inspect", lab.state["images"]["scanner"]]))[0]
    assert (scanner["Config"].get("Labels") or {}).get(
        "org.opencontainers.image.revision"
    ) == receipt.source_sha
    topology = Topology.from_env()
    resources = {
        path: request(topology, path).status
        for path in ("/", "/api/v1/health", "/api/v1/taxonomy", "/api/v1/demo/report")
    }
    assert all(code == 200 for code in resources.values())
    receipt.checks.append(
        check.pass_(
            "all roles ready; packaged resources available",
            roles=roles,
            scanner_image_id=scanner["Id"],
            resources=resources,
            migration="0080_05",
            protocol=1,
            python_lock_sha256=hashlib.sha256((ROOT / "apps/api/uv.lock").read_bytes()).hexdigest(),
            frontend_lock_sha256=hashlib.sha256(
                (ROOT / "package-lock.json").read_bytes()
            ).hexdigest(),
        )
    )
    return receipt
