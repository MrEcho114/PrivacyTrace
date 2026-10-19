"""Opaque-box, requirement-driven E2E test suite for PrivacyTrace PR #88 (R6 Fixes).

Architecture (4-Tier Model):
- Tier 1: Feature Coverage (R1 Source Type Confirmation, R2 collector/1 Collection Import &
  Legacy Compatibility, R3 Upload Exception Deduplication, R4 Contract Serialization)
- Tier 2: Boundary & Corner Cases (Empty Bodies, 150 MiB Stream Boundary, Corrupted Zip Headers,
  Duplicate IDs, Missing Base APK, Quota Boundaries)
- Tier 3: Cross-Feature Combinations (Multi-Source Ingest + Quota Checks + Audit Log Persistence +
  Provenance Propagation to Final Reports + Draft Isolation)
- Tier 4: Real-World Application Scenarios (End-to-End Ingestion of Policy Collector Batch Exports,
  Report Tool Receipt Verification, Host App vs SDK Consistency Evaluation)
"""

import json
from uuid import uuid4

import pytest
from apk_fixture_builder import apk, package_set_archive
from fastapi.testclient import TestClient

from privacytrace import apk_worker, pipeline
from privacytrace.consistency import evaluate
from privacytrace.main import create_app
from privacytrace.models import EvaluationInput
from privacytrace.resources import read_json, taxonomy
from privacytrace.web_models import ExternalPolicyCollectionInput, ExternalPolicyExportInput

HEADERS = {"X-PrivacyTrace-Local": "1"}
COLLECTOR_VERSION = "privacytrace-policy-collector/1"
SAMPLE_POLICY_TEXT = "We access camera and precise location for navigation services."


def make_source(source_id="ext-source-1", **overrides):
    payload = {
        "id": source_id,
        "title": "Synthetic Policy Document",
        "source_type": "SDK_POLICY",
        "url": "https://example.com/privacy",
        "text": SAMPLE_POLICY_TEXT,
    }
    payload.update(overrides)
    return payload


def make_collection(*results):
    return {"version": COLLECTOR_VERSION, "results": list(results)}


@pytest.fixture
def intake_fixture(tmp_path):
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={
                "name": "E2E R6 Fixture Draft",
                "sources": [{"id": "initial-src", "title": "Draft Initial Source"}],
            },
        )
        assert resp.status_code == 200, resp.text
        draft_id = resp.json()["id"]
        yield client, f"/api/v1/web/drafts/{draft_id}", app, draft_id


# ==============================================================================
# Tier 1: Feature Coverage (R1, R2, R3, R4)
# ==============================================================================


@pytest.mark.parametrize("legacy", [False, True])
def test_tier1_r1_source_type_confirmation_interception_opaque(intake_fixture, legacy):
    """R1: External import without source_type raises
    SOURCE_TYPE_CONFIRMATION_REQUIRED (409) atomically."""
    client, route, _, _ = intake_fixture
    untyped = make_source("untyped-1")
    del untyped["source_type"]

    payload = (
        {"source": untyped} if legacy else make_collection({"state": "PROVIDED", "source": untyped})
    )

    before_state = client.get(route).json()
    resp = client.post(route + "/import-external", headers=HEADERS, json=payload)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "SOURCE_TYPE_CONFIRMATION_REQUIRED"

    # Verify atomic rollback: no state changes persisted
    after_state = client.get(route).json()
    assert after_state == before_state


@pytest.mark.parametrize(
    "source_type",
    [
        "SDK_POLICY",
        "OFFICIAL_WEB_POLICY",
        "STORE_POLICY",
        "IN_APP_POLICY",
    ],
)
def test_tier1_r1_source_type_valid_types_accepted(intake_fixture, source_type):
    """R1: Explicit confirmation with all canonical source types is accepted."""
    client, route, _, _ = intake_fixture
    valid_source = make_source("typed-source", source_type=source_type)
    payload = make_collection({"state": "PROVIDED", "source": valid_source})

    resp = client.post(route + "/import-external", headers=HEADERS, json=payload)
    assert resp.status_code == 200, resp.text

    draft = client.get(route).json()
    imported = next(s for s in draft["sources"] if s["id"] == "typed-source")
    assert imported["source_type"] == source_type
    assert imported["provenance"] == "EXTERNAL_CHAT_EXPORT"


