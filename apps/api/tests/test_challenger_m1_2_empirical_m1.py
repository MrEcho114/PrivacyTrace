"""Challenger 2 empirical verification suite for Milestone 1 PR #88 repairs.

Author: challenger_m1_2
Scope:
1. ARSC resource parsing resilience:
   - Simulates corrupt/invalid resource IDs and exceptions in _manifest_resource_strings.
   - Verifies the worker returns [] without crashing, throwing, or dropping valid URLs.
   - Verifies corrupt resources.arsc binary file fallback preserves direct URLs.
2. Split APK permission deduplication:
   - Verifies scanning split APKs sharing the same permissions as base APK does not
     redundantly burn the 500 behavior budget.
   - Compares with the non-deduplicated counter-factual to prove bug elimination.
   - Verifies multi-split cascading permission deduplication.
3. Candidate UNREVIEWED semantics:
   - Verifies starting a draft with unreviewed candidates (checked=False) succeeds.
   - Verifies generated policy claims and documents are marked review_status='UNREVIEWED',
     completeness='PARTIAL', attachments_status='NOT_CHECKED'.
   - Verifies consistency evaluation yields MatchStatus.INSUFFICIENT_EVIDENCE and never
     falsely labels undeclared behaviors as NOT_DECLARED.
"""

import struct
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from apk_fixture_builder import apk
from fastapi.testclient import TestClient
from test_e2e_pt_mob_102 import build_test_apk
from test_web_intake import HEADERS, new_draft

from privacytrace.apk_worker import (
    _manifest_resource_strings,
    inspect_package_metadata,
    scan,
    scan_package_set,
)
from privacytrace.main import create_app
from privacytrace.models import ApiCall, MatchStatus
from privacytrace.resources import taxonomy

# ==============================================================================
# 1. ARSC Resource Parsing Resilience
# ==============================================================================


class BrokenResourcesGetPackagesNames:
    """Simulates unpack failure on resources header."""

    def get_packages_names(self):
        raise struct.error("unpack requires a buffer of 4 bytes")


class BrokenResourcesGetTypes:
    """Simulates missing or corrupt type table."""

    def get_packages_names(self):
        return ["com.example.pkg"]

    def get_types(self, owner):
        raise KeyError(f"Corrupt type table for {owner}")


class BrokenResourcesGetResIdByKey:
    """Simulates corrupt key-to-id mapping."""

    def get_packages_names(self):
        return ["com.example.pkg"]

    def get_types(self, owner):
        return []

    def get_res_id_by_key(self, owner, res_type, key):
        raise ValueError(f"Corrupt key mapping for {key}")


class BrokenResourcesXmlNameNonString:
    """Simulates resource ID pointing to non-string resource (e.g. drawable)."""

    def get_packages_names(self):
        return ["com.example.pkg"]

    def get_types(self, owner):
        return []

    def get_res_id_by_key(self, owner, res_type, key):
        return 0x7F010001

    def get_resource_xml_name(self, res_id, package=None):
        return "@drawable/icon"


class BrokenResourcesRecursionError:
    """Simulates cyclic resource aliases in ARSC."""

    def get_packages_names(self):
        return ["com.example.pkg"]

    def get_types(self, owner):
        return []

    def get_res_id_by_key(self, owner, res_type, key):
        return 0x7F010002

    def get_resource_xml_name(self, res_id, package=None):
        return "@string/cyclic_alias"

    def get_resolved_res_configs(self, res_id):
        raise RecursionError("maximum recursion depth exceeded while resolving alias")


class BrokenResourcesArbitraryException:
    """Simulates unexpected runtime exception (e.g. MemoryError, IndexError)."""

    def get_packages_names(self):
        return ["com.example.pkg"]

    def get_types(self, owner):
        return []

    def get_res_id_by_key(self, owner, res_type, key):
        return 0x7F010003

    def get_resource_xml_name(self, res_id, package=None):
        return "@string/corrupt_chunk"

    def get_resolved_res_configs(self, res_id):
        raise IndexError("buffer index out of range in string pool")


class BrokenResourcesParseIdException:
    """Simulates parse_id raising arbitrary exception."""

    def parse_id(self, value):
        raise TypeError("unsupported operand type")


