"""Exercise the shipped collector artifacts against existing intake/report seams.

All material is synthetic; the report test replaces only APK scanning, not policy
import, quote validation, candidate persistence, or report construction.
"""

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from apk_fixture_builder import apk
from fastapi.testclient import TestClient

from privacytrace import apk_worker, pipeline
from privacytrace.main import create_app
from privacytrace.resources import taxonomy
from privacytrace.web_models import CollectedSourceInput

PACKAGE = Path(__file__).resolve().parents[3] / "skills/privacytrace-policy-collector"
EXAMPLES = json.loads((PACKAGE / "examples.json").read_text(encoding="utf-8"))
HEADERS = {"X-PrivacyTrace-Local": "1"}
VERSION = "privacytrace-policy-collector/1"


def test_generated_source_fields_follow_import_contract_not_internal_defaults():
    """A model reading the package must not inherit WebSource's official default."""
    exported = (PACKAGE / "COPY.txt").read_text(encoding="utf-8")
    schema = CollectedSourceInput.model_json_schema()
    for field, definition in schema["properties"].items():
        line = next(line for line in exported.splitlines() if line.startswith(f"- `{field}`"))
        assert json.loads(line.split(": `", 1)[1].removesuffix("`")) == definition
    assert schema["properties"]["source_type"]["default"] is None


@pytest.mark.parametrize("example", EXAMPLES["collection"], ids=lambda item: item["state"])
def test_shipped_collection_examples_enter_real_import_or_require_confirmation(tmp_path, example):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        draft = client.post("/api/v1/web/drafts", headers=HEADERS, json={
            "name": "Package fixture", "sources": [{"id": "initial", "title": "Empty"}],
        }).json()
        route = f"/api/v1/web/drafts/{draft['id']}"
        response = client.post(route + "/import-external", headers=HEADERS,
                               json={"version": VERSION, "results": [example]})
        source = example["source"]
        if source is not None and source.get("source_type") is None:
            assert response.status_code == 409
            assert response.json()["detail"] == "SOURCE_TYPE_CONFIRMATION_REQUIRED"
            assert client.get(route).json() == draft
        else:
            assert response.status_code == 200, response.text
            saved = response.json()
            assert saved["external_imports"][0]["results"][0]["state"] == example["state"]
            if example["state"] in {"RETRIEVED", "PROVIDED"}:
                captures = app.state.web_intake.captures(saved, require_checked=False)
                assert captures[0]["document"].artifact.text == source["text"]
            else:
                with pytest.raises(ValueError, match="At least one source needs policy text"):
                    app.state.web_intake.captures(saved, require_checked=False)


def report_semantics(report):
    """Compare meaning while keeping distinct acquisition receipts out of equality."""
    return {
        "documents": [doc.model_dump(mode="json", exclude={"captured_at"})
                      for doc in report.policy_documents],
        "claims": [claim.model_dump(mode="json") for claim in report.policy_claims],
        "quotes": [item.model_dump(mode="json") for item in report.evidence
                   if item.kind == "POLICY_SENTENCE"],
    }