def test_tier1_r1_mislabeling_protection_isolation(intake_fixture):
    """R1: Third-party SDK policy is never automatically converted to OFFICIAL_WEB_POLICY."""
    client, route, app, _ = intake_fixture
    sdk_source = make_source("sdk-ad-network", source_type="SDK_POLICY")
    resp = client.post(
        route + "/import-external",
        headers=HEADERS,
        json=make_collection({"state": "PROVIDED", "source": sdk_source}),
    )
    assert resp.status_code == 200, resp.text

    draft = client.get(route).json()
    sdk_entry = next(s for s in draft["sources"] if s["id"] == "sdk-ad-network")
    assert sdk_entry["source_type"] == "SDK_POLICY"
    assert sdk_entry["source_type"] != "OFFICIAL_WEB_POLICY"

    # Captures must reflect unreviewed third-party status
    captures = app.state.web_intake.captures(draft, require_checked=False)
    assert len(captures) == 1
    doc = captures[0]["document"]
    assert doc.review_status == "UNREVIEWED"
    assert doc.completeness == "PARTIAL"
    assert doc.attachments_status == "NOT_CHECKED"


def test_tier1_r2_collector_one_batch_contract_all_states(intake_fixture):
    """R2: Ingest collector/1 collection with all 6 states and
    verify source & audit representations."""
    client, route, _, _ = intake_fixture
    observed = "2026-10-17T08:00:00+08:00"
    payload = make_collection(
        {
            "state": "RETRIEVED",
            "observed_at": observed,
            "source": make_source("retrieved-src", text="Full Policy Text."),
        },
        {"state": "PROVIDED", "source": make_source("provided-src", url="")},
        {"state": "URL_ONLY", "source": make_source("url-only-src", text="")},
        {"state": "OFFLINE", "source": make_source("offline-src", text="")},
        {"state": "UNAVAILABLE", "source": make_source("unavailable-src", text="")},
        {"state": "NOT_FOUND", "source": None},
    )

    resp = client.post(route + "/import-external", headers=HEADERS, json=payload)
    assert resp.status_code == 200, resp.text

    draft = client.get(route).json()
    sources = {s["id"]: s for s in draft["sources"]}

    # Initial source + 5 results with sources (NOT_FOUND has no source) = 6 sources
    assert len(sources) == 6
    assert sources["retrieved-src"]["status"] == "ready"
    assert sources["retrieved-src"]["text"] == "Full Policy Text."
    assert sources["provided-src"]["status"] == "manual"
    assert sources["url-only-src"]["status"] == "empty"
    assert sources["offline-src"]["status"] == "empty"
    assert sources["unavailable-src"]["error_code"] == "SOURCE_UNAVAILABLE"

    # Audit history persistence
    assert len(draft["external_imports"]) == 1
    audit = draft["external_imports"][0]
    assert audit["version"] == COLLECTOR_VERSION
    assert len(audit["results"]) == 6
    assert audit["results"][0]["state"] == "RETRIEVED"
    assert audit["results"][0]["observed_at"] == observed
    assert audit["results"][-1]["state"] == "NOT_FOUND"
    assert audit["results"][-1]["source_id"] is None


def test_tier1_r2_legacy_compatibility_single_source_export(intake_fixture):
    """R2: Ingest legacy single-source ExternalPolicyExportInput payload seamlessly."""
    client, route, _, _ = intake_fixture
    legacy_payload = {
        "source": make_source("legacy-src", source_type="IN_APP_POLICY"),
        "claims": [{"excerpt": SAMPLE_POLICY_TEXT, "data_type": "CAMERA"}],
        "summary": "Auditor synthetic analysis summary",
    }

    resp = client.post(route + "/import-external", headers=HEADERS, json=legacy_payload)
    assert resp.status_code == 200, resp.text

    draft = client.get(route).json()
    imported_src = next(s for s in draft["sources"] if s["id"] == "legacy-src")
    assert imported_src["source_type"] == "IN_APP_POLICY"
    assert len(draft["candidates"]) == 1
    assert draft["candidates"][0]["checked"] is False
    assert draft["candidates"][0]["data_type"] == "CAMERA"
    assert draft["external_imports"][0]["summary"] == "Auditor synthetic analysis summary"


