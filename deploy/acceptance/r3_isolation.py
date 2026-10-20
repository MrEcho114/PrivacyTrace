"""Read the Runner's actual Docker inspect/cleanup attestations, never fixtures."""

import json
import os
import sqlite3

from .laboratory import inspect_roles
from .provision import ROOT, Laboratory
from .receipt import CheckRecorder, Receipt, read_source_sha


def scan_examples(results, scanner_image, fixtures):
    scans = [
        item
        for item in results
        if item.get("error") is None
        and item.get("receipt", {}).get("image_id") == scanner_image
        and (item.get("result") or {}).get("tools", {}).get("ruleset")
    ]
    single = next(
        (
            item
            for item in scans
            if item["result"].get("package_name") == fixtures.single_package
            and item["result"].get("apk_sha256") == fixtures.single_sha256
            and not item["result"].get("package_set")
        ),
        None,
    )
    splits = next(
        (
            item
            for item in scans
            if item["result"].get("package_name") == fixtures.set_package
            and item["result"].get("package_set", {}).get("split_count") == 2
            and set(item["result"].get("package_set", {}).get("split_names", []))
            == {"config.en", "feature_camera"}
        ),
        None,
    )
    assert single is not None and splits is not None, (
        "full single-APK and split scan results required"
    )
    return [single, splits]


def run():
    receipt = Receipt(scope="r3-actual-isolation", source_sha=read_source_sha(ROOT))
    scope = json.loads((ROOT / "docs/deployment/acceptance-scope.json").read_text())
    receipt.environment["waivers"] = scope["waivers"]
    recorder = CheckRecorder(
        "r3.actual_scan_isolation", "Runner ledger -> Docker inspect attestations", ticket="R3"
    )
    state = os.environ.get("PT_ACCEPTANCE_LAB_STATE")
    if not state:
        receipt.checks.append(recorder.skip("an owned deployment and real scans are required"))
        return receipt
    lab = Laboratory(state)
    inspect_roles(lab)
    with sqlite3.connect(f"file:{lab.root}/runner/requests.sqlite?mode=ro", uri=True) as conn:
        results = [
            json.loads(row[0])
            for row in conn.execute("SELECT result FROM operations WHERE state='DONE'")
        ]
    from .r2_business_loop import Fixtures

    examples = scan_examples(results, lab.state["images"]["scanner"], Fixtures.build())
    proofs = [item["receipt"] for item in examples]
    for proof in proofs:
        isolation = proof["isolation"]
        assert proof["user"] == "65534:65534"
        assert proof["cleanup_verified"] and proof["input_removed"] and proof["container_created"]
        assert isolation["NetworkMode"] == "none" and isolation["ReadonlyRootfs"]
        assert isolation["Memory"] == isolation["MemorySwap"] == 1024**3
        assert isolation["NanoCpus"] == 10**9 and isolation["PidsLimit"] == 32
        assert isolation["CapDrop"] == ["ALL"] and not isolation.get("CapAdd")
        assert not isolation["Privileged"] and any(
            value.startswith("no-new-privileges") for value in isolation["SecurityOpt"]
        )
        assert proof["mounts"] == [{"destination": "/input/sample.apk", "read_only": True}]
    receipt.checks.append(
        recorder.pass_(
            "actual scan policy and cleanup verified",
            scan_count=len(proofs),
            image_id=lab.state["images"]["scanner"],
            actual_inspect=proofs[0],
            scan_request_ids=[item["request_id"] for item in examples],
            scan_inputs=["synthetic single APK", "synthetic base + config.en + feature_camera"],
            api_worker_socket=False,
            scan_host_separate=False,
            credential_mounts=False,
        )
    )
    receipt.notes = "Dedicated-host separation was explicitly waived by the user; see waivers."
    return receipt
