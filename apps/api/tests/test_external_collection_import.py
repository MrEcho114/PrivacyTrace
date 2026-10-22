"""HTTP collection compatibility and policy semantics; all materials are synthetic."""

import json
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest
from apk_fixture_builder import apk
from fastapi.testclient import TestClient
from test_web_intake import HEADERS

from privacytrace import apk_worker, pipeline, web_intake
from privacytrace.consistency import evaluate
from privacytrace.main import create_app
from privacytrace.models import EvaluationInput
from privacytrace.policy_llm_extractor import MockLLMClient
from privacytrace.resources import read_json, taxonomy

VERSION = "privacytrace-policy-collector/1"
TEXT = "We access precise location."


def source(source_id="external", **changes):
    return {
        "id": source_id, "title": "Synthetic policy", "source_type": "SDK_POLICY",
        "url": "https://example.invalid/privacy", "text": TEXT, **changes,
    }


def collection(*results):
    return {"version": VERSION, "results": list(results)}


@pytest.fixture
def intake(tmp_path):
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        response = client.post("/api/v1/web/drafts", headers=HEADERS, json={
            "name": "Collection fixture", "sources": [{"id": "placeholder", "title": "Empty"}],
        })
        assert response.status_code == 200, response.text
        yield client, f"/api/v1/web/drafts/{response.json()['id']}", app


def test_canonical_all_states_preserve_sources_and_external_audit(intake):
    client, route, app = intake
    observed = "2026-10-16T03:00:00+08:00"
    response = client.post(route + "/import-external", headers=HEADERS, json=collection(
        {"state": "RETRIEVED", "observed_at": observed,
         "source": source("retrieved", text="Original\r\n政策正文。")},
        {"state": "PROVIDED", "source": source("provided", url="")},
        {"state": "URL_ONLY", "source": source("link", text="")},
        {"state": "OFFLINE", "source": source("offline-link", text="")},
        {"state": "UNAVAILABLE", "source": source("unavailable", text="")},
        {"state": "OFFLINE", "source": None},
        {"state": "NOT_FOUND", "source": None},
    ))
    assert response.status_code == 200, response.text
    draft = client.get(route).json()
    sources = {s["id"]: s for s in draft["sources"]}
    assert len(sources) == 6 and not draft["candidates"]
    assert sources["retrieved"]["text"] == "Original\r\n政策正文。"
    assert sources["retrieved"]["sha256"] == sha256("Original\r\n政策正文。".encode()).hexdigest()
    assert sources["retrieved"]["status"] == "ready"
    assert sources["provided"]["status"] == "manual"
    for key in ("retrieved", "provided"):
        assert sources[key]["source_type"] == "SDK_POLICY"
        assert sources[key]["captured_at"] != observed
        assert sources[key]["final_url"] is None
    for key in ("link", "offline-link", "unavailable"):
        assert not sources[key]["text"] and sources[key]["captured_at"] is None
    assert sources["link"]["status"] == sources["offline-link"]["status"] == "empty"
    assert sources["unavailable"]["error_code"] == "SOURCE_UNAVAILABLE"
    audit = draft["external_imports"][0]
    assert audit["version"] == VERSION and len(audit["results"]) == 7
    assert audit["results"][0]["observed_at"] == observed
    assert audit["results"][-1] == {
        "state": "NOT_FOUND", "source_id": None, "source_type": None, "observed_at": None,
    }
    captures = app.state.web_intake.captures(draft, require_checked=False)
    assert len(captures) == 2
    assert all(c["document"].review_status == "UNREVIEWED" for c in captures)
    assert all(c["document"].completeness == "PARTIAL" for c in captures)
    assert all(c["document"].attachments_status == "NOT_CHECKED" for c in captures)


def test_source_less_not_found_and_offline_may_omit_source_entirely(intake):
    """#241: the documented NOT_FOUND/OFFLINE shape omits `source`, not nulls it."""
    client, route, _ = intake
    response = client.post(route + "/import-external", headers=HEADERS, json=collection(
        {"state": "NOT_FOUND"},
        {"state": "OFFLINE", "observed_at": "2026-10-16T03:00:00+08:00"},
    ))
    assert response.status_code == 200, response.text
    draft = client.get(route).json()
    assert [s["id"] for s in draft["sources"]] == ["placeholder"]
    assert not draft["candidates"]
    audit = draft["external_imports"][0]
    assert [r["state"] for r in audit["results"]] == ["NOT_FOUND", "OFFLINE"]
    assert [r["source_id"] for r in audit["results"]] == [None, None]
    assert audit["results"][1]["observed_at"] == "2026-10-16T03:00:00+08:00"