def test_arsc_resource_strings_exceptions_and_corrupt_ids():
    """Empirically verify _manifest_resource_strings catches all ARSC corruption

    and error conditions, returning [] without crashing or throwing.
    """
    pkg = "com.example.pkg"

    # 1. get_packages_names raises struct.error
    assert _manifest_resource_strings("@string/foo", BrokenResourcesGetPackagesNames(), pkg) == []

    # 2. get_types raises KeyError
    assert _manifest_resource_strings("@string/foo", BrokenResourcesGetTypes(), pkg) == []

    # 3. get_res_id_by_key raises ValueError
    assert _manifest_resource_strings("@string/foo", BrokenResourcesGetResIdByKey(), pkg) == []

    # 4. get_resource_xml_name returns non-string resource (@drawable/icon)
    assert _manifest_resource_strings("@string/foo", BrokenResourcesXmlNameNonString(), pkg) == []

    # 5. get_resolved_res_configs raises RecursionError
    assert _manifest_resource_strings("@string/foo", BrokenResourcesRecursionError(), pkg) == []

    # 6. get_resolved_res_configs raises arbitrary Exception (IndexError)
    assert (
        _manifest_resource_strings("@string/foo", BrokenResourcesArbitraryException(), pkg) == []
    )

    # 7. parse_id raises TypeError / ValueError
    assert (
        _manifest_resource_strings("@0x7f010001", BrokenResourcesParseIdException(), pkg) == []
    )

    # 8. Malformed or non-existent resource reference syntaxes
    dummy = BrokenResourcesArbitraryException()
    for bad_syntax in [
        "",
        "@",
        "@string",
        "@string/",
        "@:string/foo",
        "@/string/foo",
        "@@string/foo",
        "https://example.com/not_a_resource",
        "string/no_at_symbol",
    ]:
        res = _manifest_resource_strings(bad_syntax, dummy, pkg)
        assert res == [], f"Expected [] for bad syntax: {bad_syntax}, got {res}"


def test_inspect_package_metadata_corrupt_arsc_isolation(tmp_path: Path, monkeypatch):
    """Empirically verify inspect_package_metadata isolates malformed ARSC entries

    and does NOT terminate the worker or drop prior/subsequent valid URLs.
    """
    apk_file = tmp_path / "metadata_test.apk"
    apk(apk_file)

    class MockElement:

        def __init__(self, val):
            self.val = val

        def get(self, key, default=""):
            return self.val

    # Sequence of metadata entries:
    # 1. Corrupt ARSC entry (@string/corrupt) -> throws in _manifest_resource_strings
    # 2. Valid direct URL (https://example.com/direct_1)
    # 3. Valid ARSC entry (@string/valid_arsc) -> resolves to https://example.com/from_arsc
    # 4. Another corrupt entry (@0xdeadbeef) -> returns []
    # 5. Valid direct URL (https://example.com/direct_2)
    meta_elements = [
        MockElement("@string/corrupt"),
        MockElement("https://example.com/direct_1"),
        MockElement("@string/valid_arsc"),
        MockElement("@0xdeadbeef"),
        MockElement("https://example.com/direct_2"),
    ]

    class MockXmlRoot:

        def iter(self, tag):
            if tag == "meta-data":
                return meta_elements
            return []

    class MockAXMLPrinter:

        def __init__(self, data):
            pass

        def get_xml_obj(self):
            return MockXmlRoot()

    class MockArchive:

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def namelist(self):
            return ["AndroidManifest.xml", "resources.arsc"]

        def read(self, name):
            return b"fake_arsc_bytes"

    class MockARSCParser:

        def __init__(self, data):
            pass

        def get_packages_names(self):
            return ["com.example.test"]

        def get_types(self, owner):
            return []

        def get_res_id_by_key(self, owner, res_type, key):
            if key == "corrupt":
                raise struct.error("Simulated ARSC corruption in corrupt entry")
            if key == "valid_arsc":
                return 0x7F010010
            return None

        def parse_id(self, val):
            if "deadbeef" in val:
                raise ValueError("invalid id")
            return 0x7F010010, "com.example.test"

        def get_resource_xml_name(self, res_id, package=None):
            return "@string/valid_arsc"

        def get_resolved_res_configs(self, res_id):
            return [(None, "https://example.com/from_arsc")]

    monkeypatch.setattr("privacytrace.apk_worker.ZipFile", MockArchive)
    monkeypatch.setattr("androguard.core.axml.AXMLPrinter", MockAXMLPrinter)
    monkeypatch.setattr("androguard.core.axml.ARSCParser", MockARSCParser)
    monkeypatch.setattr(
        "privacytrace.package_set.inspect_apk_bytes",
        lambda data, name: (
            type(
                "Pkg",
                (),
                {
                    "sha256": "1" * 64,
                    "package_name": "com.example.test",
                    "model_dump": lambda self, mode: {},
                },
            )(),
            [],
        ),
    )

    res = inspect_package_metadata(apk_file)

    # Worker must NOT crash, and must preserve both direct URLs and the valid ARSC URL!
    expected_urls = [
        "https://example.com/direct_1",
        "https://example.com/from_arsc",
        "https://example.com/direct_2",
    ]
    assert res["policy_urls"] == expected_urls, (
        f"Expected {expected_urls}, but got {res['policy_urls']}"
    )


