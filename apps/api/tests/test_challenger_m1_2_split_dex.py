"""Adversarial stress-test harness for PT-MOB-102 Multi-Split DEX & Evidence Attribution.

Author: challenger_m1_2
Scope:
1. Split DEX namespacing invariant:
   `set(coverage.scanned_dex) | set(coverage.failed_dex) == set(sample.dex_entries)`
   `set(coverage.scanned_dex) & set(coverage.failed_dex) == set()`
   exercising complex multi-DEX splits, multi-DEX base, corrupt DEX isolation,
   missing classes.dex in base, and split without DEX entries.
2. Permission union consistency:
   Exact mathematical union and sorted deduplication across 6+ splits with
   disjoint and overlapping permissions, plus SDK tag and maxSdkVersion constraints.
3. Evidence attribution:
   Every evidence item has accurate package_split ('base' or split name), locator contains
   'split=<name>;', source starts with namespaced prefix, and policy evidence strictly
   fails Pydantic validation if package_split is attached.
4. Single-APK backward compatibility:
   Standalone single-APK scan never emits package_split, 'split=' in locators,
   or ':' namespace prefixes in dex_entries or source paths.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from apk_fixture_builder import apk as build_apk
from apk_fixture_builder import dex

from privacytrace.apk_worker import scan, scan_package_set
from privacytrace.job_store import JobStore
from privacytrace.models import AnalysisJob, EvaluationInput, Evidence, SourceOrigin
from privacytrace.package_set import validate_package_set
from privacytrace.pipeline import run as run_pipeline
from privacytrace.policy_intake import capture as capture_policy
from privacytrace.resources import taxonomy
from privacytrace.runtime_models import SampleMetadata, ScanCoverage, StoredJob

# ==============================================================================
# Helper fixtures & utilities
# ==============================================================================


@pytest.fixture
def rules():
    return taxonomy()


def make_dummy_policy(path: Path) -> Path:
    """Creates a valid captured policy directory via policy_intake.capture."""
    path.mkdir(parents=True, exist_ok=True)
    raw_path = path / "policy.txt"
    raw_path.write_text("我们收集相机权限与麦克风录音用于视频通话。", encoding="utf-8")
    out_dir = path / "capture_dir"
    return capture_policy(
        raw_path=raw_path,
        source_url="https://example.org/privacy",
        version="1",
        output_dir=out_dir,
        candidates=[
            {
                "data_type": "CAMERA",
                "action": "ACCESS",
                "excerpt": "我们收集相机权限与麦克风录音用于视频通话。",
            }
        ],
    )


# ==============================================================================
# Challenge Area 1: Split DEX Namespacing Invariant
# ==============================================================================


def test_multidex_splits_namespacing_invariant(tmp_path: Path, rules):
    """Complex multi-split sets with multi-DEX splits satisfy namespacing invariants."""
    base_apk = tmp_path / "base.apk"
    split_a = tmp_path / "split_a.apk"
    split_b = tmp_path / "split_b.apk"
    split_c = tmp_path / "split_c.apk"
    split_d = tmp_path / "split_d.apk"

    # Base APK: 2 DEX files (classes.dex, classes2.dex)
    build_apk(
        base_apk,
        package_name="org.privacytrace.multidex",
        version_code="100",
        split=False,
        entries={
            "classes.dex": dex(camera=True),
            "classes2.dex": dex(kind="android_id"),
        },
    )

    # Split A: 2 DEX files (classes.dex, classes2.dex)
    build_apk(
        split_a,
        package_name="org.privacytrace.multidex",
        version_code="100",
        split="feature.a",
        split_name="feature.a",
        entries={
            "classes.dex": dex(kind="microphone"),
            "classes2.dex": dex(camera=True),
        },
    )

    # Split B: 3 DEX files (classes.dex, classes2.dex, classes3.dex)
    build_apk(
        split_b,
        package_name="org.privacytrace.multidex",
        version_code="100",
        split="feature.b",
        split_name="feature.b",
        entries={
            "classes.dex": dex(kind="contacts"),
            "classes2.dex": dex(kind="media"),
            "classes3.dex": dex(camera=True),
        },
    )

    # Split C: 1 non-primary DEX file only (classes2.dex)
    build_apk(
        split_c,
        package_name="org.privacytrace.multidex",
        version_code="100",
        split="feature.c",
        split_name="feature.c",
        entries={
            "classes2.dex": dex(kind="microphone"),
        },
    )

    # Split D: 1 primary DEX file (classes.dex)
    build_apk(
        split_d,
        package_name="org.privacytrace.multidex",
        version_code="100",
        split="feature.d",
        split_name="feature.d",
        entries={
            "classes.dex": dex(kind="android_id"),
        },
    )

    splits = [
        ("feature.a", split_a),
        ("feature.b", split_b),
        ("feature.c", split_c),
        ("feature.d", split_d),
    ]

    result = scan_package_set(base_apk, splits, rules)

    expected_dex_entries = [
        "base:classes.dex",
        "base:classes2.dex",
        "split:feature.a:classes.dex",
        "split:feature.a:classes2.dex",
        "split:feature.b:classes.dex",
        "split:feature.b:classes2.dex",
        "split:feature.b:classes3.dex",
        "split:feature.c:classes2.dex",
        "split:feature.d:classes.dex",
    ]
    assert result["dex_entries"] == expected_dex_entries

    scanned_dex = set(result["coverage"]["scanned_dex"])
    failed_dex = set(result["coverage"]["failed_dex"])
    sample_dex_entries = set(result["dex_entries"])

    # 1. Mathematical invariant: scanned | failed == entries
    assert scanned_dex | failed_dex == sample_dex_entries
    # 2. Mutually disjoint invariant: scanned & failed == empty
    assert scanned_dex & failed_dex == set()
    # 3. All DEX files scanned cleanly
    assert not failed_dex
    assert len(scanned_dex) == 9
    # 4. Completeness must be COMPLETE
    assert result["coverage"]["completeness"] == "COMPLETE"

    # 5. StoredJob runtime model validation enforces coverage accounting
    sample_meta = SampleMetadata(
        name="Challenger Multi-DEX Sample",
        package_name=result["package_name"],
        version_code=result["version_code"],
        version_name=result["version_name"],
        apk_sha256=result["apk_sha256"],
        permissions=result["permissions"],
        dex_entries=result["dex_entries"],
        package_set=result["package_set"],
    )
    cov_data = {k: v for k, v in result["coverage"].items() if k != "completeness"}
    scan_cov = ScanCoverage.model_validate(
        {**cov_data, "status": result["coverage"]["completeness"]}
    )

    job = AnalysisJob(
        id="job-challenger-multidex",
        sample_id="sample-challenger-multidex",
        input_mode="APK",
        source_origin=SourceOrigin.REAL_SCAN,
        state="SUCCEEDED",
        ruleset_version=rules["version"],
        created_at=datetime.now(timezone.utc),
        package_name=result["package_name"],
        version_code=result["version_code"],
    )
    bundle = EvaluationInput(
        job=job,
        evidence=result["evidence"],
        behaviors=result["behaviors"],
        policy_documents=[],
        policy_claims=[],
    )
    stored_job = StoredJob(
        job=job,
        bundle=bundle,
        sample=sample_meta,
        coverage=scan_cov,
        tools=result["tools"],
    )
    assert stored_job.sample.dex_entries == expected_dex_entries


def test_multidex_splits_with_corrupted_dex_entries(tmp_path: Path, rules):
    """Corrupted DEX files in base and splits are cleanly tracked in failed_dex
    without breaking coverage accounting.
    """
    base_apk = tmp_path / "base.apk"
    split_1 = tmp_path / "split_1.apk"
    split_2 = tmp_path / "split_2.apk"
    split_3 = tmp_path / "split_3.apk"

    # Base APK: classes.dex (valid) + classes2.dex (corrupt)
    build_apk(
        base_apk,
        package_name="org.privacytrace.corrupt",
        version_code="1",
        split=False,
        entries={
            "classes.dex": dex(camera=True),
            "classes2.dex": b"NOT_A_VALID_DEX_HEADER_GARBAGE_BYTES_12345",
        },
    )

    # Split 1: classes.dex (valid) + classes2.dex (corrupt)
    build_apk(
        split_1,
        package_name="org.privacytrace.corrupt",
        version_code="1",
        split="feature.corrupt1",
        split_name="feature.corrupt1",
        entries={
            "classes.dex": dex(kind="microphone"),
            "classes2.dex": b"ANOTHER_CORRUPT_DEX_BYTES_99999",
        },
    )

    # Split 2: classes.dex (corrupt)
    build_apk(
        split_2,
        package_name="org.privacytrace.corrupt",
        version_code="1",
        split="feature.corrupt2",
        split_name="feature.corrupt2",
        entries={
            "classes.dex": b"CORRUPT_PRIMARY_DEX_00000",
        },
    )

    # Split 3: classes.dex (valid)
    build_apk(
        split_3,
        package_name="org.privacytrace.corrupt",
        version_code="1",
        split="feature.clean3",
        split_name="feature.clean3",
        entries={
            "classes.dex": dex(kind="contacts"),
        },
    )

    splits = [
        ("feature.corrupt1", split_1),
        ("feature.corrupt2", split_2),
        ("feature.clean3", split_3),
    ]

    result = scan_package_set(base_apk, splits, rules)

    scanned_dex = set(result["coverage"]["scanned_dex"])
    failed_dex = set(result["coverage"]["failed_dex"])
    sample_dex_entries = set(result["dex_entries"])

    expected_failed = {
        "base:classes2.dex",
        "split:feature.corrupt1:classes2.dex",
        "split:feature.corrupt2:classes.dex",
    }
    expected_scanned = {
        "base:classes.dex",
        "split:feature.corrupt1:classes.dex",
        "split:feature.clean3:classes.dex",
    }

    assert failed_dex == expected_failed
    assert scanned_dex == expected_scanned

    # 1. Invariant: scanned | failed == entries
    assert scanned_dex | failed_dex == sample_dex_entries
    assert scanned_dex & failed_dex == set()

    # 2. Completeness MUST be PARTIAL due to failed DEX entries
    assert result["coverage"]["completeness"] == "PARTIAL"

    # 3. Errors list contains exactly 3 DEX_PARSE_FAILED entries with namespaced paths
    dex_errors = [e for e in result["errors"] if e.get("code") == "DEX_PARSE_FAILED"]
    assert len(dex_errors) == 3
    error_messages = [e["message"] for e in dex_errors]
    assert any("base:classes2.dex" in msg for msg in error_messages)
    assert any("split:feature.corrupt1:classes2.dex" in msg for msg in error_messages)
    assert any("split:feature.corrupt2:classes.dex" in msg for msg in error_messages)

    # 4. Verify StoredJob model validator enforces that PARTIAL passes while COMPLETE fails
    sample_meta = SampleMetadata(
        name="Challenger Corrupt DEX Sample",
        package_name=result["package_name"],
        version_code=result["version_code"],
        version_name=result["version_name"],
        apk_sha256=result["apk_sha256"],
        permissions=result["permissions"],
        dex_entries=result["dex_entries"],
        package_set=result["package_set"],
    )
    job = AnalysisJob(
        id="job-challenger-corrupt",
        sample_id="sample-challenger-corrupt",
        input_mode="APK",
        source_origin=SourceOrigin.REAL_SCAN,
        state="SUCCEEDED",
        ruleset_version=rules["version"],
        created_at=datetime.now(timezone.utc),
        package_name=result["package_name"],
        version_code=result["version_code"],
    )
    bundle = EvaluationInput(
        job=job,
        evidence=result["evidence"],
        behaviors=result["behaviors"],
        policy_documents=[],
        policy_claims=[],
    )

    # PARTIAL coverage passes
    cov_dict = {k: v for k, v in result["coverage"].items() if k != "completeness"}
    cov_partial = ScanCoverage.model_validate({**cov_dict, "status": "PARTIAL"})
    StoredJob(
        job=job,
        bundle=bundle,
        sample=sample_meta,
        coverage=cov_partial,
        tools=result["tools"],
    )

    # Falsely claiming COMPLETE with failed DEX entries MUST raise ValueError
    cov_complete = ScanCoverage.model_validate({**cov_dict, "status": "COMPLETE"})
    with pytest.raises(ValueError, match="Failed DEX entries cannot be COMPLETE"):
        StoredJob(
            job=job,
            bundle=bundle,
            sample=sample_meta,
            coverage=cov_complete,
            tools=result["tools"],
        )


def test_split_without_dex_entries_coverage_invariant(tmp_path: Path, rules):
    """A resource-only or config split with 0 DEX entries preserves coverage accounting."""
    base_apk = tmp_path / "base.apk"
    split_res = tmp_path / "split_res.apk"
    split_code = tmp_path / "split_code.apk"

    build_apk(
        base_apk,
        package_name="org.privacytrace.resonly",
        version_code="5",
        split=False,
        entries={"classes.dex": dex(camera=True)},
    )

    # Resource-only split: empty entries dict (no classes.dex at all)
    build_apk(
        split_res,
        package_name="org.privacytrace.resonly",
        version_code="5",
        split="config.fr",
        split_name="config.fr",
        entries={},
    )

    # Code split: classes.dex
    build_apk(
        split_code,
        package_name="org.privacytrace.resonly",
        version_code="5",
        split="feature.pay",
        split_name="feature.pay",
        entries={"classes.dex": dex(kind="contacts")},
    )

    splits = [
        ("config.fr", split_res),
        ("feature.pay", split_code),
    ]

    result = scan_package_set(base_apk, splits, rules)

    expected_entries = ["base:classes.dex", "split:feature.pay:classes.dex"]
    assert result["dex_entries"] == expected_entries
    assert set(result["coverage"]["scanned_dex"]) == set(expected_entries)
    assert result["coverage"]["failed_dex"] == []
    assert result["coverage"]["completeness"] == "COMPLETE"
    assert set(result["coverage"]["scanned_dex"]) | set(result["coverage"]["failed_dex"]) == set(
        result["dex_entries"]
    )


def test_base_missing_classes_dex_results_in_partial_completeness(tmp_path: Path, rules):
    """Missing primary classes.dex in base APK forces PARTIAL completeness
    even if splits have classes.dex.
    """
    base_apk = tmp_path / "base.apk"
    split_1 = tmp_path / "split_1.apk"

    # Base has classes2.dex only (missing classes.dex)
    build_apk(
        base_apk,
        package_name="org.privacytrace.nobaseprimary",
        version_code="1",
        split=False,
        entries={"classes2.dex": dex(camera=True)},
    )

    # Split has classes.dex
    build_apk(
        split_1,
        package_name="org.privacytrace.nobaseprimary",
        version_code="1",
        split="feature.sub",
        split_name="feature.sub",
        entries={"classes.dex": dex(kind="microphone")},
    )

    splits = [("feature.sub", split_1)]
    result = scan_package_set(base_apk, splits, rules)

    assert "base:classes.dex" not in result["dex_entries"]
    assert "base:classes2.dex" in result["dex_entries"]
    assert "split:feature.sub:classes.dex" in result["dex_entries"]

    # Invariant still holds
    assert set(result["coverage"]["scanned_dex"]) | set(result["coverage"]["failed_dex"]) == set(
        result["dex_entries"]
    )
    # Completeness must be PARTIAL because base:classes.dex was absent
    assert result["coverage"]["completeness"] == "PARTIAL"


# ==============================================================================
# Challenge Area 2: Permission Union Consistency Across 5+ Splits
# ==============================================================================


def test_permission_union_consistency_across_six_splits(tmp_path: Path, rules):
    """Permission union across base and 6 splits is strictly deduplicated, sorted, and complete."""
    base_apk = tmp_path / "base.apk"
    split_1 = tmp_path / "split_1.apk"
    split_2 = tmp_path / "split_2.apk"
    split_3 = tmp_path / "split_3.apk"
    split_4 = tmp_path / "split_4.apk"
    split_5 = tmp_path / "split_5.apk"
    split_6 = tmp_path / "split_6.apk"

    pkg = "org.privacytrace.permunion"

    # Base: CAMERA, INTERNET
    build_apk(
        base_apk,
        package_name=pkg,
        version_code="10",
        split=False,
        permission="android.permission.CAMERA",
        sdk_23_permission="android.permission.INTERNET",
    )

    # Split 1: RECORD_AUDIO, CAMERA (overlaps Base)
    build_apk(
        split_1,
        package_name=pkg,
        version_code="10",
        split="split.audio",
        split_name="split.audio",
        permission="android.permission.RECORD_AUDIO",
        sdk_23_permission="android.permission.CAMERA",
    )

    # Split 2: ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION (disjoint from Base)
    build_apk(
        split_2,
        package_name=pkg,
        version_code="10",
        split="split.location",
        split_name="split.location",
        permission="android.permission.ACCESS_FINE_LOCATION",
        sdk_23_permission="android.permission.ACCESS_COARSE_LOCATION",
    )

    # Split 3: ACCESS_FINE_LOCATION (overlaps Split 2), READ_CONTACTS
    build_apk(
        split_3,
        package_name=pkg,
        version_code="10",
        split="split.contacts",
        split_name="split.contacts",
        permission="android.permission.ACCESS_FINE_LOCATION",
        sdk_23_permission="android.permission.READ_CONTACTS",
    )

    # Split 4: READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
    build_apk(
        split_4,
        package_name=pkg,
        version_code="10",
        split="split.storage",
        split_name="split.storage",
        permission="android.permission.READ_EXTERNAL_STORAGE",
        sdk_23_permission="android.permission.WRITE_EXTERNAL_STORAGE",
    )

    # Split 5: CAMERA (overlaps Base & Split 1), RECORD_AUDIO (overlaps Split 1)
    build_apk(
        split_5,
        package_name=pkg,
        version_code="10",
        split="split.media_extra",
        split_name="split.media_extra",
        permission="android.permission.CAMERA",
        sdk_23_permission="android.permission.RECORD_AUDIO",
    )

    # Split 6: BLUETOOTH, INTERNET (overlaps Base)
    build_apk(
        split_6,
        package_name=pkg,
        version_code="10",
        split="split.bt",
        split_name="split.bt",
        permission="android.permission.BLUETOOTH",
        sdk_23_permission="android.permission.INTERNET",
    )

    splits = [
        ("split.audio", split_1),
        ("split.location", split_2),
        ("split.contacts", split_3),
        ("split.storage", split_4),
        ("split.media_extra", split_5),
        ("split.bt", split_6),
    ]

    result = scan_package_set(base_apk, splits, rules)

    expected_permissions = sorted(
        {
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.BLUETOOTH",
            "android.permission.CAMERA",
            "android.permission.INTERNET",
            "android.permission.READ_CONTACTS",
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.RECORD_AUDIO",
            "android.permission.WRITE_EXTERNAL_STORAGE",
        }
    )

    # Exact mathematical union match
    assert result["permissions"] == expected_permissions
    # Strict sorting invariant
    assert result["permissions"] == sorted(result["permissions"])
    # Zero duplicates
    assert len(result["permissions"]) == len(set(result["permissions"]))

    # Check manifest evidence attribution
    manifest_ev = [e for e in result["evidence"] if e["kind"] == "MANIFEST"]
    # Base manifest evidence
    base_manifest = [e for e in manifest_ev if e.get("package_split") == "base"]
    assert any("android.permission.CAMERA" in e["excerpt"] for e in base_manifest)

    # Split manifest evidence
    split_manifest = [e for e in manifest_ev if e.get("package_split") != "base"]
    for ev in split_manifest:
        assert ev["package_split"] in [s_name for s_name, _ in splits]
        assert f"split={ev['package_split']};" in ev["locator"]

    # Exact condition manifest deduplication:
    # Split 5 declared CAMERA with uses-permission (identical to Base) -> must be deduplicated
    split_5_cam = [
        e
        for e in split_manifest
        if e["package_split"] == "split.media_extra" and "android.permission.CAMERA" in e["excerpt"]
    ]
    assert len(split_5_cam) == 0, (
        "Identical uses-permission CAMERA in Split 5 must be deduplicated against Base"
    )

    # Split 6 declared INTERNET with uses-permission-sdk-23 (identical to Base)
    # -> must be deduplicated
    split_6_net = [
        e
        for e in split_manifest
        if e["package_split"] == "split.bt" and "android.permission.INTERNET" in e["excerpt"]
    ]
    assert len(split_6_net) == 0, (
        "Identical uses-permission-sdk-23 INTERNET in Split 6 must be deduplicated against Base"
    )

    # Split 1 declared CAMERA with uses-permission-sdk-23 (different condition than Base)
    # -> preserved as a distinct conditional capability scoped to Split 1
    split_1_cam = [
        e
        for e in split_manifest
        if e["package_split"] == "split.audio" and "android.permission.CAMERA" in e["excerpt"]
    ]
    assert len(split_1_cam) == 1
    assert "min_sdk=23" in split_1_cam[0]["locator"]
    assert "split=split.audio;" in split_1_cam[0]["locator"]


def test_permission_union_preserves_sdk_conditions(tmp_path: Path, rules):
    """Permissions with maxSdkVersion and uses-permission-sdk-23 preserve conditions."""
    base_apk = tmp_path / "base.apk"
    split_1 = tmp_path / "split_1.apk"

    pkg = "org.privacytrace.sdkcond"

    # Base has fine location with maxSdkVersion=28
    build_apk(
        base_apk,
        package_name=pkg,
        version_code="1",
        split=False,
        permission="android.permission.ACCESS_FINE_LOCATION",
        manifest_options={"max_sdk": 28},
    )

    # Split has camera with uses-permission-sdk-23
    build_apk(
        split_1,
        package_name=pkg,
        version_code="1",
        split="feature.cam",
        split_name="feature.cam",
        permission="android.permission.INTERNET",
        sdk_23_permission="android.permission.CAMERA",
    )

    splits = [("feature.cam", split_1)]
    result = scan_package_set(base_apk, splits, rules)

    assert "android.permission.ACCESS_FINE_LOCATION" in result["permissions"]
    assert "android.permission.CAMERA" in result["permissions"]

    loc_ev = [
        e
        for e in result["evidence"]
        if e["kind"] == "MANIFEST" and "ACCESS_FINE_LOCATION" in e["excerpt"]
    ]
    assert len(loc_ev) == 1
    assert "max_sdk=28" in loc_ev[0]["locator"]
    assert loc_ev[0]["package_split"] == "base"
    assert "split=base;" in loc_ev[0]["locator"]

    cam_ev = [e for e in result["evidence"] if e["kind"] == "MANIFEST" and "CAMERA" in e["excerpt"]]
    assert len(cam_ev) == 1
    assert "min_sdk=23" in cam_ev[0]["locator"]
    assert cam_ev[0]["package_split"] == "feature.cam"
    assert "split=feature.cam;" in cam_ev[0]["locator"]


# ==============================================================================
# Challenge Area 3: Evidence Attribution & Policy Evidence Isolation
# ==============================================================================


def test_evidence_attribution_and_locator_split_prefix(tmp_path: Path, rules):
    """Every evidence item in multi-split analysis has accurate package_split,
    namespaced locator, and valid Evidence model.
    """
    base_apk = tmp_path / "base.apk"
    split_mic = tmp_path / "split_mic.apk"
    split_contact = tmp_path / "split_contact.apk"

    pkg = "org.privacytrace.attribution_deep"

    build_apk(
        base_apk,
        package_name=pkg,
        version_code="1",
        split=False,
        permission="android.permission.CAMERA",
        camera=True,
    )

    build_apk(
        split_mic,
        package_name=pkg,
        version_code="1",
        split="split.audio",
        split_name="split.audio",
        permission="android.permission.RECORD_AUDIO",
        kind="microphone",
    )

    build_apk(
        split_contact,
        package_name=pkg,
        version_code="1",
        split="split.contacts",
        split_name="split.contacts",
        permission="android.permission.READ_CONTACTS",
        kind="contacts",
    )

    splits = [
        ("split.audio", split_mic),
        ("split.contacts", split_contact),
    ]

    result = scan_package_set(base_apk, splits, rules)

    expected_splits = {"base", "split.audio", "split.contacts"}
    assert len(result["evidence"]) >= 3

    for ev in result["evidence"]:
        # 1. package_split must be non-empty and in expected_splits
        split_val = ev.get("package_split")
        assert split_val in expected_splits, (
            f"Evidence {ev['id']} has invalid package_split: {split_val}"
        )

        # 2. Locator must contain 'split=<split_val>;'
        assert f"split={split_val};" in ev["locator"], (
            f"Evidence {ev['id']} locator missing split={split_val};"
        )

        # 3. Source must start with namespaced prefix
        if split_val == "base":
            assert ev["source"].startswith("base:"), (
                f"Base evidence source must start with 'base:': {ev['source']}"
            )
        else:
            assert ev["source"].startswith(f"split:{split_val}:"), (
                f"Split evidence source must start with 'split:{split_val}:': {ev['source']}"
            )

        # 4. Must pass Pydantic validation
        validated = Evidence.model_validate(ev)
        assert validated.package_split == split_val

    # 5. Behavior orphan prevention: all behavior evidence_ids must point to real evidence
    all_ev_ids = {e["id"] for e in result["evidence"]}
    for bh in result["behaviors"]:
        for ev_id in bh["evidence_ids"]:
            assert ev_id in all_ev_ids, f"Behavior {bh['id']} references orphan evidence {ev_id}"


def test_policy_evidence_strictly_rejects_package_split():
    """Policy evidence (POLICY_DOCUMENT, POLICY_SENTENCE) strictly fails
    validation if package_split is set.
    """
    # 1. POLICY_DOCUMENT with package_split="base"
    with pytest.raises(ValueError, match="Policy evidence must not reference a package split"):
        Evidence(
            id="ev-doc-base",
            kind="POLICY_DOCUMENT",
            status="DECLARED",
            source="https://example.com/privacy",
            locator="doc=1",
            document_id="doc-1",
            artifact_sha256="a" * 64,
            package_split="base",
        )

    # 2. POLICY_DOCUMENT with package_split="split_name"
    with pytest.raises(ValueError, match="Policy evidence must not reference a package split"):
        Evidence(
            id="ev-doc-split",
            kind="POLICY_DOCUMENT",
            status="DECLARED",
            source="https://example.com/privacy",
            locator="doc=1",
            document_id="doc-1",
            artifact_sha256="b" * 64,
            package_split="config.en",
        )

    # 3. POLICY_SENTENCE with package_split="base"
    with pytest.raises(ValueError, match="Policy evidence must not reference a package split"):
        Evidence(
            id="ev-sent-base",
            kind="POLICY_SENTENCE",
            status="DECLARED",
            source="https://example.com/privacy",
            locator="sentence=1",
            excerpt="We collect camera photos.",
            document_id="doc-1",
            start_offset=0,
            end_offset=24,
            package_split="base",
        )

    # 4. POLICY_SENTENCE with package_split="feature.a"
    with pytest.raises(ValueError, match="Policy evidence must not reference a package split"):
        Evidence(
            id="ev-sent-split",
            kind="POLICY_SENTENCE",
            status="DECLARED",
            source="https://example.com/privacy",
            locator="sentence=1",
            excerpt="We collect camera photos.",
            document_id="doc-1",
            start_offset=0,
            end_offset=24,
            package_split="feature.a",
        )

    # 5. POLICY_SENTENCE with package_split="" (empty string is also not None)
    with pytest.raises(ValueError, match="Policy evidence must not reference a package split"):
        Evidence(
            id="ev-sent-empty",
            kind="POLICY_SENTENCE",
            status="DECLARED",
            source="https://example.com/privacy",
            locator="sentence=1",
            excerpt="We collect camera photos.",
            document_id="doc-1",
            start_offset=0,
            end_offset=24,
            package_split="",
        )

    # 6. Valid policy sentence with package_split=None passes cleanly
    valid_policy_sentence = Evidence(
        id="ev-sent-valid",
        kind="POLICY_SENTENCE",
        status="DECLARED",
        source="https://example.com/privacy",
        locator="sentence=1",
        excerpt="We collect camera photos.",
        document_id="doc-1",
        start_offset=0,
        end_offset=24,
        package_split=None,
    )
    assert valid_policy_sentence.package_split is None


def test_static_evidence_kinds_accept_package_split():
    """All static evidence kinds (MANIFEST, API, SDK) accept package_split and None."""
    # MANIFEST
    ev_manifest = Evidence(
        id="ev-man-1",
        kind="MANIFEST",
        status="STATIC_POTENTIAL",
        source="base:AndroidManifest.xml",
        locator="apk_sha256=1234;split=base;permission=CAMERA",
        excerpt="android.permission.CAMERA",
        package_split="base",
    )
    assert ev_manifest.package_split == "base"

    # API
    ev_api = Evidence(
        id="ev-api-1",
        kind="API",
        status="STATIC_POTENTIAL",
        source="split:feature.audio:classes.dex",
        locator="apk_sha256=1234;split=feature.audio;dex=classes.dex;target=AudioRecord->startRecording",
        excerpt="invoke-virtual startRecording",
        api_call={
            "target_descriptor": "Landroid/media/AudioRecord;->startRecording()V",
            "rule_id": "rule-audio-1",
            "ruleset_version": "1.0",
        },
        package_split="feature.audio",
    )
    assert ev_api.package_split == "feature.audio"

    # SDK
    ev_sdk = Evidence(
        id="ev-sdk-1",
        kind="SDK",
        status="STATIC_POTENTIAL",
        source="split:feature.ads:classes.dex",
        locator="apk_sha256=1234;split=feature.ads;dex=classes.dex;class=com.google.android.gms.ads.AdView",
        excerpt="AdView matches Google Ads",
        package_split="feature.ads",
    )
    assert ev_sdk.package_split == "feature.ads"

    # Legacy static evidence with package_split=None
    ev_legacy = Evidence(
        id="ev-legacy-1",
        kind="MANIFEST",
        status="STATIC_POTENTIAL",
        source="AndroidManifest.xml",
        locator="apk_sha256=1234;permission=CAMERA",
        excerpt="android.permission.CAMERA",
        package_split=None,
    )
    assert ev_legacy.package_split is None


# ==============================================================================
# Challenge Area 4: Single-APK Backward Compatibility
# ==============================================================================


def test_single_apk_scan_no_package_split_leakage(tmp_path: Path, rules):
    """Direct standalone scan of a single APK never emits package_split,
    'split=' locators, or ':' namespaces.
    """
    single_apk = tmp_path / "single.apk"

    build_apk(
        single_apk,
        package_name="org.privacytrace.standalone_challenger",
        version_code="42",
        version_name="3.2.1",
        split=False,
        permission="android.permission.CAMERA",
        camera=True,
    )

    result = scan(single_apk, rules)

    # 1. dex_entries must NOT contain ':' or 'base:'
    for dex_entry in result["dex_entries"]:
        assert ":" not in dex_entry, f"DEX entry leaked namespace prefix: {dex_entry}"
        assert not dex_entry.startswith("base:")
        assert not dex_entry.startswith("split:")

    # 2. scanned_dex must NOT contain ':' or 'base:'
    for dex_entry in result["coverage"]["scanned_dex"]:
        assert ":" not in dex_entry, f"Scanned DEX leaked namespace prefix: {dex_entry}"

    # 3. Evidence items must NOT contain package_split or 'split=' in locator
    assert len(result["evidence"]) >= 1
    for ev in result["evidence"]:
        assert ev.get("package_split") is None, f"Single APK evidence leaked package_split: {ev}"
        assert "split=" not in ev["locator"], (
            f"Single APK locator leaked split parameter: {ev['locator']}"
        )
        assert not ev["source"].startswith("base:"), (
            f"Single APK source leaked base prefix: {ev['source']}"
        )
        assert not ev["source"].startswith("split:"), (
            f"Single APK source leaked split prefix: {ev['source']}"
        )

    # 4. Result dict must NOT contain package_set key
    assert "package_set" not in result or result.get("package_set") is None


def test_single_apk_pipeline_end_to_end_backward_compatibility(tmp_path: Path):
    """Full pipeline execution with a single APK publishes a report with zero split leakage."""
    job_store = JobStore(tmp_path / "jobs")
    receipt_path = make_dummy_policy(tmp_path / "policy")
    single_apk = tmp_path / "single.apk"

    build_apk(
        single_apk,
        package_name="org.privacytrace.pipe_single",
        version_code="1",
        split=False,
        permission="android.permission.CAMERA",
        camera=True,
    )

    result = run_pipeline(
        apk=single_apk,
        policy=receipt_path,
        name="Single APK Pipeline Test",
        job_id="job-pipe-single",
        store_dir=tmp_path / "jobs",
    )
    assert result["status"] == "SUCCEEDED"

    report = job_store.report("job-pipe-single")
    assert report.coverage.status == "COMPLETE"

    # 1. No namespaces in dex_entries or scanned_dex
    for entry in report.sample.dex_entries:
        assert ":" not in entry
    for entry in report.coverage.scanned_dex:
        assert ":" not in entry

    # 2. package_set summary must be None for single APK
    assert report.sample.package_set is None

    # 3. Evidence: every item has package_split is None
    for ev in report.evidence:
        assert ev.package_split is None
        assert "split=" not in ev.locator


def test_multi_split_pipeline_end_to_end_attribution(tmp_path: Path, monkeypatch):
    """Full pipeline execution with a package set correctly publishes report
    with split attribution and coverage completeness.
    """
    packages_dir = tmp_path / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    job_store = JobStore(tmp_path / "jobs")
    receipt_path = make_dummy_policy(tmp_path / "policy")

    base_apk = packages_dir / "base.apk"
    split_apk = packages_dir / "split_cam.apk"

    pkg = "org.privacytrace.pipe_split"

    build_apk(
        base_apk,
        package_name=pkg,
        version_code="7",
        split=False,
        permission="android.permission.INTERNET",
    )

    build_apk(
        split_apk,
        package_name=pkg,
        version_code="7",
        split="feature.cam",
        split_name="feature.cam",
        permission="android.permission.CAMERA",
        camera=True,
    )

    pkg_set = validate_package_set(packages_dir)

    # Controlled parser double. Actual container transport is covered separately.
    def fixture_scan(path, **kwargs):
        assert path == packages_dir
        return scan_package_set(base_apk, [("feature.cam", split_apk)], taxonomy())

    monkeypatch.setattr("privacytrace.pipeline.scan_isolated", fixture_scan)

    result = run_pipeline(
        apk=packages_dir,
        policy=receipt_path,
        name="Multi-Split Pipeline Test",
        job_id="job-pipe-split",
        store_dir=tmp_path / "jobs",
        package_set=pkg_set.model_dump(),
    )
    assert result["status"] == "SUCCEEDED"

    report = job_store.report("job-pipe-split")
    assert report.coverage.status == "COMPLETE"

    # 1. sample.package_set is populated
    assert report.sample.package_set is not None
    assert report.sample.package_set.split_count == 1
    assert report.sample.package_set.split_names == ["feature.cam"]

    # 2. Namespaced dex_entries
    assert "base:classes.dex" in report.sample.dex_entries
    assert "split:feature.cam:classes.dex" in report.sample.dex_entries

    # 3. Evidence split attribution
    static_ev = [e for e in report.evidence if e.kind in ("MANIFEST", "API", "SDK")]
    policy_ev = [e for e in report.evidence if e.kind in ("POLICY_DOCUMENT", "POLICY_SENTENCE")]

    assert len(static_ev) >= 2
    assert len(policy_ev) >= 1

    for ev in static_ev:
        assert ev.package_split in ("base", "feature.cam")
        assert f"split={ev.package_split};" in ev.locator

    for ev in policy_ev:
        assert ev.package_split is None
        assert "split=" not in ev.locator