@pytest.mark.parametrize("state", ["RETRIEVED", "PROVIDED", "URL_ONLY", "UNAVAILABLE"])
def test_states_that_need_a_source_still_reject_an_omitted_one(intake, state):
    """#241 keeps the other states strict: a missing source is not a discovery result."""
    client, route, _ = intake
    before = client.get(route).json()
    response = client.post(route + "/import-external", headers=HEADERS, json=collection(
        {"state": state},
    ))
    assert response.status_code == 422, response.text
    assert client.get(route).json() == before


@pytest.mark.parametrize("claim, stored", [
    ({"excerpt": TEXT, "data_type": "PRECISE_LOCATION"}, None),
    ({"excerpt": TEXT, "data_type": "PRECISE_LOCATION", "condition": None}, None),
    ({"excerpt": TEXT, "data_type": "PRECISE_LOCATION", "condition": ""}, None),
    ({"excerpt": TEXT, "data_type": "PRECISE_LOCATION",
      "condition": "仅在用户开启定位时"}, "仅在用户开启定位时"),
])
def test_legacy_empty_condition_is_stored_as_absent(intake, claim, stored):
    """#247: an empty condition declares no condition; non-empty text stays verbatim."""
    client, route, app = intake
    response = client.post(route + "/import-external", headers=HEADERS, json={
        "source": source(), "claims": [claim],
    })
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["candidates"][0]["condition"] == stored
    capture = app.state.web_intake.captures(draft, require_checked=False)[0]
    assert capture["claims"][0].condition == stored


@pytest.mark.parametrize("claim, status", [
    ({"condition": 5}, 422),
    ({"condition": "x" * 1001}, 422),
    ({"excerpt": "not in the source", "condition": ""}, 409),
])
def test_legacy_invalid_conditions_are_still_rejected(intake, claim, status):
    """#247 normalization does not loosen quote, type, or length validation."""
    client, route, _ = intake
    before = client.get(route).json()
    body = {"excerpt": TEXT, "data_type": "PRECISE_LOCATION", **claim}
    response = client.post(route + "/import-external", headers=HEADERS, json={
        "source": source(), "claims": [body],
    })
    assert response.status_code == status, response.text
    assert client.get(route).json() == before


@pytest.mark.parametrize("source_type", [
    "SDK_POLICY", "OFFICIAL_WEB_POLICY", "STORE_POLICY", "IN_APP_POLICY",
])
def test_legacy_import_type_controls_host_disclosure(intake, source_type):
    client, route, app = intake
    response = client.post(route + "/import-external", headers=HEADERS, json={
        "source": source(source_type=source_type, package_name="org.privacytrace.demo",
                         version_code=1, region="CN", product="HOST_APP"),
        "claims": [{"excerpt": TEXT, "data_type": "PRECISE_LOCATION", "polarity": "POSITIVE",
                    "subject": "HOST_APP", "action": "ACCESS"}],
    })
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["sources"][-1]["source_type"] == source_type
    assert draft["candidates"][0]["checked"] is False
    capture = app.state.web_intake.captures(draft, require_checked=False)[0]
    demo = read_json("samples/demo/evaluation-input.json")
    demo["behaviors"] = [demo["behaviors"][0]]
    demo["evidence"] = [e for e in demo["evidence"] if not e.get("document_id")]
    demo["evidence"].extend(e.model_dump(mode="json") for e in capture["evidence"])
    demo["policy_documents"] = [capture["document"].model_dump(mode="json")]
    demo["policy_claims"] = [c.model_dump(mode="json") for c in capture["claims"]]
    result = evaluate(EvaluationInput.model_validate(demo))
    expected = "INSUFFICIENT_EVIDENCE" if source_type == "SDK_POLICY" else "EXACT_MATCH"
    assert [i.status for i in result.issues] == [expected]


@pytest.mark.parametrize("legacy", [False, True])
def test_unknown_source_type_requires_confirmation_without_writes(intake, legacy):
    client, route, _ = intake
    unknown = source()
    del unknown["source_type"]
    payload = (
        {"source": unknown} if legacy else collection({"state": "PROVIDED", "source": unknown})
    )
    before = client.get(route).json()
    response = client.post(route + "/import-external", headers=HEADERS, json=payload)
    assert response.status_code == 409
    assert response.json()["detail"] == "SOURCE_TYPE_CONFIRMATION_REQUIRED"
    assert client.get(route).json() == before