def test_inspect_package_metadata_corrupt_arsc_binary_file(tmp_path: Path):
    """Empirically verify corrupt resources.arsc binary chunk in APK is caught gracefully

    and does not abort metadata inspection or drop direct URLs.
    """
    apk_file = tmp_path / "corrupt_arsc.apk"
    with ZipFile(apk_file, "w", compression=ZIP_STORED) as zf:
        # Valid minimal manifest containing a direct URL
        from test_e2e_pt_mob_102 import build_axml_manifest

        axml = build_axml_manifest(
            package_name="org.privacytrace.corrupt_arsc",
            meta_data={
                "privacy_policy_direct": "https://example.com/direct_privacy",
                "privacy_policy_arsc": "@string/privacy",
            },
        )
        zf.writestr(ZipInfo("AndroidManifest.xml", (2026, 1, 1, 0, 0, 0)), axml)
        # Corrupt resources.arsc binary chunk
        zf.writestr(
            ZipInfo("resources.arsc", (2026, 1, 1, 0, 0, 0)),
            b"GARBAGE_NON_ARSC_BYTES_CORRUPTED_FILE_DATA_9999",
        )

    res = inspect_package_metadata(apk_file)
    assert res["package_file"]["package_name"] == "org.privacytrace.corrupt_arsc"
    assert "https://example.com/direct_privacy" in res["policy_urls"]


# ==============================================================================
# 2. Split APK Permission Deduplication & 500 Behavior Budget
# ==============================================================================


def test_split_apk_permission_deduplication_preserves_500_behavior_budget(tmp_path: Path):
    """Empirically verify that scanning split APKs with identical permissions to base

    does not redundantly burn the 500 behavior budget and preserves split DEX behaviors.
    """
    tax = taxonomy()
    # 200 mapped permissions
    perms = [f"android.permission.TEST_PERM_{i}" for i in range(200)]
    rules = {
        "version": "test",
        "permission_mappings": [{"permission": p, "data_type": "CAMERA"} for p in perms],
        "api_mappings": tax["api_mappings"],
    }

    base = build_test_apk(
        tmp_path / "base.apk",
        package_name="org.privacytrace.budget",
        permissions=perms,
        dex_kind="contacts",
    )
    split1 = build_test_apk(
        tmp_path / "split1.apk",
        package_name="org.privacytrace.budget",
        split_name="split1",
        permissions=perms,
        dex_kind="camera",
    )
    split2 = build_test_apk(
        tmp_path / "split2.apk",
        package_name="org.privacytrace.budget",
        split_name="split2",
        permissions=perms,
        dex_kind="microphone",
    )

    # 1. WITH Deduplication (PR #88 repair)
    res_dedup = scan_package_set(base, [("split1", split1), ("split2", split2)], rules)

    # Base added 200 permission behaviors + 1 contacts DEX behavior = 201
    # Split 1 duplicate permissions were skipped; 2 camera DEX behaviors added
    # Split 2 duplicate permissions were skipped; 0 microphone DEX behaviors added
    # Total behaviors = 203 <= 500, no truncation!
    assert len(res_dedup["behaviors"]) == 203
    assert not any(
        "truncated at 500" in n
        for n in res_dedup["coverage"]["behavior_limitations"]
    )
    splits_in_evidence = {e.get("package_split") for e in res_dedup["evidence"]}
    assert {"base", "split1", "split2"} <= splits_in_evidence

    # 2. Counter-factual: verify that WITHOUT deduplication, behavior budget would be exhausted
    from privacytrace.apk_worker import ComponentScanContext

    s_base = scan(base, rules, component=ComponentScanContext())
    assert len(s_base["behaviors"]) == 201

    s_split1 = scan(
        split1,
        rules,
        component=ComponentScanContext("split1", len(s_base["behaviors"])),  # No dedup
    )
    assert len(s_split1["behaviors"]) == 201

    s_split2 = scan(
        split2,
        rules,
        component=ComponentScanContext(
            "split2", len(s_base["behaviors"]) + len(s_split1["behaviors"]),
        ),  # No dedup
    )
    # Split 2 starts at 402, and hits 500 at 98 behaviors, truncating remaining entries!
    assert len(s_split2["behaviors"]) == 98
    assert len(s_base["behaviors"]) + len(s_split1["behaviors"]) + len(s_split2["behaviors"]) == 500
    assert any("truncated at 500" in n for n in s_split2["coverage"]["behavior_limitations"])