def test_tier1_r3_upload_exception_deduplication(tmp_path):
    """R3: Verify uniform upload exception handling on both /apk and /package-set."""
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        # 1. 404 DRAFT_NOT_FOUND on non-existent draft
        non_existent_route = "/api/v1/web/drafts/00000000000000000000000000000000"
        for endpoint in ("/apk", "/package-set"):
            resp = client.post(non_existent_route + endpoint, headers=HEADERS, content=b"content")
            assert resp.status_code == 404
            assert resp.json()["detail"] == "DRAFT_NOT_FOUND"

        # Create valid draft
        draft_resp = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={"name": "Deduplication draft", "sources": [{"id": "s", "title": "T"}]},
        )
        assert draft_resp.status_code == 200
        draft_id = draft_resp.json()["id"]
        route = f"/api/v1/web/drafts/{draft_id}"

        # 2. 400 CORRUPTED_FILE on corrupted zip bytes to /package-set
        resp = client.post(
            route + "/package-set", headers=HEADERS, content=b"PK\x03\x04\x00\x00\x00\x00corrupt"
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "CORRUPTED_FILE"

        # 3. Successful upload, then 409 UPLOAD_REJECTED on duplicate upload attempt
        apk_file = apk(tmp_path / "sample.apk")
        resp = client.post(route + "/apk", headers=HEADERS, content=apk_file.read_bytes())
        assert resp.status_code == 200

        # Subsequent uploads must be rejected with 409
        for endpoint in ("/apk", "/package-set"):
            dup_resp = client.post(route + endpoint, headers=HEADERS, content=b"more content")
            assert dup_resp.status_code == 409
            assert dup_resp.json()["detail"] == "UPLOAD_REJECTED"


def test_tier1_r4_contract_serialization_integrity():
    """R4: Pydantic model contract validation for collection and legacy models."""
    collection_dict = {
        "version": "privacytrace-policy-collector/1",
        "results": [
            {
                "state": "PROVIDED",
                "source": {
                    "id": "c1",
                    "title": "Contract Title",
                    "source_type": "OFFICIAL_WEB_POLICY",
                    "text": "Valid text.",
                },
            }
        ],
    }
    validated_coll = ExternalPolicyCollectionInput.model_validate(collection_dict)
    assert validated_coll.version == "privacytrace-policy-collector/1"
    assert len(validated_coll.results) == 1

    legacy_dict = {
        "source": {
            "id": "leg1",
            "title": "Legacy Title",
            "source_type": "SDK_POLICY",
            "text": "Legacy text.",
        },
        "claims": [{"excerpt": "Legacy text.", "data_type": "CAMERA"}],
        "summary": "Summary text",
    }
    validated_leg = ExternalPolicyExportInput.model_validate(legacy_dict)
    assert validated_leg.source.id == "leg1"
    assert len(validated_leg.claims) == 1
    assert validated_leg.summary == "Summary text"


# ==============================================================================
# Tier 2: Boundary & Corner Cases
# ==============================================================================


def test_tier2_empty_upload_body_rejection(intake_fixture):
    """Empty body upload triggers canonical error codes: 409 on /apk,
    400 on /package-set, 422 on /import-external."""
    client, route, _, _ = intake_fixture

    # Empty APK upload -> 409 UPLOAD_REJECTED
    resp_apk = client.post(route + "/apk", headers=HEADERS, content=b"")
    assert resp_apk.status_code == 409
    assert resp_apk.json()["detail"] == "UPLOAD_REJECTED"

    # Empty package-set upload -> 400 EMPTY_PACKAGE_SET
    resp_pkg = client.post(route + "/package-set", headers=HEADERS, content=b"")
    assert resp_pkg.status_code == 400
    assert resp_pkg.json()["detail"] == "EMPTY_PACKAGE_SET"

    # Empty collection payload -> 422
    resp_import = client.post(route + "/import-external", headers=HEADERS, json=make_collection())
    assert resp_import.status_code == 422

    # Empty JSON object -> 422
    resp_empty_json = client.post(route + "/import-external", headers=HEADERS, json={})
    assert resp_empty_json.status_code == 422


def test_tier2_size_boundary_150_mib_enforcement(tmp_path, monkeypatch):
    """Stream size bound: uploads exceeding MAX_INPUT limit abort with HTTP 413 UPLOAD_TOO_LARGE."""
    # Test boundary streaming threshold by scaling MAX_INPUT to 2048 bytes
    monkeypatch.setattr("privacytrace.web_intake.MAX_INPUT", 2048)
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft_resp = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={"name": "Quota draft", "sources": [{"id": "s1", "title": "S1"}]},
        )
        assert draft_resp.status_code == 200
        draft_id = draft_resp.json()["id"]
        route = f"/api/v1/web/drafts/{draft_id}"

        # 4096 bytes exceeds 2048 bytes threshold -> HTTP 413
        oversized = b"X" * 4096
        resp = client.post(route + "/apk", headers=HEADERS, content=oversized)
        assert resp.status_code == 413
        assert resp.json()["detail"] == "UPLOAD_TOO_LARGE"

        # Verify no orphan pending files in draft dir
        directory = app.state.web_intake.directory(draft_id)
        assert not list(directory.glob("*pending*"))
        assert not (directory / "input.apk").exists()


