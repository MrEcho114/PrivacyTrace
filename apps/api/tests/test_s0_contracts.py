"""S0 public model/API boundaries, not parser internals."""

import sqlite3
from hashlib import sha256

import pytest
from pydantic import ValidationError

from privacytrace.models import EvaluationInput
from privacytrace.resources import ROOT


def test_long_policy_artifact_keeps_full_text_and_exact_sentence_span(bundle_data):
    doc = bundle_data["policy_documents"][0]
    text = "甲" * 12000 + "我们访问精确位置。" + "乙" * 23
    assert len(text) == 12032
    doc["artifact"] = {
        "text": text,
        "sha256": sha256(text.encode()).hexdigest(),
        "normalization": "NONE",
    }
    doc.pop("text", None)
    doc.pop("sha256", None)
    snapshot = next(e for e in bundle_data["evidence"] if e["id"] == doc["evidence_id"])
    snapshot.update(excerpt="", artifact_sha256=doc["artifact"]["sha256"])
    sentence = next(e for e in bundle_data["evidence"] if e["kind"] == "POLICY_SENTENCE")
    sentence.update(start_offset=12000, end_offset=12009)
    bundle = EvaluationInput.model_validate(bundle_data)
    artifact = bundle.policy_documents[0].artifact
    assert artifact.text == text
    quote = next(e for e in bundle.evidence if e.kind == "POLICY_SENTENCE")
    assert artifact.text[quote.start_offset : quote.end_offset] == "我们访问精确位置。"


@pytest.mark.parametrize("length,accepted", [(200000, True), (200001, False)])
def test_policy_artifact_length_boundary(bundle_data, length, accepted):
    doc = bundle_data["policy_documents"][0]
    doc["artifact"] = {
        "text": "甲" * length,
        "sha256": sha256(("甲" * length).encode()).hexdigest(),
    }
    doc.pop("text", None)
    doc.pop("sha256", None)
    bundle_data["policy_claims"] = []
    bundle_data["evidence"] = [e for e in bundle_data["evidence"] if e["kind"] != "POLICY_SENTENCE"]
    snapshot = next(e for e in bundle_data["evidence"] if e["id"] == doc["evidence_id"])
    snapshot.update(excerpt="", artifact_sha256=doc["artifact"]["sha256"])
    if accepted:
        assert (
            len(EvaluationInput.model_validate(bundle_data).policy_documents[0].artifact.text)
            == length
        )
    else:
        with pytest.raises(ValidationError, match="at most 200000"):
            EvaluationInput.model_validate(bundle_data)


@pytest.mark.parametrize("failure", ["hash", "snapshot_hash", "span", "range", "order", "missing"])
def test_artifact_hash_and_sentence_positions_are_enforced(bundle_data, failure):
    doc = bundle_data["policy_documents"][0]
    sentence = next(e for e in bundle_data["evidence"] if e["kind"] == "POLICY_SENTENCE")
    if failure == "hash":
        doc["artifact"]["sha256"] = "0" * 64
    elif failure == "snapshot_hash":
        next(e for e in bundle_data["evidence"] if e["id"] == doc["evidence_id"])[
            "artifact_sha256"
        ] = "0" * 64
    elif failure == "span":
        sentence.update(start_offset=1, end_offset=10)
    elif failure == "range":
        sentence["end_offset"] = 100000
    elif failure == "order":
        sentence.update(start_offset=9, end_offset=9)
    else:
        sentence.pop("start_offset")
    with pytest.raises(ValidationError):
        EvaluationInput.model_validate(bundle_data)


def test_unicode_offsets_are_codepoints_and_no_normalization_is_silent(bundle_data):
    doc = bundle_data["policy_documents"][0]
    text = "😀\r\n我们访问精确位置。"
    doc["artifact"] = {"text": text, "sha256": sha256(text.encode()).hexdigest()}
    snapshot = next(e for e in bundle_data["evidence"] if e["id"] == doc["evidence_id"])
    snapshot["artifact_sha256"] = doc["artifact"]["sha256"]
    sentence = next(e for e in bundle_data["evidence"] if e["kind"] == "POLICY_SENTENCE")
    sentence.update(start_offset=3, end_offset=12)
    bundle = EvaluationInput.model_validate(bundle_data)
    assert bundle.policy_documents[0].artifact.text == text
    assert bundle.model_dump()["evidence"][-1]["start_offset"] == 3
    doc["artifact"]["text"] = text.replace("\r\n", "\n")
    with pytest.raises(ValidationError, match="hash"):
        EvaluationInput.model_validate(bundle_data)


def test_sql_storage_contract_preserves_long_artifact_and_review_states(bundle_data):
    db = sqlite3.connect(":memory:")
    db.executescript((ROOT / "apps/api/schema.sql").read_text(encoding="utf-8"))
    text = "甲" * 12032
    digest = sha256(text.encode()).hexdigest()
    db.execute("INSERT INTO policy_artifact VALUES (?, ?, ?)", (digest, text, "NONE"))
    row = db.execute(
        "SELECT text, normalization FROM policy_artifact WHERE sha256=?", (digest,)
    ).fetchone()
    assert row == (text, "NONE")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO policy_artifact VALUES (?, ?, ?)", ("0" * 64, "甲" * 200001, "NONE")
        )
    columns = {row[1] for row in db.execute("PRAGMA table_info(policy_document)")}
    assert {
        "artifact_sha256",
        "extraction_status",
        "review_status",
        "attachments_status",
        "applicability_json",
    } <= columns
    columns = {row[1] for row in db.execute("PRAGMA table_info(evidence)")}
    assert {"start_offset", "end_offset", "api_call_json", "artifact_sha256"} <= columns
    db.close()