def test_multi_split_permission_cascade_deduplication(tmp_path: Path):
    """Empirically verify cascading permission deduplication across 4 splits."""
    tax = taxonomy()
    # 60 permissions total
    p_base = [f"android.permission.PERM_{i}" for i in range(30)]
    p_split1 = [f"android.permission.PERM_{i}" for i in range(40)]  # 0..29 overlap Base, 30..39 new
    p_split2 = [f"android.permission.PERM_{i}" for i in range(50)]  # 0..39 overlap, 40..49 new
    p_split3 = [f"android.permission.PERM_{i}" for i in range(60)]  # 0..49 overlap, 50..59 new

    all_perms = [f"android.permission.PERM_{i}" for i in range(60)]
    rules = {
        "version": "test",
        "permission_mappings": [{"permission": p, "data_type": "CAMERA"} for p in all_perms],
        "api_mappings": tax["api_mappings"],
    }

    base = build_test_apk(
        tmp_path / "base.apk",
        package_name="org.privacytrace.cascade",
        permissions=p_base,
        dex_kind="contacts",
    )
    split1 = build_test_apk(
        tmp_path / "split1.apk",
        package_name="org.privacytrace.cascade",
        split_name="split1",
        permissions=p_split1,
        dex_kind="contacts",
    )
    split2 = build_test_apk(
        tmp_path / "split2.apk",
        package_name="org.privacytrace.cascade",
        split_name="split2",
        permissions=p_split2,
        dex_kind="contacts",
    )
    split3 = build_test_apk(
        tmp_path / "split3.apk",
        package_name="org.privacytrace.cascade",
        split_name="split3",
        permissions=p_split3,
        dex_kind="contacts",
    )

    res = scan_package_set(
        base,
        [("split1", split1), ("split2", split2), ("split3", split3)],
        rules,
    )

    # Permissions list in result must have all 60 unique permissions
    assert len(res["permissions"]) == 60
    assert res["permissions"] == sorted(all_perms)

    # Permission behaviors must be added exactly once per unique permission (60 permissions)
    perm_behaviors = [
        b for b in res["behaviors"]
        if any(e["kind"] == "MANIFEST" for e in res["evidence"] if e["id"] in b["evidence_ids"])
    ]
    assert len(perm_behaviors) == 60

    # Manifest evidence excerpts must be unique (no duplicate permission evidence)
    manifest_excerpts = [
        e["excerpt"] for e in res["evidence"] if e["kind"] == "MANIFEST"
    ]
    assert len(manifest_excerpts) == len(set(manifest_excerpts)) == 60


# ==============================================================================
# 3. Candidate UNREVIEWED Semantics & Consistency Evaluation
# ==============================================================================