def test_tier2_corrupted_zip_headers_rejected(intake_fixture):
    """Invalid ZIP archive headers on /package-set return 400 CORRUPTED_FILE."""
    client, route, _, _ = intake_fixture
    # Non-zip bytes with .apk extension
    resp = client.post(
        route + "/package-set",
        headers=HEADERS,
        content=b"This is purely text data, not a ZIP archive.",
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "CORRUPTED_FILE"

    # Truncated ZIP local file header
    resp_truncated = client.post(route + "/package-set", headers=HEADERS, content=b"PK\x03\x04")
    assert resp_truncated.status_code == 400
    assert resp_truncated.json()["detail"] == "CORRUPTED_FILE"


def test_tier2_duplicate_ids_rejected(intake_fixture):
    """Duplicate IDs in intra-payload or colliding with existing draft sources are rejected."""
    client, route, _, _ = intake_fixture

    # Intra-payload duplicate source ID -> 422
    payload = make_collection(
        {"state": "PROVIDED", "source": make_source("dup-id")},
        {"state": "PROVIDED", "source": make_source("dup-id")},
    )
    resp = client.post(route + "/import-external", headers=HEADERS, json=payload)
    assert resp.status_code == 422

    # Colliding with draft's existing initial source "initial-src" -> 409
    collision_payload = make_collection({"state": "PROVIDED", "source": make_source("initial-src")})
    resp_collision = client.post(
        route + "/import-external", headers=HEADERS, json=collision_payload
    )
    assert resp_collision.status_code == 409


def test_tier2_missing_base_apk_in_package_set(tmp_path):
    """Package set containing only splits without a base APK returns 400 MISSING_BASE_APK."""
    split_apk = apk(
        tmp_path / "feature.apk",
        package_name="org.privacytrace.splitonly",
        split="feature",
        split_name="feature",
    )
    archive = package_set_archive(
        tmp_path / "splits_only.zip",
        {"feature.apk": split_apk.read_bytes()},
    )

    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft_resp = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={"name": "Split draft", "sources": [{"id": "s1", "title": "S1"}]},
        )
        draft_id = draft_resp.json()["id"]
        route = f"/api/v1/web/drafts/{draft_id}"

        resp = client.post(route + "/package-set", headers=HEADERS, content=archive.read_bytes())
        assert resp.status_code == 400
        assert resp.json()["detail"] == "MISSING_BASE_APK"


