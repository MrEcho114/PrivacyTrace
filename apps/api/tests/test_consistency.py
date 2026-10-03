from copy import deepcopy

import pytest

from privacytrace.consistency import evaluate
from privacytrace.models import EvaluationInput, MatchStatus
from privacytrace.resources import read_json


def add_second_policy(data, *, source="STORE_POLICY", complete=True, with_claim=False):
    doc = deepcopy(data["policy_documents"][0])
    doc.update(id="policy-second", source_type=source, evidence_id="ev-second-snapshot")
    doc["completeness"] = "COMPLETE" if complete else "PARTIAL"
    data["policy_documents"].append(doc)
    data["evidence"].append(
        {
            "id": doc["evidence_id"],
            "kind": "POLICY_DOCUMENT",
            "status": "DECLARED",
            "source": "synthetic/second.txt",
            "locator": "snapshot",
            "excerpt": "",
            "artifact_sha256": doc["artifact"]["sha256"],
            "document_id": doc["id"],
        }
    )
    if with_claim:
        data["evidence"].append(
            {
                "id": "ev-second-sentence",
                "kind": "POLICY_SENTENCE",
                "status": "DECLARED",
                "source": "synthetic/second.txt",
                "locator": "sentence[1]",
                "excerpt": "我们访问精确位置。",
                "start_offset": 0,
                "end_offset": 9,
                "document_id": doc["id"],
            }
        )
        data["policy_claims"].append(
            {
                "id": "claim-second",
                "document_id": doc["id"],
                "data_type": "PRECISE_LOCATION",
                "action": "ACCESS",
                "polarity": "AFFIRMATIVE",
                "subject": "HOST_APP",
                "evidence_ids": ["ev-second-sentence"],
            }
        )


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("exact", "EXACT_MATCH"),
        ("category", "CATEGORY_MATCH"),
        ("not_declared", "NOT_DECLARED"),
        ("ambiguous", "AMBIGUOUS_DISCLOSURE"),
        ("unknown_action", "AMBIGUOUS_DISCLOSURE"),
        ("partial", "INSUFFICIENT_EVIDENCE"),
        ("permission_only", "INSUFFICIENT_EVIDENCE"),
        ("sdk_only", "INSUFFICIENT_EVIDENCE"),
        ("no_policy", "INSUFFICIENT_EVIDENCE"),
        ("only_sdk_policy", "INSUFFICIENT_EVIDENCE"),
        ("unrelated_claim", "NOT_DECLARED"),
        ("child_does_not_cover_parent", "NOT_DECLARED"),
        ("capability_with_api", "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_semantic_states(bundle_data, scenario, expected):
    claim = bundle_data["policy_claims"][0]
    if scenario == "category":
        claim["data_type"] = "LOCATION"
        sentence = next(e for e in bundle_data["evidence"] if e["kind"] == "POLICY_SENTENCE")
        sentence["excerpt"] = "我们访问位置信息。"
        sentence.update(start_offset=9, end_offset=18)
    elif scenario in {"not_declared", "partial"}:
        bundle_data["policy_claims"] = []
        if scenario == "partial":
            bundle_data["policy_documents"][0]["completeness"] = "PARTIAL"
    elif scenario == "ambiguous":
        claim["ambiguity_flags"] = ["CATCH_ALL"]
    elif scenario == "unknown_action":
        claim["action"] = "UNKNOWN"
    elif scenario == "permission_only":
        bundle_data["behaviors"][0]["evidence_ids"] = ["ev-location-permission"]
    elif scenario == "sdk_only":
        bundle_data["behaviors"][0]["evidence_ids"] = ["ev-demo-sdk"]
    elif scenario == "no_policy":
        bundle_data["policy_documents"] = []
        bundle_data["policy_claims"] = []
        bundle_data["evidence"] = [e for e in bundle_data["evidence"] if not e.get("document_id")]
    elif scenario == "only_sdk_policy":
        bundle_data["policy_documents"][0]["source_type"] = "SDK_POLICY"
    elif scenario == "unrelated_claim":
        claim["data_type"] = "CONTACTS"
    elif scenario == "child_does_not_cover_parent":
        bundle_data["behaviors"][0]["data_type"] = "LOCATION"
        call = next(e for e in bundle_data["evidence"] if e["id"] == "ev-location-api")["api_call"]
        call.update(rule_id="android.location.last-known.generic", context={})
    elif scenario == "capability_with_api":
        bundle_data["behaviors"][0]["action"] = "CAPABILITY"
    result = evaluate(EvaluationInput.model_validate(bundle_data))
    assert [issue.status.value for issue in result.issues] == [expected]
    assert all(issue.evidence_ids for issue in result.issues)


@pytest.mark.parametrize(
    "source,complete,expected_conflict",
    [
        ("STORE_POLICY", True, True),
        ("IN_APP_POLICY", True, False),
        ("STORE_POLICY", False, False),
        ("SDK_POLICY", True, False),
    ],
)
def test_conflicts_require_distinct_host_sources(bundle_data, source, complete, expected_conflict):
    add_second_policy(bundle_data, source=source, complete=complete)
    result = evaluate(EvaluationInput.model_validate(bundle_data))
    conflicts = [i for i in result.issues if i.status == MatchStatus.POLICY_SOURCE_CONFLICT]
    assert bool(conflicts) is expected_conflict
    if conflicts:
        assert len(conflicts[0].policy_document_ids) == 2
        assert "ev-second-snapshot" in conflicts[0].evidence_ids


def test_sdk_declaration_cannot_repair_host_absence(bundle_data):
    bundle_data["policy_claims"] = []
    add_second_policy(bundle_data, source="SDK_POLICY", with_claim=True)
    result = evaluate(EvaluationInput.model_validate(bundle_data))
    assert [i.status for i in result.issues] == [MatchStatus.NOT_DECLARED]


def test_device_information_is_ancestor_of_oaid():
    data = read_json("samples/demo/evaluation-input.json")
    data["behaviors"] = [data["behaviors"][2]]
    data["policy_claims"][-1]["data_type"] = "DEVICE_INFORMATION"
    result = evaluate(EvaluationInput.model_validate(data))
    assert any(i.status == MatchStatus.CATEGORY_MATCH for i in result.issues)


def test_report_is_deterministic_and_every_reference_resolves():
    bundle = EvaluationInput.model_validate(read_json("samples/demo/evaluation-input.json"))
    first = evaluate(bundle)
    assert first == evaluate(bundle)
    ids = {e.id for e in bundle.evidence}
    assert all(set(i.evidence_ids) <= ids for i in first.issues)
    assert len(first.issues) == 7
    assert all(b.purpose == "UNKNOWN" for b in bundle.behaviors)
