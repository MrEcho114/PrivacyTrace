import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from privacytrace.models import EvaluationInput
from privacytrace.resources import ROOT, taxonomy


@pytest.mark.parametrize(
    "failure",
    [
        "dangling",
        "duplicate",
        "unknown_type",
        "wrong_document",
        "fake_quote",
        "fake_hash",
        "wrong_version",
        "declaration_as_fact",
        "hint_without_basis",
    ],
)
def test_invalid_evidence_contracts_are_rejected(bundle_data, failure):
    if failure == "dangling":
        bundle_data["behaviors"][0]["evidence_ids"] = ["missing"]
    elif failure == "duplicate":
        bundle_data["evidence"].append(deepcopy(bundle_data["evidence"][0]))
    elif failure == "unknown_type":
        bundle_data["behaviors"][0]["data_type"] = "INVENTED_TYPE"
    elif failure == "wrong_document":
        bundle_data["policy_claims"][0]["document_id"] = "missing"
    elif failure == "fake_quote":
        next(e for e in bundle_data["evidence"] if e["kind"] == "POLICY_SENTENCE")["excerpt"] = (
            "编造原句"
        )
    elif failure == "fake_hash":
        bundle_data["policy_documents"][0]["artifact"]["sha256"] = "0" * 64
    elif failure == "wrong_version":
        bundle_data["job"]["ruleset_version"] = "unknown"
    elif failure == "declaration_as_fact":
        bundle_data["behaviors"][0]["purpose"] = "Navigation"
    elif failure == "hint_without_basis":
        bundle_data["behaviors"][0]["contextual_hints"] = [
            {
                "value": "Navigation",
                "evidence_ids": ["ev-demo-sdk"],
            }
        ]
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(bundle_data)


def test_taxonomy_has_no_cycles_and_mappings_resolve():
    rules = taxonomy()
    types = {t["id"]: t for t in rules["data_types"]}
    for item in types.values():
        seen = {item["id"]}
        parent = item["parent"]
        while parent:
            assert parent in types and parent not in seen
            seen.add(parent)
            parent = types[parent]["parent"]
    for group in ["permission_mappings", "api_mappings", "policy_phrase_mappings"]:
        assert all(mapping["data_type"] in types for mapping in rules[group])


def test_sql_design_initializes_and_preserves_foreign_keys():
    database = sqlite3.connect(":memory:")
    database.executescript((ROOT / "apps/api/schema.sql").read_text())
    assert database.execute("PRAGMA foreign_keys").fetchone() == (1,)
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO analysis_job (id, sample_id, state, ruleset_version, created_at, error) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("job", "nonexistent", "QUEUED", "0.1.0", "2026-10-02", None),
        )
    database.close()


def test_generated_contracts_match_authoritative_models():
    import json

    from privacytrace.models import EvaluationResult
    from privacytrace.sdk_ruleset import SdkSignatureRuleset

    for name, model in [
        ("evaluation-input", EvaluationInput),
        ("evaluation-result", EvaluationResult),
        ("sdk-signatures", SdkSignatureRuleset),
    ]:
        path: Path = ROOT / "packages/contracts" / f"{name}.schema.json"
        assert json.loads(path.read_text(encoding="utf-8")) == model.model_json_schema()


def test_shipped_sdk_ruleset_validates_against_its_contract():
    """The active ruleset is data; the contract is code. Keep them in step."""
    from privacytrace.resources import sdk_signatures
    from privacytrace.sdk_ruleset import SdkSignatureRuleset

    rules = sdk_signatures()
    validated = SdkSignatureRuleset.model_validate(rules)
    assert validated.version == rules["version"]
    assert validated.signatures, "active ruleset must ship at least one signature"
    assert validated.excluded_namespaces, "platform namespaces must stay excluded"


@pytest.mark.parametrize("version", ["1.0", "1.0.0.0", "v1.0.0", ""])
def test_sdk_ruleset_rejects_malformed_version(version):
    from privacytrace.sdk_ruleset import SdkSignatureRuleset

    rules = {"version": version}
    with pytest.raises(ValidationError):
        SdkSignatureRuleset.model_validate(rules)
