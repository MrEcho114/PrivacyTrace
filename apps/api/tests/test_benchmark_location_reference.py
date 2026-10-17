"""Independent reference parsing, exact byte locations, and canonical CLI consumers."""

import importlib.util
import json
from copy import deepcopy

import pytest

from privacytrace import benchmark, benchmark_locations
from privacytrace.policy_intake import digest
from privacytrace.resources import ROOT, taxonomy


def test_dexdump_parser_distinguishes_invokes_units_bytes_and_instruction_ordinals():
    spec = importlib.util.spec_from_file_location(
        "independent_dexdump", ROOT / "scripts/controlled/location_reference.py")
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    calls = parser.parse_dump("""
  Class descriptor : 'Lexample/Caller;'
      name : 'read'
      type : '()V'
000100: 1a00 0100                              |0000: const-string v0, "gps"
000104: 6e20 0200 1000 |0002: invoke-virtual {v0, v1}, Lexample/Target;.read:()V // method@0002
00010a: 6e20 0200 1000 |0005: invoke-virtual {v0, v1}, Lexample/Target;.read:()V // method@0002
""")
    assert [call["offset_code_units"] for call in calls] == [2, 5]
    assert [call["offset_bytes"] for call in calls] == [4, 10]
    assert [call["instruction_ordinal"] for call in calls] == [1, 2]
    assert [call["dex_file_offset_bytes"] for call in calls] == [0x104, 0x10A]
    assert {call["caller_descriptor"] for call in calls} == {"Lexample/Caller;->read()V"}
    assert {call["target_descriptor"] for call in calls} == {"Lexample/Target;->read()V"}


def test_same_method_multiple_invokes_require_each_exact_callsite_once():
    reference = deepcopy(benchmark_locations.load_reference())
    artifact = reference["scenarios"]["C02"]
    first = next(call for call in artifact["invokes"]
                 if "->readLocation(" in call["caller_descriptor"])
    second = {**first, "offset_bytes": 10, "offset_code_units": 5, "instruction_ordinal": 2}
    artifact["invokes"].append(second)
    rule = next(rule for rule in taxonomy()["api_mappings"]
                if rule["rule_id"] == "android.location.last-known.gps")
    label = {"api_count": 2, "target_descriptor": rule["target_descriptor"],
             "data_type": rule["data_type"]}
    api = [{"source": "classes.dex",
            "locator": benchmark_locations.locator(artifact["apk_sha256"], call),
            "api_call": {**rule, "ruleset_version": taxonomy()["version"]}}
           for call in (first, second)]
    def match(values):
        return benchmark.api_locators_match(
            values, "C02", label, artifact["apk_sha256"], reference)
    assert match(api)
    assert not match([api[0], api[0]])
    assert not match(api[:1])
    api[1]["locator"] = api[1]["locator"].replace("offset_bytes=10;", "offset_bytes=5;")
    assert not match(api)  # A code-unit PC cannot be supplied as a byte offset.


@pytest.mark.parametrize("field,value", [
    ("source", "classes2.dex"), ("caller", "Wrong"), ("target", "Wrong"),
    ("context", {}), ("offset", 2), ("offset", 6), ("apk", "f" * 64),
])
def test_new_scenario_exact_location_binding_rejects_mismatch(field, value):
    reference = benchmark_locations.load_reference()
    artifact = reference["scenarios"]["C07"]
    call = next(call for call in artifact["invokes"]
                if "->readLocation(" in call["caller_descriptor"])
    truth = json.loads((benchmark.SUITES["pt907"] / "ground-truth.json").read_bytes())
    label = truth["scenarios"]["C07"]
    rule = next(rule for rule in taxonomy()["api_mappings"]
                if rule["rule_id"] == "android.location.last-known.gps")
    api = {"source": "classes.dex",
           "locator": benchmark_locations.locator(artifact["apk_sha256"], call),
           "api_call": {**rule, "ruleset_version": taxonomy()["version"]}}
    apk_hash = artifact["apk_sha256"]
    assert benchmark.api_locators_match([api], "C07", label, apk_hash, reference)
    if field == "source":
        api[field] = value
    elif field == "context":
        api["api_call"][field] = value
    elif field == "apk":
        apk_hash = value
    else:
        changed = {**call, {"caller": "caller_descriptor", "target": "target_descriptor",
                           "offset": "offset_bytes"}[field]: value}
        api["locator"] = benchmark_locations.locator(apk_hash, changed)
    assert not benchmark.api_locators_match([api], "C07", label, apk_hash, reference)


def test_frozen_reference_requires_checksum_and_original_apk_binding(tmp_path, monkeypatch):
    path = tmp_path / "reference.json"
    reference = deepcopy(benchmark_locations.load_reference())
    monkeypatch.setattr(benchmark_locations, "REFERENCE", path)
    reference["scenarios"]["C12"]["apk_sha256"] = "f" * 64
    raw = json.dumps(reference).encode()
    path.write_bytes(raw)
    path.with_suffix(".sha256").write_text("0" * 64)
    with pytest.raises(ValueError, match="changed after freeze"):
        benchmark_locations.load_reference()
    path.with_suffix(".sha256").write_text(digest(raw))
    with pytest.raises(ValueError, match="different frozen APK"):
        benchmark_locations.load_reference()


@pytest.mark.parametrize("suite,count", [("spec30", 6), ("pt907", 12)])
@pytest.mark.parametrize("passed", [False, True])
def test_cli_exit_reads_canonical_field_without_legacy_alias(
    monkeypatch, capsys, suite, count, passed,
):
    monkeypatch.setattr(benchmark, "run_benchmark", lambda *a, **k: {
        "scenarios_passed": passed, "scenario_count": count})
    monkeypatch.setattr(benchmark.sys, "argv", ["benchmark", "run", "--suite", suite,
                                               "--artifacts", "unused", "--output", "unused"])
    assert benchmark.main() == (0 if passed else 1)
    assert json.loads(capsys.readouterr().out)["scenarios_passed"] is passed
