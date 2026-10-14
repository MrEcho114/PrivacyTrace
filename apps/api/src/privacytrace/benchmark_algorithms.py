"""Feature-only prediction worker: stdin materials, no truth files or host mounts."""

import hashlib
import json
import sys
import time
from pathlib import Path

from .consistency import evaluate
from .models import EvaluationInput
from .resources import ROOT, taxonomy


def predict(material):
    supplied_hash = material.pop("material_sha256")
    actual_hash = hashlib.sha256(
        json.dumps(material, ensure_ascii=True, sort_keys=True).encode()
    ).hexdigest()
    if actual_hash != supplied_hash:
        raise ValueError("Feature material hash mismatch")
    bundle = EvaluationInput.model_validate(material["bundle"])
    rules = taxonomy(bundle.job.ruleset_version)
    text = "\n".join(doc.artifact.text for doc in bundle.policy_documents)
    phrases = {}
    for item in rules["policy_phrase_mappings"]:
        phrases.setdefault(item["data_type"], []).append(item["phrase"])
    predictions, elapsed = {}, {}
    started = time.perf_counter()
    permission_results = []
    for mapping in rules["permission_mappings"]:
        if mapping["permission"] not in material["permissions"]:
            continue
        refs = [
            item.id
            for item in bundle.evidence
            if item.kind == "MANIFEST" and item.excerpt.split(";")[0] == mapping["permission"]
        ]
        permission_results.append(
            {
                "data_type": mapping["data_type"],
                "action": "CAPABILITY",
                "status": "EXACT_MATCH"
                if any(phrase in text for phrase in phrases.get(mapping["data_type"], []))
                else "NOT_DECLARED",
                "evidence_ids": refs,
            }
        )
    predictions["permission_keyword"] = permission_results
    elapsed["permission_keyword"] = time.perf_counter() - started

    started = time.perf_counter()
    api_results = []
    # Independently map the complete descriptor AND context, using the same trusted taxonomy.
    for item in bundle.evidence:
        call = item.api_call
        if call is None:
            continue
        mapping = next(
            rule
            for rule in rules["api_mappings"]
            if rule["target_descriptor"] == call.target_descriptor
            and rule["context"] == call.context
            and rule["rule_id"] == call.rule_id
        )
        api_results.append(
            {
                "data_type": mapping["data_type"],
                "action": "ACCESS",
                "status": "EXACT_MATCH"
                if any(phrase in text for phrase in phrases.get(mapping["data_type"], []))
                else "NOT_DECLARED",
                "evidence_ids": [item.id],
            }
        )
    if not api_results:
        api_results = [
            {
                "data_type": item.data_type,
                "action": item.action,
                "status": "INSUFFICIENT_EVIDENCE",
                "evidence_ids": item.evidence_ids,
            }
            for item in bundle.behaviors
        ]
    predictions["api_flat"] = api_results
    elapsed["api_flat"] = time.perf_counter() - started

    started = time.perf_counter()
    result = evaluate(bundle)
    behaviors = {item.id: item for item in bundle.behaviors}
    predictions["privacytrace"] = [
        {
            "data_type": behaviors[issue.behavior_id].data_type,
            "action": behaviors[issue.behavior_id].action,
            "status": issue.status,
            "evidence_ids": issue.evidence_ids,
        }
        for issue in result.issues
    ]
    elapsed["privacytrace"] = time.perf_counter() - started
    return {
        "predictions": predictions,
        "scheme_elapsed_seconds": elapsed,
        "truth_files_absent": not (ROOT / "benchmarks").exists(),
        "material_sha256": actual_hash,
    }


if __name__ == "__main__":
    # The Docker image contains only API source and rules; no benchmark labels. No repository mount.
    if (ROOT / "benchmarks").exists() or Path("/var/run/docker.sock").exists():
        raise SystemExit("Prediction worker requires a feature-only environment")
    print(json.dumps(predict(json.load(sys.stdin)), ensure_ascii=True))