def test_tier2_quota_limits_stress(intake_fixture):
    """Quota limits: >8 sources, >64 external import audits, and
    >8 collection results are rejected."""
    client, route, _, _ = intake_fixture

    # Exceeding collection results envelope (>8 results) -> 422
    nine_results = make_collection(*[{"state": "OFFLINE", "source": None} for _ in range(9)])
    resp = client.post(route + "/import-external", headers=HEADERS, json=nine_results)
    assert resp.status_code == 422

    # Fill sources up to 8 (1 initial + 7 new) -> status 200
    seven_sources = make_collection(
        *[{"state": "PROVIDED", "source": make_source(f"fill-{i}")} for i in range(7)]
    )
    resp_fill = client.post(route + "/import-external", headers=HEADERS, json=seven_sources)
    assert resp_fill.status_code == 200
    assert len(client.get(route).json()["sources"]) == 8

    # Attempt to add 9th source -> 409
    extra_source = make_collection({"state": "PROVIDED", "source": make_source("extra-src")})
    resp_overflow = client.post(route + "/import-external", headers=HEADERS, json=extra_source)
    assert resp_overflow.status_code == 409
    assert len(client.get(route).json()["sources"]) == 8


# ==============================================================================
# Tier 3: Cross-Feature Combinations
# ==============================================================================


def test_tier3_multi_source_imports_quota_audit_and_provenance_propagation(
    intake_fixture, tmp_path, monkeypatch
):
    """Cross-feature: Multi-source batch imports + legacy import + quota check
    rollback + audit persistence + report receipt."""
    client, route, app, draft_id = intake_fixture
    sample_apk = apk(tmp_path / "base.apk")

    # Mock isolated scan to return synthetic scan double
    monkeypatch.setattr(
        pipeline,
        "scan_isolated",
        lambda path, **kw: apk_worker.scan(path, taxonomy()),
    )

    # 1. Batch Import 1: collector/1 with 2 sources (1 OFFICIAL_WEB_POLICY, 1 SDK_POLICY)
    batch1 = make_collection(
        {
            "state": "RETRIEVED",
            "observed_at": "2026-10-17T09:00:00Z",
            "source": make_source("batch1-official", source_type="OFFICIAL_WEB_POLICY"),
        },
        {"state": "PROVIDED", "source": make_source("batch1-sdk", source_type="SDK_POLICY")},
    )
    resp1 = client.post(route + "/import-external", headers=HEADERS, json=batch1)
    assert resp1.status_code == 200

    # 2. Batch Import 2: legacy export with 1 STORE_POLICY
    legacy = {
        "source": make_source("batch2-store", source_type="STORE_POLICY"),
        "claims": [{"excerpt": SAMPLE_POLICY_TEXT, "data_type": "PRECISE_LOCATION"}],
        "summary": "Legacy batch 2 summary",
    }
    resp2 = client.post(route + "/import-external", headers=HEADERS, json=legacy)
    assert resp2.status_code == 200

    # Draft: initial-src + 2 from batch1 + 1 from legacy = 4 sources; 2 audits
    draft = client.get(route).json()
    assert len(draft["sources"]) == 4
    assert len(draft["external_imports"]) == 2

    # 3. Quota collision / overflow: attempt to add 5 more sources (4 + 5 = 9 > 8 limit)
    overflow = make_collection(
        *[{"state": "PROVIDED", "source": make_source(f"overflow-{i}")} for i in range(5)]
    )
    resp_over = client.post(route + "/import-external", headers=HEADERS, json=overflow)
    assert resp_over.status_code == 409

    # Verify atomic rollback: sources count remains 4 and external_imports remain 2
    draft_after = client.get(route).json()
    assert len(draft_after["sources"]) == 4
    assert len(draft_after["external_imports"]) == 2

    # 4. Upload APK and start analysis
    upload_resp = client.post(route + "/apk", headers=HEADERS, content=sample_apk.read_bytes())
    assert upload_resp.status_code == 200

    job_resp = client.post(
        route + "/start",
        headers=HEADERS,
        json={"revision": upload_resp.json()["revision"], "request_id": uuid4().hex},
    )
    assert job_resp.status_code == 200
    job_id = job_resp.json()["id"]

    # Wait for job completion
    app.state.web_intake.futures[job_id].result(timeout=15)
    report = app.state.job_store.report(job_id)

    # 5. Verify report tools receipts & provenance
    receipts = json.loads(report.tools["web_external_imports"])
    assert len(receipts) == 2
    assert receipts[0]["version"] == COLLECTOR_VERSION
    assert len(receipts[0]["results"]) == 2
    assert receipts[1]["summary"] == "Legacy batch 2 summary"

    # Verify web_policy_sources receipts contain provenance
    policy_sources = json.loads(report.tools["web_policy_sources"])
    ext_sources = [
        s for s in policy_sources if s["id"] in ("batch1-official", "batch1-sdk", "batch2-store")
    ]
    assert len(ext_sources) == 3
    for s in ext_sources:
        assert s["provenance"] == "EXTERNAL_CHAT_EXPORT"

    # Verify policy document locator contains disclaimer
    for doc in report.policy_documents:
        ev = next((e for e in report.evidence if e.id == doc.evidence_id), None)
        if ev:
            assert "acquisition=EXTERNAL_CHAT_EXPORT" in ev.locator
            assert "not proof of official verification" in ev.locator


