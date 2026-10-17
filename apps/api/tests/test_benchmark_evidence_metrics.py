"""Evidence metrics audit real references rather than successful scan flags."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from privacytrace import benchmark
from privacytrace.models import EvaluationInput
from privacytrace.policy_intake import digest
from privacytrace.resources import taxonomy


@pytest.fixture
def prediction_report(bundle_data, tmp_path, monkeypatch):
    bundle = EvaluationInput.model_validate(bundle_data)
    # A corrupted in-memory report must not inherit the store's earlier validation.
    report = SimpleNamespace(
        **dict(bundle),
        model_dump=lambda **kwargs: bundle.model_dump(mode="json"),
        model_dump_json=bundle.model_dump_json,
        coverage=SimpleNamespace(model_dump=lambda: {"status": "COMPLETE"},
                                 behavior_limitations=[]),
        sample=SimpleNamespace(apk_sha256="a" * 64),
    )
    monkeypatch.setattr(benchmark, "analyze", lambda *a, **k: {
        "job_id": "test-job", "status": "SUCCEEDED", "errors": [],
    })
    monkeypatch.setattr(benchmark, "JobStore",
                        lambda path: SimpleNamespace(report=lambda id: report))
    monkeypatch.setattr(benchmark, "schemes", lambda report: {"predictions": {
        scheme: [] for scheme in benchmark.SCHEMES}})
    (tmp_path / "test-job.json").write_text("{}")
    feature = tmp_path / "C02.json"
    feature.write_text("{}")
    return report, lambda: benchmark.predict(feature, tmp_path, tmp_path, 1)


@pytest.mark.parametrize("field,value", [
    ("excerpt", "这不是原句"), ("start_offset", 1), ("end_offset", 10),
    ("document_id", "unknown-document"),
])
def test_corrupted_policy_span_is_not_reported_as_validated(prediction_report, field, value):
    report, predict = prediction_report
    sentence = next(item for item in report.evidence if item.kind == "POLICY_SENTENCE")
    setattr(sentence, field, value)
    record = predict()
    assert record["policy_spans_validated"] is False
    assert record["policy_span_validation"]["errors"][0]["code"] == "POLICY_EVIDENCE_INVALID"


def test_unicode_offsets_count_codepoints_not_utf8_bytes_or_utf16_units(prediction_report):
    report, predict = prediction_report
    doc = report.policy_documents[0]
    doc.artifact.text = "😀前缀。我们访问精确位置。"
    doc.artifact.sha256 = digest(doc.artifact.text.encode())
    snapshot = next(item for item in report.evidence if item.kind == "POLICY_DOCUMENT")
    snapshot.artifact_sha256 = doc.artifact.sha256
    snapshot.excerpt = ""
    sentence = next(item for item in report.evidence if item.kind == "POLICY_SENTENCE")
    sentence.start_offset, sentence.end_offset = 4, 13
    record = predict()
    assert record["policy_spans_validated"] is True
    assert record["policy_span_validation"]["checked_evidence_ids"] == [sentence.id]
    sentence.start_offset += 1  # UTF-16 would count the emoji as two units.
    assert predict()["policy_spans_validated"] is False


def test_changed_policy_snapshot_hash_is_not_reported_as_validated(prediction_report):
    report, predict = prediction_report
    report.policy_documents[0].artifact.text += "篡改"
    assert predict()["policy_spans_validated"] is False


@pytest.fixture
def located_record():
    rule = next(rule for rule in taxonomy()["api_mappings"]
                if rule["rule_id"] == "android.location.last-known.gps")
    api = {
        "id": "api-target", "kind": "API", "source": "classes.dex",
        "locator": "caller=Lorg/privacytrace/controlled/c02/MainActivity;"
                   "->readLocation(Landroid/location/LocationManager;)Landroid/location/Location;"
                   ";offset_bytes=4;",
        "api_call": {**{key: rule[key] for key in ("rule_id", "target_descriptor", "context")},
                     "ruleset_version": taxonomy()["version"]},
    }
    manifest = {"id": "permission", "kind": "MANIFEST", "source": "AndroidManifest.xml",
                "locator": "uses-permission[1]", "api_call": None}
    prediction = {"data_type": "PRECISE_LOCATION", "action": "ACCESS",
                  "status": "EXACT_MATCH", "evidence_ids": [api["id"]]}
    record = {
        "scenario_id": "C02", "analysis": {"status": "SUCCEEDED", "errors": []},
        "api_evidence": [api], "evidence_locators": [api, manifest],
        "policy_spans_validated": True,
        "policy_span_validation": {"validated": True, "checked_evidence_ids": [], "errors": []},
        "predictions": {scheme: [deepcopy(prediction)] for scheme in benchmark.SCHEMES},
    }
    label = {"data_type": "PRECISE_LOCATION", "action": "ACCESS", "expected": "EXACT_MATCH",
             "api_count": 1, "target_descriptor": rule["target_descriptor"]}
    return record, {"scenarios": {"C02": label}}


@pytest.mark.parametrize("refs", [[], ["permission"], ["wrong-api-id"]])
def test_scheme_without_target_api_reference_cannot_inherit_scanner_success(located_record, refs):
    record, truth = located_record
    record["predictions"]["permission_keyword"][0]["evidence_ids"] = refs
    rows, _ = benchmark.score([record], truth)
    row = next(row for row in rows if row["scheme"] == "permission_keyword")
    assert row["scheme_prediction_evidence_locator_validated"] is False
    assert row["shared_scanner_api_evidence_verified"] is True
    assert next(row for row in rows if row["scheme"] == "api_flat")[
        "scheme_prediction_evidence_locator_validated"] is True


def test_missing_target_prediction_cannot_inherit_scanner_success(located_record):
    record, truth = located_record
    record["predictions"]["permission_keyword"] = []
    row = benchmark.score([record], truth)[0][0]
    assert row["scheme_prediction_evidence_locator_validated"] is False


def test_wrong_referenced_locator_is_rejected_even_when_shared_scan_is_correct(located_record):
    record, truth = located_record
    record["evidence_locators"] = deepcopy(record["evidence_locators"])
    record["evidence_locators"][0]["locator"] = "caller=Wrong;offset_bytes=4;"
    row = benchmark.score([record], truth)[0][0]
    assert row["scheme_prediction_evidence_locator_validated"] is False


def test_absence_of_expected_api_is_scanner_success_and_scheme_api_not_applicable(located_record):
    record, truth = located_record
    truth["scenarios"]["C02"]["api_count"] = 0
    truth["scenarios"]["C02"]["target_descriptor"] = None
    record["api_evidence"] = []
    row = benchmark.score([record], truth)[0][0]
    assert row["scheme_prediction_evidence_locator_validated"] is None
    assert row["shared_scanner_api_evidence_verified"] is True


@pytest.mark.parametrize("field,value", [
    ("source", "wrong.dex"), ("api_call", {"target_descriptor": "wrong", "context": {},
                                         "rule_id": "wrong", "ruleset_version": "0.3.0"}),
])
def test_referenced_api_mapping_must_match_frozen_target(located_record, field, value):
    record, truth = located_record
    record["evidence_locators"] = deepcopy(record["evidence_locators"])
    record["evidence_locators"][0][field] = value
    row = benchmark.score([record], truth)[0][0]
    assert row["shared_scanner_api_evidence_verified"] is True
    assert row["scheme_prediction_evidence_locator_validated"] is False


@pytest.mark.parametrize("corruption", [None, "policy", "reference"])
def test_benchmark_gate_uses_audited_policy_and_scheme_references(
    located_record, tmp_path, monkeypatch, corruption,
):
    template, _ = located_record
    truth = json.loads((benchmark.SUITE / "ground-truth.json").read_bytes())

    def predict_process(command, **kwargs):
        scenario = Path(command[command.index("--features") + 1]).stem
        label = truth["scenarios"][scenario]
        record = deepcopy(template)
        record.update(scenario_id=scenario, truth_files_absent=True,
                      coverage={"status": "COMPLETE"})
        api = record["api_evidence"][0]
        api["locator"] = api["locator"].replace("/c02/", "/" + scenario.lower() + "/")
        if not label["api_count"]:
            record["api_evidence"] = []
        for scheme in benchmark.SCHEMES:
            prediction = record["predictions"][scheme][0]
            prediction.update(status=label["expected"], action=label["action"])
            if not label["api_count"]:
                prediction["evidence_ids"] = ["permission"]
        if corruption == "policy":
            record["policy_span_validation"] = {
                "validated": False, "errors": [{"code": "POLICY_EVIDENCE_INVALID"}]}
        if corruption == "reference" and label["api_count"]:
            record["predictions"]["privacytrace"][0]["evidence_ids"] = ["wrong-api-id"]
        return SimpleNamespace(stdout=json.dumps(record))

    monkeypatch.setattr(benchmark.subprocess, "run", predict_process)
    output = tmp_path / "evaluation"
    result = benchmark.run_benchmark(tmp_path, output, 1)
    assert result["scenarios_passed"] is (corruption is None)
    comparison = json.loads((output / "comparison.json").read_bytes())
    assert len(comparison["rows"]) == 18
    assert all(row["agreement"] for row in comparison["rows"])
    assert comparison["diagnostics"]["privacytrace"]["scheme_api_locator_not_applicable"] == 1
    if corruption == "policy":
        assert all({"code": "POLICY_EVIDENCE_INVALID"} in row["errors"]
                   for row in comparison["rows"])
