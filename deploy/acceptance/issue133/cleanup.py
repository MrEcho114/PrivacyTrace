"""Revoke synthetic scopes, then destroy only the marked lane E laboratory."""

import json
import re
import shutil
import time
from pathlib import Path

from deploy.acceptance.fault_drill import _owned_scanners
from deploy.acceptance.issue133.control import scope_context
from deploy.acceptance.issue133.observe import laboratory, observe
from deploy.acceptance.provision import execute
from deploy.acceptance.topology import request


def main():
    lab = laboratory()
    root = lab.root.resolve()
    parent = Path("/var/tmp/pt133e")
    if root.parent != parent or not re.fullmatch(r"pt81-[a-f0-9]{12}", root.name):
        raise ValueError("Refuse cleanup outside the owned lane E project")
    observe(lab)
    registry = json.loads((root / "e-private/scopes.json").read_text())
    statuses = []
    for saved in registry.values():
        topology, draft, token = scope_context(lab, saved["alias"])
        status = request(
            topology, f"/api/v1/web/drafts/{draft}", method="DELETE", token=token
        ).status
        if status not in (200, 202, 204, 403, 404, 410):
            raise AssertionError("Synthetic scope cleanup was not confirmed")
        statuses.append({"scope": saved["alias"], "delete_status": status})
    until = time.monotonic() + 30
    while _owned_scanners(lab) and time.monotonic() < until:
        time.sleep(0.2)
    final = observe(lab)
    if final["active_scanners"]:
        raise AssertionError("Owned scanner remains; preserve lab for diagnosis")
    if any(not scope["tombstone"] for scope in final["persistent"]["scopes"]):
        raise AssertionError("A synthetic capability is still live")
    # The observer attached only itself to this project's edge network.
    execute(["docker", "network", "disconnect", lab.project + "_edge", "pt133e-controller"])
    lab.stop()
    # All paths are checked in this Linux process before recursive removal.
    # No host shell enumeration, other projects or global Docker pruning.
    shutil.rmtree(root)
    (parent / "current").unlink()
    print(
        json.dumps(
            {
                "scope_cleanup": statuses,
                "before_destroy": final,
                "owned_compose_removed": True,
                "private_lab_removed": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