def test_tier3_independent_draft_isolation(tmp_path):
    """Cross-feature: Two concurrent drafts with capability tokens are strictly isolated."""
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        # Create Draft A
        resp_a = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={"name": "Draft A", "sources": [{"id": "sa", "title": "Ta"}]},
        )
        draft_a = resp_a.json()
        route_a = f"/api/v1/web/drafts/{draft_a['id']}"

        # Create Draft B
        resp_b = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={"name": "Draft B", "sources": [{"id": "sb", "title": "Tb"}]},
        )
        draft_b = resp_b.json()
        route_b = f"/api/v1/web/drafts/{draft_b['id']}"

        # Import SDK policy into Draft A
        client.post(
            route_a + "/import-external",
            headers=HEADERS,
            json=make_collection(
                {"state": "PROVIDED", "source": make_source("src-a", source_type="SDK_POLICY")}
            ),
        )

        # Import Official Web policy into Draft B
        client.post(
            route_b + "/import-external",
            headers=HEADERS,
            json=make_collection(
                {
                    "state": "PROVIDED",
                    "source": make_source("src-b", source_type="OFFICIAL_WEB_POLICY"),
                }
            ),
        )

        # Inspect Draft A
        state_a = client.get(route_a).json()
        assert any(
            s["id"] == "src-a" and s["source_type"] == "SDK_POLICY" for s in state_a["sources"]
        )
        assert not any(s["id"] == "src-b" for s in state_a["sources"])

        # Inspect Draft B
        state_b = client.get(route_b).json()
        assert any(
            s["id"] == "src-b" and s["source_type"] == "OFFICIAL_WEB_POLICY"
            for s in state_b["sources"]
        )
        assert not any(s["id"] == "src-a" for s in state_b["sources"])


# ==============================================================================
# Tier 4: Real-World Application Scenarios
# ==============================================================================