@pytest.mark.parametrize("result", [
    {"state": "RETRIEVED", "source": None},
    {"state": "URL_ONLY", "source": None},
    {"state": "UNAVAILABLE", "source": None},
    {"state": "NOT_FOUND", "source": source(text="")},
    {"state": "OFFLINE", "source": source()},
    {"state": "URL_ONLY", "source": source()},
    {"state": "UNAVAILABLE", "source": source()},
    {"state": "RETRIEVED", "source": source(text="")},
    {"state": "PROVIDED", "source": source(text="   ")},
    {"state": "RETRIEVED", "source": source(url="")},
    {"state": "OFFLINE", "source": source(url="", text="")},
    {"state": "PROVIDED", "source": source(id=None)},
    {"state": "PROVIDED", "source": source(status="ready")},
    {"state": "PROVIDED", "source": source(captured_at="2026-10-16T00:00:00Z")},
    {"state": "PROVIDED", "source": source(model_audit={"official": True})},
    {"state": "PROVIDED", "source": source(source_type="UNKNOWN")},
    {"state": "PROVIDED", "source": source(text="x" * 200001)},
    {"state": "PROVIDED", "source": source(), "observed_at": "2026-10-16T00:00:00"},
    {"state": "PROVIDED", "source": source(), "observed_at": 0},
    {"state": "PROVIDED", "source": source(), "summary": "Not a collector field"},
])
def test_invalid_collection_is_rejected_atomically(intake, result):
    client, route, _ = intake
    before = client.get(route).json()
    response = client.post(route + "/import-external", headers=HEADERS, json=collection(result))
    assert response.status_code == 422, response.text
    assert client.get(route).json() == before


@pytest.mark.parametrize("payload", [
    {"version": "privacytrace-policy-collector/2",
     "results": [{"state": "OFFLINE", "source": None}]},
    collection(),
    collection(*[{"state": "OFFLINE", "source": None}] * 9),
    collection(*[{"state": "PROVIDED", "source": source()}] * 2),
    {**collection({"state": "OFFLINE", "source": None}), "unexpected": True},
])
def test_collection_envelope_validation(intake, payload):
    client, route, _ = intake
    before = client.get(route).json()
    assert client.post(route + "/import-external", headers=HEADERS, json=payload).status_code == 422
    assert client.get(route).json() == before


def test_collection_id_collision_and_source_quota_leave_no_partial_import(intake):
    client, route, _ = intake
    payload = collection(*[
        {"state": "PROVIDED", "source": source(f"s{i}")} for i in range(7)
    ], {"state": "NOT_FOUND", "source": None})
    response = client.post(route + "/import-external", headers=HEADERS, json=payload)
    assert response.status_code == 200, response.text  # Eight results, eight total sources.
    before = client.get(route).json()
    for extra in (source("s0"), source("extra")):
        response = client.post(route + "/import-external", headers=HEADERS,
                               json=collection({"state": "PROVIDED", "source": extra}))
        assert response.status_code == 409
        assert client.get(route).json() == before


def test_source_less_failure_audit_is_bounded(intake):
    client, route, _ = intake
    payload = collection({"state": "OFFLINE", "source": None})
    for _ in range(64):
        response = client.post(route + "/import-external", headers=HEADERS, json=payload)
        assert response.status_code == 200, response.text
    before = client.get(route).json()
    assert len(before["sources"]) == 1 and not before["candidates"]
    assert client.post(route + "/import-external", headers=HEADERS, json=payload).status_code == 409
    assert client.get(route).json() == before


@pytest.mark.parametrize("changes", [
    {"status": "failed"}, {"status": "empty"}, {"status": "url_only"},
    {"text": "", "status": "manual"},
])
def test_legacy_state_body_mismatch_rejected(intake, changes):
    client, route, _ = intake
    before = client.get(route).json()
    response = client.post(route + "/import-external", headers=HEADERS,
                           json={"source": source(**changes)})
    assert response.status_code == 409
    assert client.get(route).json() == before


def test_unknown_taxonomy_quote_is_not_persisted(intake):
    client, route, _ = intake
    before = client.get(route).json()
    response = client.post(route + "/import-external", headers=HEADERS, json={
        "source": source(), "claims": [{"excerpt": TEXT, "data_type": "INVENTED_TYPE"}],
    })
    assert response.status_code == 409
    assert client.get(route).json() == before


