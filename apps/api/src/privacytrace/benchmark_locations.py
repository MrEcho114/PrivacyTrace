"""Versioned independent DEX callsite references for the authored benchmark only."""

import json

from .controlled import SUITES
from .policy_intake import digest, read_safe
from .resources import ROOT

REFERENCE = ROOT / "benchmarks/locator-reference-v1/reference.json"


def load_reference():
    raw = read_safe(REFERENCE)
    if digest(raw) != REFERENCE.with_suffix(".sha256").read_text().strip():
        raise ValueError("Independent location reference changed after freeze")
    reference = json.loads(raw)
    if reference["schema_version"] != 1:
        raise ValueError("Unsupported location reference")
    for suite in SUITES.values():
        lock = json.loads(read_safe(suite / "artifacts.lock.json"))
        for scenario, apk_hash in lock["apks"].items():
            if reference["scenarios"][scenario]["apk_sha256"] != apk_hash:
                raise ValueError("Location reference is for a different frozen APK")
        if any(reference["source_hashes"].get(name) != hashed
               for name, hashed in lock["source_hashes"].items()):
            raise ValueError("Location reference is for different authored sources")
    return reference


def locator(apk_hash, call):
    return (f"apk_sha256={apk_hash};dex={call['dex']};"
            f"caller={call['caller_descriptor']};offset_bytes={call['offset_bytes']};"
            f"target={call['target_descriptor']}")


def expected_calls(reference, scenario, label, apk_hash):
    artifact = reference["scenarios"].get(scenario)
    if artifact is None or artifact["apk_sha256"] != apk_hash:
        return None
    caller = label.get("caller_descriptor", (
        "Lorg/privacytrace/controlled/" + scenario.lower()
        + "/MainActivity;->readLocation(Landroid/location/LocationManager;)"
        "Landroid/location/Location;"
    ))
    calls = [call for call in artifact["invokes"]
             if call["target_descriptor"] == label["target_descriptor"]
             and call["caller_descriptor"] == caller
             and call["context"] == label.get("target_context", {"provider": "gps"})]
    return calls if len(calls) == label["api_count"] else None
