"""Keep checked-in web types and schemas tied to authoritative API models."""

import importlib.util

import pytest

from privacytrace.resources import ROOT

spec = importlib.util.spec_from_file_location("export_schema", ROOT / "scripts/export-schema.py")
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def test_all_generated_contract_files_are_current():
    for path, expected in exporter.generated_files().items():
        assert path.read_text(encoding="utf-8") == expected, f"Regenerate {path}"


@pytest.mark.parametrize(
    "schema",
    [
        {"allOf": [{"type": "string"}]},
        {"type": "unknown"},
        {"type": "array"},
        {"type": "object", "additionalProperties": True},
        {"$ref": "https://example.invalid/schema"},
        {"$ref": "#/$defs/Absent"},
        {"type": "string", "not": {"const": "forbidden"}},
        {"anyOf": []},
        {"anyOf": [{"type": "null"}], "type": "string"},
        {"type": ["string", "null"]},
        {"enum": [{"a": "b"}]},
        {"const": {"a": "b"}},
        {"const": "a", "enum": ["a"]},
        {"$ref": "#/$defs/Absent", "properties": {"a": {"type": "string"}}},
        True,
    ],
)
def test_unsupported_schema_fails_instead_of_generating_any(schema):
    with pytest.raises(ValueError):
        exporter.ts_type(schema, {})


def test_nullable_optional_enums_and_typed_dictionaries():
    schema = {
        "type": "object", "additionalProperties": False, "required": ["values"],
        "properties": {
            "values": {"type": "object", "additionalProperties": {"type": "string"}},
            "state": {"anyOf": [{"enum": ["A", "B"]}, {"type": "null"}]},
        },
    }
    result = exporter.ts_type(schema, {})
    assert '"values": Record<string, string>' in result
    assert '"state"?: "A" | "B" | null' in result


def test_conflicting_definitions_fail():
    with pytest.raises(ValueError, match="Conflicting"):
        exporter.generate_typescript({
            "a": {"title": "A", "$defs": {"Shared": {"type": "string"}}},
            "b": {"title": "B", "$defs": {"Shared": {"type": "number"}}},
        })