def test_collection_retrieved_without_fetch_keeps_external_acquisition(
    intake, tmp_path, monkeypatch
):
    client, route, app = intake
    sample = apk(tmp_path / "fixture.apk")
    monkeypatch.setattr(pipeline, "scan_isolated",
                        lambda path, **kw: apk_worker.scan(path, taxonomy()))
    imported = client.post(route + "/import-external", headers=HEADERS, json=collection(
        {"state": "RETRIEVED", "source": source("retrieved")},
    ))
    assert imported.status_code == 200, imported.text
    draft = client.get(route).json()
    retrieved = next(s for s in draft["sources"] if s["id"] == "retrieved")
    assert retrieved["status"] == "ready"
    uploaded = client.post(route + "/apk", headers=HEADERS, content=sample.read_bytes())
    started = client.post(route + "/start", headers=HEADERS, json={
        "revision": uploaded.json()["revision"], "request_id": uuid4().hex,
    })
    assert started.status_code == 200, started.text
    job_id = started.json()["id"]
    app.state.web_intake.futures[job_id].result(timeout=15)
    report = app.state.job_store.report(job_id)
    document = next(d for d in report.policy_documents if d.id == "web-retrieved")
    locator = next(ev.locator for ev in report.evidence if ev.id == document.evidence_id)
    assert "acquisition=EXTERNAL_CHAT_EXPORT;" in locator


def test_collection_audit_survives_fetch_extract_and_persisted_report(
    intake, tmp_path, monkeypatch
):
    client, route, app = intake
    sample = apk(tmp_path / "fixture.apk")
    monkeypatch.setattr(pipeline, "scan_isolated",
                        lambda path, **kw: apk_worker.scan(path, taxonomy()))
    monkeypatch.setattr(web_intake, "fetch_policy", lambda url: {
        "status": "ready", "text": TEXT, "captured_at": "2026-10-17T00:00:00Z",
        "sha256": sha256(TEXT.encode()).hexdigest(), "final_url": url,
    })
    monkeypatch.setattr(web_intake, "UrllibLLMClient", lambda **kw: MockLLMClient(
        lambda *a: json.dumps([{"excerpt": TEXT, "data_type": "PRECISE_LOCATION"}])
    ))
    observed = "2026-10-16T00:00:00Z"
    response = client.post(route + "/import-external", headers=HEADERS, json=collection(
        {"state": "RETRIEVED", "source": source(), "observed_at": observed},
        {"state": "OFFLINE", "source": None},
    ))
    assert response.status_code == 200, response.text
    audit = deepcopy(response.json()["external_imports"])
    # Legacy summaries are acquisition audit data even after model audit is replaced.
    response = client.post(route + "/import-external", headers=HEADERS, json={
        "source": source("summary-source"), "summary": "SYNTHETIC MODEL SUMMARY",
    })
    assert response.status_code == 200, response.text
    for operation in ("fetch", "extract"):
        if operation == "extract":
            configured = client.post("/api/v1/web/settings", headers=HEADERS, json={
                "enabled": True, "api_base": "http://127.0.0.1:9001/v1", "model": "fixture",
            })
            assert configured.status_code == 200
        draft = client.get(route).json()
        response = client.post(route + f"/sources/external/{operation}", headers=HEADERS,
                               json={"revision": draft["revision"]})
        assert response.status_code == 200, response.text
    assert response.json()["external_imports"][0] == audit[0]
    updated = client.post(route + "/apk", headers=HEADERS, content=sample.read_bytes())
    job = client.post(route + "/start", headers=HEADERS, json={
        "revision": updated.json()["revision"], "request_id": uuid4().hex,
    })
    assert job.status_code == 200, job.text
    app.state.web_intake.futures[job.json()["id"]].result(timeout=15)
    report = app.state.job_store.report(job.json()["id"])
    receipts = json.loads(report.tools["web_external_imports"])
    assert receipts[0] == audit[0]
    assert receipts[1]["summary"] == "SYNTHETIC MODEL SUMMARY"
    assert all(d.source_type == "SDK_POLICY" for d in report.policy_documents)
    assert len(report.policy_documents) == 2  # OFFLINE/null never fabricated a document.
    assert "SYNTHETIC MODEL SUMMARY" not in json.dumps([
        d.model_dump(mode="json") for d in report.policy_documents
    ])
    candidates = client.get(route).json()["candidates"]
    assert candidates and all(not c["checked"] for c in candidates)
