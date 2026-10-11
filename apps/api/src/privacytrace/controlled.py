"""Controlled source-built fixtures only. No labels or real-app trust promotion."""

import argparse
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from .isolated_scan import ROOT, ScanError
from .models import Model
from .pipeline import run
from .policy_intake import capture, digest, read_safe

SUITE = ROOT / "benchmarks/controlled"


class Candidate(Model):
    excerpt: str = Field(min_length=1, max_length=10000)
    data_type: str
    polarity: str
    subject: str
    action: str


class Features(Model):
    schema_version: int = Field(ge=1, le=1)
    scenario_id: str = Field(pattern=r"^C0[1-6]$")
    package_name: str = Field(pattern=r"^org\.privacytrace\.controlled\.c0[1-6]$")
    policy_file: str = Field(pattern=r"^C0[1-6]\.txt$")
    policy_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope_known: bool
    policy_complete: bool
    candidates: list[Candidate] = Field(max_length=10)


def load_features(path: Path, artifacts: Path):
    raw = read_safe(path)
    feature = Features.model_validate_json(raw)
    lock = json.loads(read_safe(SUITE / "inputs.lock.json"))
    # Only the reviewed, versioned fixture set may assert known scope/policy facts.
    if lock["features"].get(feature.scenario_id) != digest(raw):
        raise ValueError("Feature is not in the frozen controlled suite")
    policy = SUITE / "policies" / feature.policy_file
    if digest(read_safe(policy)) != feature.policy_sha256:
        raise ValueError("Policy hash mismatch")
    build_bytes = read_safe(artifacts / "build-receipt.json")
    build = json.loads(build_bytes)
    expected_sources = lock["sources"]
    for relative, hashed in expected_sources.items():
        if digest(read_safe(SUITE / relative, SUITE)) != hashed:
            raise ValueError("Controlled source changed after freeze")
    if build["source_hashes"] != expected_sources:
        raise ValueError("Build uses different source inputs")
    apk = artifacts / (feature.scenario_id + ".apk")
    hashed = digest(read_safe(apk, max_bytes=150 * 1024 * 1024))
    artifacts_lock = json.loads(read_safe(SUITE / "artifacts.lock.json"))
    if (
        build["apks"].get(feature.scenario_id) != hashed
        or artifacts_lock["apks"].get(feature.scenario_id) != hashed
        or artifacts_lock["source_hashes"] != expected_sources
    ):
        raise ValueError("APK hash mismatch")
    return (
        feature,
        apk,
        policy,
        {
            **feature.model_dump(),
            "features_sha256": digest(raw),
            "apk_sha256": hashed,
            "build_sha256": digest(build_bytes),
        },
    )


def adapt_policy(captured, feature):
    """Promote only authored, checked controlled facts; real intake stays unchanged."""
    document = captured["document"]
    document["source_type"] = "CONTROLLED_POLICY"
    document["title"] = "自建受控配对政策 " + feature["scenario_id"]
    if document["artifact"]["sha256"] != feature["policy_sha256"]:
        raise ValueError("Controlled policy hash mismatch")
    if feature["policy_complete"]:
        document.update(
            completeness="COMPLETE",
            extraction_status="SUCCEEDED",
            review_status="REVIEWED",
            attachments_status="COMPLETE",
        )
    else:
        document["completeness"] = "PARTIAL"
    return captured


def analyze(features: Path, artifacts: Path, store_dir: Path, timeout=120, job_id=None):
    feature, apk, policy, context = load_features(features, artifacts)
    with tempfile.TemporaryDirectory(prefix="privacytrace-controlled-") as temp:
        policy_capture = capture(
            policy,
            "https://example.invalid/privacytrace/controlled/" + feature.scenario_id,
            "controlled-1",
            Path(temp) / "capture",
            [item.model_dump() for item in feature.candidates],
            package=feature.package_name,
            version_code=1,
            product_scope="CONTROLLED_TEST",
            regions=["CONTROLLED_TEST"] if feature.scope_known else [],
            actor="Agent-assisted authored fixture",
            reason="Controlled policy source annotation",
        )
        return run(
            apk,
            policy_capture,
            feature.scenario_id,
            job_id or uuid4().hex,
            timeout,
            store_dir,
            "CONTROLLED_TEST",
            controlled=context,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--store-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--job-id")
    args = parser.parse_args()
    try:
        output = analyze(args.features, args.artifacts, args.store_dir, args.timeout, args.job_id)
    except (ValueError, OSError, KeyError, TypeError, ScanError):
        output = {
            "status": "FAILED",
            "errors": [
                {
                    "code": "CONTROLLED_INPUT_INVALID",
                    "message": "Controlled material failed identity, hash or schema validation",
                }
            ],
        }
    print(json.dumps(output, ensure_ascii=True))
    return 0 if output["status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