def test_candidate_unreviewed_semantics_and_insufficient_evidence(tmp_path: Path):
    """Empirically verify that starting a draft with unreviewed candidates:

    1. Succeeds without requiring candidate approval.
    2. Marks policy documents as UNREVIEWED, PARTIAL, NOT_CHECKED.
    3. Evaluates consistency to INSUFFICIENT_EVIDENCE (never falsely NOT_DECLARED).
    """
    app = create_app(tmp_path / "jobs")
    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        route = f"/api/v1/web/drafts/{draft_id}"

        # Import external policy source with unreviewed candidates (checked=False)
        imported = client.post(
            f"{route}/import-external",
            headers=HEADERS,
            json={
                "source": {
                    "title": "Unreviewed Policy Draft",
                    "source_type": "OFFICIAL_WEB_POLICY",
                    "url": "https://example.com/unreviewed_policy",
                    "text": "我们在服务中仅收集相机权限用于图像分析。",
                },
                "claims": [
                    {
                        "excerpt": "我们在服务中仅收集相机权限用于图像分析。",
                        "data_type": "CAMERA",
                        "polarity": "AFFIRMATIVE",
                        "action": "ACCESS",
                    }
                ],
            },
        )
        assert imported.status_code == 200, imported.text
        cur_draft = client.get(route).json()
        assert len(cur_draft["candidates"]) == 1
        assert cur_draft["candidates"][0]["checked"] is False

        # Build APK with CAMERA permission
        apk_file = tmp_path / "sample.apk"
        apk(apk_file, camera=True)

        up_resp = client.post(route + "/apk", headers=HEADERS, content=apk_file.read_bytes())
        assert up_resp.status_code == 200, up_resp.text

        # Start analysis without checking candidates
        start_resp = client.post(
            route + "/start",
            headers=HEADERS,
            json={"revision": up_resp.json()["revision"], "request_id": uuid4().hex},
        )
        assert start_resp.status_code == 200, start_resp.text
        job_id = start_resp.json()["id"]

        # Wait for run to complete
        app.state.web_intake.futures[job_id].result(timeout=15)
        report = app.state.job_store.report(job_id)

        # 1. Document metadata strictly UNREVIEWED, PARTIAL, NOT_CHECKED
        doc = next(d for d in report.policy_documents if d.title == "Unreviewed Policy Draft")
        assert doc.review_status == "UNREVIEWED"
        assert doc.completeness == "PARTIAL"
        assert doc.attachments_status == "NOT_CHECKED"
        assert doc.extraction_status == "PARTIAL"

        # Every policy document in report must be UNREVIEWED
        for d in report.policy_documents:
            assert d.review_status == "UNREVIEWED"
            assert d.completeness == "PARTIAL"
            assert d.attachments_status == "NOT_CHECKED"

        # 2. Consistency engine must evaluate issues to INSUFFICIENT_EVIDENCE
        # (Missing evidence or unreviewed policies never generate false NOT_DECLARED passes)
        assert len(report.result.issues) > 0
        for issue in report.result.issues:
            assert issue.status == MatchStatus.INSUFFICIENT_EVIDENCE
            assert issue.status != MatchStatus.NOT_DECLARED