def test_same_material_keeps_semantics_and_citations_across_three_report_entries(
    tmp_path, monkeypatch,
):
    # This scans an in-memory-built synthetic APK with the existing parser. It is
    # not Docker or real APK evidence, and no external source/model is contacted.
    sample = apk(tmp_path / "fixture.apk")
    monkeypatch.setattr(pipeline, "scan_isolated",
                        lambda path, **kwargs: apk_worker.scan(path, taxonomy()))
    app = create_app(tmp_path / "jobs")
    sources = [
        {"id": "a", "title": "App fixture", "source_type": "IN_APP_POLICY",
         "url": "https://example.invalid/app", "text": EXAMPLES["extraction"][0]["text"]},
        {"id": "b", "title": "SDK fixture", "source_type": "SDK_POLICY",
         "url": "https://example.invalid/sdk", "text": EXAMPLES["extraction"][1]["text"]},
    ]
    candidates = [
        {"id": "quote-" + item["source_id"], "source_id": item["source_id"],
         **item["candidates"][0]} for item in EXAMPLES["extraction"][:2]
    ]
    reports = []
    with TestClient(app) as client:
        for entry in ("direct", "legacy", "collector"):
            draft = client.post("/api/v1/web/drafts", headers=HEADERS, json={
                "name": "Same package material",
                "sources": sources if entry == "direct" else [{"id": "initial", "title": "Empty"}],
            }).json()
            route = f"/api/v1/web/drafts/{draft['id']}"
            if entry == "collector":
                response = client.post(route + "/import-external", headers=HEADERS, json={
                    "version": VERSION, "results": [
                        {"state": "PROVIDED", "source": source} for source in sources
                    ] + [{"state": "OFFLINE", "source": None}],
                })
                assert response.status_code == 200, response.text
                draft = response.json()
            elif entry == "legacy":
                for source in sources:
                    response = client.post(route + "/import-external", headers=HEADERS, json={
                        "source": source, "summary": "GENERATED SUMMARY MUST STAY OUT OF TEXT",
                    })
                    assert response.status_code == 200, response.text
                    draft = response.json()
            saved = client.post(route + "/candidates", headers=HEADERS, json={
                "revision": draft["revision"], "candidates": candidates,
            })
            assert saved.status_code == 200, saved.text
            draft = saved.json()
            assert all(not item["checked"] for item in draft["candidates"])
            for changes in ({"source_id": "b"}, {"excerpt": "invented quote"},
                            {"data_type": "INVENTED_TYPE"}):
                invalid = deepcopy(candidates)
                invalid[0].update(changes)
                rejected = client.post(route + "/candidates", headers=HEADERS, json={
                    "revision": draft["revision"], "candidates": invalid,
                })
                assert rejected.status_code == 409
                assert client.get(route).json() == draft
            uploaded = client.post(route + "/apk", headers=HEADERS, content=sample.read_bytes())
            assert uploaded.status_code == 200, uploaded.text
            started = client.post(route + "/start", headers=HEADERS, json={
                "revision": uploaded.json()["revision"], "request_id": uuid4().hex,
            })
            assert started.status_code == 200, started.text  # unchecked is allowed
            job_id = started.json()["id"]
            app.state.web_intake.futures[job_id].result(timeout=15)
            report = app.state.job_store.report(job_id)
            assert len(report.policy_documents) == len(report.policy_claims) == 2
            by_id = {item.id: item for item in report.evidence}
            documents = {item.id: item for item in report.policy_documents}
            for claim in report.policy_claims:
                document = documents[claim.document_id]
                assert document.version == "UNKNOWN"
                assert document.applicability.package_name is None
                assert document.review_status == "UNREVIEWED"
                assert document.completeness == document.extraction_status == "PARTIAL"
                assert document.attachments_status == "NOT_CHECKED"
                for evidence_id in claim.evidence_ids:
                    evidence = by_id[evidence_id]
                    assert evidence.document_id == document.id
                    assert document.artifact.text[
                        evidence.start_offset:evidence.end_offset
                    ] == evidence.excerpt
                    source = next(s for s in sources if "web-" + s["id"] == document.id)
                    assert evidence.source == source["url"]
                snapshot = by_id[document.evidence_id]
                origin = "MANUAL_INPUT" if entry == "direct" else "EXTERNAL_CHAT_EXPORT"
                assert f"acquisition={origin};" in snapshot.locator
                assert snapshot.artifact_sha256 == document.artifact.sha256
            if entry != "direct":
                receipts = json.loads(report.tools["web_external_imports"])
                assert receipts[0]["version"] == (
                    VERSION if entry == "collector" else "legacy-single-source"
                )
            reports.append(report_semantics(report))
    assert reports[0] == reports[1] == reports[2]
