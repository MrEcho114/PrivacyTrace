from copy import deepcopy

import pytest
from pydantic import ValidationError
from test_consistency import add_second_policy

from privacytrace.consistency import evaluate
from privacytrace.models import EvaluationInput


def statuses(data):
    return [i.status.value for i in evaluate(EvaluationInput.model_validate(data)).issues]


@pytest.mark.parametrize(
    "field,value",
    [
        ("extraction_status", "FAILED"),
        ("extraction_status", "PARTIAL"),
        ("extraction_status", "NOT_STARTED"),
        ("review_status", "UNREVIEWED"),
        ("attachments_status", "MISSING"),
        ("attachments_status", "NOT_CHECKED"),
        ("completeness", "PARTIAL"),
    ],
)
def test_absence_requires_complete_extraction_review_and_attachments(bundle_data, field, value):
    bundle_data["policy_claims"] = []
    bundle_data["policy_documents"][0][field] = value
    assert statuses(bundle_data) == ["INSUFFICIENT_EVIDENCE"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("polarity", "NEGATIVE"),
        ("polarity", "UNKNOWN"),
        ("condition", "仅在用户开启附近功能时"),
        ("subject", "THIRD_PARTY"),
        ("subject", "UNKNOWN"),
    ],
)
def test_negative_conditional_and_other_subject_are_not_positive_disclosures(
    bundle_data, field, value
):
    bundle_data["policy_claims"][0][field] = value
    assert statuses(bundle_data) == ["AMBIGUOUS_DISCLOSURE"]


def test_mixed_negative_and_positive_claims_require_review(bundle_data):
    claim = deepcopy(bundle_data["policy_claims"][0])
    claim.update(id="negative", polarity="NEGATIVE")
    bundle_data["policy_claims"].append(claim)
    assert statuses(bundle_data) == ["AMBIGUOUS_DISCLOSURE"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_name", "another.app"),
        ("version_codes", [99]),
        ("regions", ["US"]),
        ("product_scope", "another-product"),
    ],
)
def test_inapplicable_policy_cannot_create_cross_source_conflict(bundle_data, field, value):
    add_second_policy(bundle_data)
    bundle_data["policy_documents"][1]["applicability"][field] = value
    assert statuses(bundle_data) == ["EXACT_MATCH"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_name", None),
        ("version_codes", []),
        ("regions", []),
        ("product_scope", None),
    ],
)
def test_unknown_applicability_downgrades_missing_claims(bundle_data, field, value):
    bundle_data["policy_claims"] = []
    bundle_data["policy_documents"][0]["applicability"][field] = value
    assert statuses(bundle_data) == ["INSUFFICIENT_EVIDENCE"]


def test_one_policy_can_apply_to_multiple_apk_versions(bundle_data):
    for code in (1, 2):
        bundle_data["job"]["version_code"] = code
        assert statuses(bundle_data) == ["EXACT_MATCH"]


def test_positive_quote_can_survive_partial_extraction_but_is_marked_for_review(bundle_data):
    bundle_data["policy_documents"][0]["extraction_status"] = "PARTIAL"
    result = evaluate(EvaluationInput.model_validate(bundle_data))
    assert result.issues[0].status.value == "EXACT_MATCH"
    assert result.issues[0].requires_review is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("extraction_status", "PARTIAL"),
        ("review_status", "UNREVIEWED"),
        ("attachments_status", "MISSING"),
        ("attachments_status", "NOT_CHECKED"),
    ],
)
def test_unreviewed_positive_claim_does_not_create_source_conflict(bundle_data, field, value):
    bundle_data["policy_documents"][0][field] = value
    add_second_policy(bundle_data)
    # The second, fully reviewed channel has no claim. The first quote is still
    # visible as a candidate, not eligible for a conclusive cross-source conflict.
    bundle_data["policy_documents"][1][field] = {
        "extraction_status": "SUCCEEDED",
        "review_status": "REVIEWED",
        "attachments_status": "COMPLETE",
    }[field]
    result = evaluate(EvaluationInput.model_validate(bundle_data))
    assert [i.status.value for i in result.issues] == ["EXACT_MATCH", "NOT_DECLARED"]
    assert result.issues[0].requires_review is True


@pytest.mark.parametrize("version", [True, "1", -1, 1.5])
def test_policy_version_codes_are_strict_integers(bundle_data, version):
    bundle_data["policy_documents"][0]["applicability"]["version_codes"] = [version]
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(bundle_data)


@pytest.mark.parametrize("failure", ["no_call", "descriptor", "rule", "version", "context", "type"])
def test_untrusted_api_labels_and_mapping_mismatches_are_rejected(bundle_data, failure):
    api = next(e for e in bundle_data["evidence"] if e["id"] == "ev-location-api")
    if failure == "no_call":
        api.pop("api_call")
        api["excerpt"] = 'Log.d("tag", "location");'
    elif failure == "descriptor":
        api["api_call"]["target_descriptor"] = (
            "Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I"
        )
    elif failure == "rule":
        api["api_call"]["rule_id"] = "invented"
    elif failure == "version":
        api["api_call"]["ruleset_version"] = "0.1.0"
    elif failure == "context":
        api["api_call"]["context"] = {"provider": "network"}
    else:
        bundle_data["behaviors"][0]["data_type"] = "IMEI"
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(bundle_data)


def test_synthetic_oaid_rule_is_not_accepted_for_real_apk(bundle_data):
    bundle_data["job"]["input_mode"] = "APK"
    with pytest.raises(ValidationError, match="trusted rule"):
        EvaluationInput.model_validate(bundle_data)


@pytest.mark.parametrize("field", ["purpose", "recipient", "transfer", "temporal_scope"])
def test_policy_facts_cannot_be_written_into_static_behavior(bundle_data, field):
    bundle_data["behaviors"][0][field] = "from policy"
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(bundle_data)