def test_unreviewed_policy_undeclared_behavior_evaluated_as_insufficient_evidence(tmp_path: Path):
    """Empirically verify that when an app has an observed API behavior that is NOT

    covered by an unreviewed candidate, the consistency engine outputs
    MatchStatus.INSUFFICIENT_EVIDENCE instead of MatchStatus.NOT_DECLARED.
    """
    from datetime import datetime, timezone

    from privacytrace.consistency import evaluate
    from privacytrace.models import (
        AnalysisJob,
        EvaluationInput,
        Evidence,
        PolicyDocument,
        PrivacyBehavior,
        SourceOrigin,
    )

    job = AnalysisJob(
        id="job-unreviewed-test",
        sample_id="sample-1",
        package_name="com.example.app",
        version_code=1,
        region="CN",
        product_scope="main",
        input_mode="APK",
        source_origin=SourceOrigin.REAL_SCAN,
        state="SUCCEEDED",
        ruleset_version=taxonomy()["version"],
        created_at=datetime.now(timezone.utc),
    )

    # Behavior with real API call evidence (has_api = True) for LOCATION
    api_call = ApiCall(
        target_descriptor="Landroid/location/LocationManager;->getLastKnownLocation(Ljava/lang/String;)Landroid/location/Location;",
        rule_id="android.location.last-known.generic",
        ruleset_version=taxonomy()["version"],
    )
    behavior_ev = Evidence(
        id="ev-call-location",
        kind="API",
        status="STATIC_POTENTIAL",
        source="classes.dex",
        locator="dex=classes.dex;method=getLastKnownLocation",
        excerpt="getLastKnownLocation",
        api_call=api_call,
    )
    behavior = PrivacyBehavior(
        id="bh-location",
        data_type="LOCATION",
        action="ACCESS",
        evidence_ids=[behavior_ev.id],
    )

    import hashlib
    text_unreviewed = "我们收集相机信息。"
    sha_unreviewed = hashlib.sha256(text_unreviewed.encode("utf-8")).hexdigest()

    # Unreviewed policy document (no claims for LOCATION)
    doc_unreviewed = PolicyDocument.model_validate({
        "id": "doc-unreviewed",
        "source_type": "OFFICIAL_WEB_POLICY",
        "title": "Unreviewed Policy",
        "version": "1.0",
        "captured_at": "2026-10-18T00:00:00Z",
        "artifact": {"text": text_unreviewed, "sha256": sha_unreviewed},
        "completeness": "PARTIAL",
        "extraction_status": "SUCCEEDED",
        "review_status": "UNREVIEWED",
        "attachments_status": "NOT_CHECKED",
        "applicability": {
            "package_name": "com.example.app",
            "version_codes": [1],
            "regions": ["CN"],
            "product_scope": "main",
        },
        "evidence_id": "ev-doc-1",
    })
    doc_ev = Evidence(
        id="ev-doc-1",
        kind="POLICY_DOCUMENT",
        status="DECLARED",
        source="https://example.com/privacy",
        locator="Captured UTF-8 text",
        document_id="doc-unreviewed",
        artifact_sha256=sha_unreviewed,
    )

    bundle_unreviewed = EvaluationInput(
        job=job,
        evidence=[behavior_ev, doc_ev],
        behaviors=[behavior],
        policy_documents=[doc_unreviewed],
        policy_claims=[],  # No claims for LOCATION
    )

    result_unreviewed = evaluate(bundle_unreviewed)
    assert len(result_unreviewed.issues) == 1
    issue_unreviewed = result_unreviewed.issues[0]

    # In unreviewed/partial policy, missing disclosure evaluates to INSUFFICIENT_EVIDENCE!
    assert issue_unreviewed.status == MatchStatus.INSUFFICIENT_EVIDENCE
    expected_clause = "快照、条款抽取、附件检查或全文复核未完成，不能据此判断声明缺失。"
    assert expected_clause in issue_unreviewed.explanation

    # Compare with fully reviewed policy:
    text_reviewed = "我们收集相机信息。"
    sha_reviewed = hashlib.sha256(text_reviewed.encode("utf-8")).hexdigest()
    doc_reviewed = PolicyDocument.model_validate({
        "id": "doc-reviewed",
        "source_type": "OFFICIAL_WEB_POLICY",
        "title": "Reviewed Policy",
        "version": "1.0",
        "captured_at": "2026-10-18T00:00:00Z",
        "artifact": {"text": text_reviewed, "sha256": sha_reviewed},
        "completeness": "COMPLETE",
        "extraction_status": "SUCCEEDED",
        "review_status": "REVIEWED",
        "attachments_status": "COMPLETE",
        "applicability": {
            "package_name": "com.example.app",
            "version_codes": [1],
            "regions": ["CN"],
            "product_scope": "main",
        },
        "evidence_id": "ev-doc-2",
    })
    doc_ev_2 = Evidence(
        id="ev-doc-2",
        kind="POLICY_DOCUMENT",
        status="DECLARED",
        source="https://example.com/privacy",
        locator="Captured UTF-8 text",
        document_id="doc-reviewed",
        artifact_sha256=sha_reviewed,
    )
    bundle_reviewed = EvaluationInput(
        job=job,
        evidence=[behavior_ev, doc_ev_2],
        behaviors=[behavior],
        policy_documents=[doc_reviewed],
        policy_claims=[],
    )
    result_reviewed = evaluate(bundle_reviewed)
    assert len(result_reviewed.issues) == 1
    issue_reviewed = result_reviewed.issues[0]

    # In fully reviewed policy, missing disclosure evaluates to NOT_DECLARED!
    assert issue_reviewed.status == MatchStatus.NOT_DECLARED
    assert "在本次已完成全文及附件复核的适用政策快照中未找到对应条款" in issue_reviewed.explanation