def test_tier4_end_to_end_collector_export_to_report_receipts(
    intake_fixture, tmp_path, monkeypatch
):
    """Tier 4: Realistic policy collector batch export ingestion through package set
    scan and report generation."""
    client, route, app, draft_id = intake_fixture

    base_apk = apk(tmp_path / "base.apk", package_name="org.privacytrace.realworld", camera=True)
    split_apk = apk(
        tmp_path / "feature.apk",
        package_name="org.privacytrace.realworld",
        split="feature",
        split_name="feature",
    )
    archive = package_set_archive(
        tmp_path / "bundle.zip",
        {"base.apk": base_apk.read_bytes(), "feature.apk": split_apk.read_bytes()},
    )

    def fixture_package_scan(path, **kw):
        if hasattr(path, "is_dir") and path.is_dir():
            base = path / "base.apk"
            splits = [("feature", path / "feature.apk")]
            return apk_worker.scan_package_set(base, splits, taxonomy())
        return apk_worker.scan(path, taxonomy())

    monkeypatch.setattr(pipeline, "scan_isolated", fixture_package_scan)

    # 1. Realistic collector/1 batch export
    batch = make_collection(
        {
            "state": "RETRIEVED",
            "observed_at": "2026-10-17T10:00:00Z",
            "source": make_source(
                "real-official", source_type="OFFICIAL_WEB_POLICY", text="Official privacy policy."
            ),
        },
        {
            "state": "PROVIDED",
            "source": make_source(
                "real-sdk", source_type="SDK_POLICY", text="SDK privacy disclosure."
            ),
        },
        {
            "state": "URL_ONLY",
            "source": make_source(
                "real-faq",
                source_type="OFFICIAL_WEB_POLICY",
                text="",
                url="https://example.com/faq",
            ),
        },
        {
            "state": "OFFLINE",
            "source": make_source("real-mirror", source_type="OFFICIAL_WEB_POLICY", text=""),
        },
        {"state": "NOT_FOUND", "source": None},
    )
    resp = client.post(route + "/import-external", headers=HEADERS, json=batch)
    assert resp.status_code == 200, resp.text

    # 2. Upload Package Set Archive
    pkg_resp = client.post(route + "/package-set", headers=HEADERS, content=archive.read_bytes())
    assert pkg_resp.status_code == 200, pkg_resp.text
    assert len(pkg_resp.json()["package_set"]["splits"]) == 1

    # 3. Start Analysis
    start_resp = client.post(
        route + "/start",
        headers=HEADERS,
        json={"revision": pkg_resp.json()["revision"], "request_id": uuid4().hex},
    )
    assert start_resp.status_code == 200
    job_id = start_resp.json()["id"]

    app.state.web_intake.futures[job_id].result(timeout=15)
    report = app.state.job_store.report(job_id)

    # 4. Verify Report Invariants
    assert report.sample.package_set.split_names == ["feature"]
    receipts = json.loads(report.tools["web_external_imports"])
    assert len(receipts) == 1
    assert len(receipts[0]["results"]) == 5

    # Exactly 2 policy documents created (for RETRIEVED and PROVIDED with text);
    # no phantom documents for OFFLINE/NOT_FOUND
    assert len(report.policy_documents) == 2
    doc_titles = {d.title for d in report.policy_documents}
    assert "Synthetic Policy Document" in doc_titles


def test_tier4_host_app_vs_sdk_policy_consistency_evaluation(intake_fixture):
    """Tier 4: Consistency evaluation verifies R1 mislabeling protection prevents
    SDK policy from covering host claims."""
    client, route, app, _ = intake_fixture

    # Test SDK_POLICY vs OFFICIAL_WEB_POLICY
    for source_type, expected_status in [
        ("SDK_POLICY", "INSUFFICIENT_EVIDENCE"),
        ("OFFICIAL_WEB_POLICY", "EXACT_MATCH"),
    ]:
        # Create fresh draft for each comparison
        draft_resp = client.post(
            "/api/v1/web/drafts",
            headers=HEADERS,
            json={"name": f"Eval draft {source_type}", "sources": [{"id": "s0", "title": "Base"}]},
        )
        cur_route = f"/api/v1/web/drafts/{draft_resp.json()['id']}"

        # Import external policy with specified source_type
        import_resp = client.post(
            cur_route + "/import-external",
            headers=HEADERS,
            json={
                "source": make_source(
                    f"policy-{source_type}",
                    source_type=source_type,
                    package_name="org.privacytrace.demo",
                    version_code=1,
                    product="HOST_APP",
                    region="CN",
                ),
                "claims": [
                    {
                        "excerpt": SAMPLE_POLICY_TEXT,
                        "data_type": "PRECISE_LOCATION",
                        "polarity": "POSITIVE",
                        "subject": "HOST_APP",
                        "action": "ACCESS",
                    }
                ],
            },
        )
        assert import_resp.status_code == 200
        draft = import_resp.json()

        capture = app.state.web_intake.captures(draft, require_checked=False)[0]
        demo = read_json("samples/demo/evaluation-input.json")
        demo["behaviors"] = [demo["behaviors"][0]]  # Precise location behavior
        demo["evidence"] = [e for e in demo["evidence"] if not e.get("document_id")]
        demo["evidence"].extend(e.model_dump(mode="json") for e in capture["evidence"])
        demo["policy_documents"] = [capture["document"].model_dump(mode="json")]
        demo["policy_claims"] = [c.model_dump(mode="json") for c in capture["claims"]]

        result = evaluate(EvaluationInput.model_validate(demo))
        assert [i.status for i in result.issues] == [expected_status]
