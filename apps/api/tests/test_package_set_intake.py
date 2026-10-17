"""Unit and contract tests for PT-MOB-102 (Issue #70) Multi-Package APK Set Intake.

Covers:
- Dual-mode endpoints (/apk auto-detection and /package-set)
- Package set data models and AXML binary inspection
- All 10 integrity rules & rejection modes
- Transactional staging, rollback, and zero-orphan guarantees
- Pre-body capability auth on /package-set
- Multi-package DEX scanning, permission aggregation, coverage completeness,
  and evidence split attribution
- Backward compatibility for standalone single APK scans
"""

from pathlib import Path

import pytest
from apk_fixture_builder import apk as build_apk
from apk_fixture_builder import apk_bytes, package_set_archive
from fastapi.testclient import TestClient

from privacytrace.apk_worker import scan, scan_package_set
from privacytrace.main import create_app
from privacytrace.models import Evidence
from privacytrace.package_set import (
    MAX_FILE_SIZE,
    PackageFile,
    PackagePart,
    PackageSetIntegrityError,
    PackageSetManifestInput,
    validate_package_set,
)
from privacytrace.resources import taxonomy

HEADERS = {"X-PrivacyTrace-Local": "1"}
pytestmark = pytest.mark.usefixtures("synthetic_package_metadata")


def create_draft(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/web/drafts",
        headers=HEADERS,
        json={
            "name": "Multi-package test draft",
            "sources": [
                {
                    "id": "src-1",
                    "title": "Privacy Policy",
                    "text": "我们收集相机权限与麦克风录音用于视频通话。",
                    "status": "manual",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ==============================================================================
# Positive Intake Flows
# ==============================================================================


def test_single_apk_intake_via_package_set_endpoint(tmp_path: Path):
    """Single APK uploaded via /package-set sets up package_set and input.apk."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    raw_apk = apk_bytes(
        package_name="org.privacytrace.single",
        version_code=7,
        version_name="1.0",
        camera=True,
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=raw_apk,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["uploaded"] is True
    assert updated["package_set"] is not None

    pkg_set = updated["package_set"]
    assert pkg_set["package_name"] == "org.privacytrace.single"
    assert pkg_set["version_code"] == 7
    assert pkg_set["base"]["part"] == "BASE"
    assert pkg_set["base"]["split_name"] is None
    assert pkg_set["splits"] == []
    assert updated["apk_sha256"] == pkg_set["base"]["sha256"]

    draft_dir = tmp_path / "web" / draft_id
    assert (draft_dir / "input.apk").is_file()
    assert (draft_dir / "packages" / "base.apk").is_file()
    assert (draft_dir / "input.apk").read_bytes() == raw_apk


def test_single_apk_intake_via_legacy_apk_endpoint_backward_compatibility(tmp_path: Path):
    """Single APK uploaded via legacy /apk maintains exact backward compatibility."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    raw_apk = apk_bytes(
        package_name="org.privacytrace.single",
        version_code=7,
        version_name="1.0",
        camera=True,
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        headers=HEADERS,
        content=raw_apk,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["uploaded"] is True
    assert updated["package_set"] is None

    draft_dir = tmp_path / "web" / draft_id
    assert (draft_dir / "input.apk").is_file()
    assert (draft_dir / "input.apk").read_bytes() == raw_apk


def test_valid_multi_package_bundle_intake(tmp_path: Path):
    """Valid package set archive uploaded via /package-set succeeds."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    base = apk_bytes(
        package_name="org.privacytrace.multiset",
        version_code=42,
        version_name="2.1",
        split=False,
        camera=True,
    )
    split_en = apk_bytes(
        package_name="org.privacytrace.multiset",
        version_code=42,
        version_name="2.1",
        split="config.en",
        provider="network",
    )
    split_arm = apk_bytes(
        package_name="org.privacytrace.multiset",
        version_code=42,
        version_name="2.1",
        split="config.arm64_v8a",
        kind="microphone",
    )

    archive = package_set_archive(
        apks={
            "base.apk": base,
            "split_config.en.apk": split_en,
            "split_config.arm64_v8a.apk": split_arm,
        }
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=archive,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["uploaded"] is True
    assert updated["package_set"] is not None

    pkg_set = updated["package_set"]
    assert pkg_set["package_name"] == "org.privacytrace.multiset"
    assert pkg_set["version_code"] == 42
    assert pkg_set["base"]["part"] == "BASE"
    assert len(pkg_set["splits"]) == 2
    split_names = {s["split_name"] for s in pkg_set["splits"]}
    assert split_names == {"config.en", "config.arm64_v8a"}

    draft_dir = tmp_path / "web" / draft_id
    assert (draft_dir / "input.apk").is_file()
    assert (draft_dir / "input.apk").read_bytes() == base
    assert (draft_dir / "packages" / "base.apk").is_file()
    assert (draft_dir / "packages" / "split_config.en.apk").is_file()
    assert (draft_dir / "packages" / "split_config.arm64_v8a.apk").is_file()


def test_transparent_multi_package_on_legacy_apk_endpoint(tmp_path: Path):
    """Uploading a multi-package archive to legacy /apk auto-detects and accepts it."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    base = apk_bytes(
        package_name="org.privacytrace.autodetect",
        version_code=10,
        split=False,
    )
    split = apk_bytes(
        package_name="org.privacytrace.autodetect",
        version_code=10,
        split="feature.chat",
    )
    archive = package_set_archive(apks={"base.apk": base, "split_chat.apk": split})

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        headers=HEADERS,
        content=archive,
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["uploaded"] is True
    assert updated["package_set"] is not None
    assert len(updated["package_set"]["splits"]) == 1
    assert updated["package_set"]["splits"][0]["split_name"] == "feature.chat"


# ==============================================================================
# All 10 Integrity Rules & Rejection Modes
# ==============================================================================


def test_rejection_rule_1_empty_package_set(tmp_path: Path):
    """Rule 1: Empty package set (0 files or no APKs) is rejected with 400."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    # 1a: Zero bytes upload
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=b"",
    )
    assert resp.status_code == 400
    assert "EMPTY_PACKAGE_SET" in resp.text

    # 1b: Zip archive with non-APK files only
    archive = package_set_archive(apks={"README.txt": b"no apks here"})
    resp2 = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=archive,
    )
    assert resp2.status_code == 400
    assert "EMPTY_PACKAGE_SET" in resp2.text


def test_rejection_rule_2_single_file_too_large(tmp_path: Path):
    """Rule 2: Single APK exceeding 150 MiB limit raises UPLOAD_TOO_LARGE (413)."""
    fake_oversized_file = PackageFile(
        file_name="huge.apk",
        part=PackagePart.BASE,
        sha256="a" * 64,
        size_bytes=MAX_FILE_SIZE + 1024,
        package_name="org.oversized",
        version_code=1,
    )
    with pytest.raises(PackageSetIntegrityError) as exc_info:
        validate_package_set([fake_oversized_file])
    assert exc_info.value.code == "UPLOAD_TOO_LARGE"
    assert exc_info.value.http_status == 413


def test_rejection_rule_3_cumulative_set_too_large(tmp_path: Path):
    """Rule 3: Cumulative size of all files exceeding 150 MiB raises PACKAGE_SET_TOO_LARGE (413)."""
    base = PackageFile(
        file_name="base.apk",
        part=PackagePart.BASE,
        sha256="a" * 64,
        size_bytes=80 * 1024 * 1024,
        package_name="org.cumulativetoolarge",
        version_code=1,
    )
    split = PackageFile(
        file_name="split.apk",
        part=PackagePart.SPLIT,
        split_name="feature",
        sha256="b" * 64,
        size_bytes=80 * 1024 * 1024,
        package_name="org.cumulativetoolarge",
        version_code=1,
    )
    # Total = 160 MiB > 150 MiB
    with pytest.raises(PackageSetIntegrityError) as exc_info:
        validate_package_set([base, split])
    assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE"
    assert exc_info.value.http_status == 413


def test_rejection_rule_4_corrupted_file(tmp_path: Path):
    """Rule 4: Corrupted ZIP archive or damaged AXML is rejected with CORRUPTED_FILE (400)."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    # 4a: Corrupted raw bytes (not a ZIP)
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=b"CORRUPTED_RAW_NON_ZIP_BYTES",
    )
    assert resp.status_code == 400
    assert "CORRUPTED_FILE" in resp.text

    # 4b: ZIP containing APK with corrupted AndroidManifest.xml
    corrupted_apk = bytearray(apk_bytes())
    # Corrupt the ZIP entry for manifest
    manifest_idx = corrupted_apk.find(b"AndroidManifest.xml")
    assert manifest_idx != -1
    corrupted_apk[manifest_idx : manifest_idx + 10] = b"DamagedXml"

    bad_archive = package_set_archive(apks={"base.apk": bytes(corrupted_apk)})
    resp2 = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=bad_archive,
    )
    assert resp2.status_code == 400
    assert "CORRUPTED_FILE" in resp2.text


def test_rejection_rule_5_missing_base_apk(tmp_path: Path):
    """Rule 5: Archive containing only split APKs without a base APK is rejected."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    split1 = apk_bytes(package_name="org.nobase", version_code=1, split="config.en")
    split2 = apk_bytes(package_name="org.nobase", version_code=1, split="config.hdpi")

    archive = package_set_archive(apks={"split1.apk": split1, "split2.apk": split2})
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=archive,
    )
    assert resp.status_code == 400
    assert "MISSING_BASE_APK" in resp.text


def test_rejection_rule_6_multiple_base_apks(tmp_path: Path):
    """Rule 6: Archive containing multiple base APKs is rejected with MULTIPLE_BASE_APKS."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    base1 = apk_bytes(package_name="org.multibase", version_code=1, split=False)
    base2 = apk_bytes(package_name="org.multibase", version_code=1, split=False)

    archive = package_set_archive(apks={"base1.apk": base1, "base2.apk": base2})
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=archive,
    )
    assert resp.status_code == 400
    assert "MULTIPLE_BASE_APKS" in resp.text


def test_rejection_rule_7_split_package_mismatch(tmp_path: Path):
    """Rule 7: Split declaring a different package name than base is rejected."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    base = apk_bytes(package_name="org.correct.base", version_code=1, split=False)
    split = apk_bytes(package_name="org.imposter.split", version_code=1, split="config.en")

    archive = package_set_archive(apks={"base.apk": base, "split.apk": split})
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=archive,
    )
    assert resp.status_code == 400
    assert "SPLIT_PACKAGE_MISMATCH" in resp.text


def test_rejection_rule_8_split_version_code_mismatch(tmp_path: Path):
    """Rule 8: Split declaring a different version code than base is rejected."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    base = apk_bytes(package_name="org.versioncheck", version_code=100, split=False)
    split = apk_bytes(package_name="org.versioncheck", version_code=101, split="config.en")

    archive = package_set_archive(apks={"base.apk": base, "split.apk": split})
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=archive,
    )
    assert resp.status_code == 400
    assert "VERSION_CODE_MISMATCH" in resp.text


def test_rejection_rule_9_duplicate_split_name(tmp_path: Path):
    """Rule 9: Multiple splits declaring the same split name are rejected."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    base = apk_bytes(package_name="org.dupsplit", version_code=5, split=False)
    split1 = apk_bytes(package_name="org.dupsplit", version_code=5, split="config.en")
    split2 = apk_bytes(package_name="org.dupsplit", version_code=5, split="config.en")

    archive = package_set_archive(
        apks={"base.apk": base, "split1.apk": split1, "split2.apk": split2}
    )
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=archive,
    )
    assert resp.status_code == 400
    assert "DUPLICATE_SPLIT_NAME" in resp.text


def test_rejection_rule_10_declared_sha256_mismatch(tmp_path: Path):
    """Rule 10: Declared manifest SHA-256 mismatch raises SHA256_MISMATCH."""
    base_file = PackageFile(
        file_name="base.apk",
        part=PackagePart.BASE,
        sha256="a" * 64,
        size_bytes=1000,
        package_name="org.shamismatch",
        version_code=1,
    )
    manifest = PackageSetManifestInput(
        package_name="org.shamismatch",
        version_code=1,
        files=[
            PackageFile(
                file_name="base.apk",
                part=PackagePart.BASE,
                sha256="b" * 64,  # Intentionally altered digest
                size_bytes=1000,
                package_name="org.shamismatch",
                version_code=1,
            )
        ],
    )
    with pytest.raises(PackageSetIntegrityError) as exc_info:
        validate_package_set([base_file], declared_manifest=manifest)
    assert exc_info.value.code == "SHA256_MISMATCH"


# ==============================================================================
# Transactional Rollback & Zero Orphans
# ==============================================================================


def test_transactional_rollback_leaves_zero_orphans(tmp_path: Path):
    """When intake validation fails, staging files are purged, leaving zero orphans."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]
    draft_dir = tmp_path / "web" / draft_id

    # Upload invalid package set (mismatched package name)
    base = apk_bytes(package_name="org.base.pkg", version_code=1, split=False)
    split = apk_bytes(package_name="org.wrong.pkg", version_code=1, split="config.en")
    bad_archive = package_set_archive(apks={"base.apk": base, "split.apk": split})

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=bad_archive,
    )
    assert resp.status_code == 400
    assert "SPLIT_PACKAGE_MISMATCH" in resp.text

    # Verify zero orphan staging directories or partial files
    pending_dirs = list(draft_dir.glob("packages.pending.*"))
    pending_files = list(draft_dir.glob("upload.pending.*"))
    assert len(pending_dirs) == 0, f"Found orphan staging dirs: {pending_dirs}"
    assert len(pending_files) == 0, f"Found orphan pending files: {pending_files}"
    assert not (draft_dir / "packages").exists()
    assert not (draft_dir / "input.apk").exists()

    # Draft metadata remains untouched
    fresh_draft = client.get(f"/api/v1/web/drafts/{draft_id}").json()
    assert fresh_draft["uploaded"] is False
    assert fresh_draft.get("package_set") is None

    # Subsequent valid upload succeeds cleanly
    valid_base = apk_bytes(package_name="org.base.pkg", version_code=1, split=False)
    valid_archive = package_set_archive(apks={"base.apk": valid_base})
    resp_retry = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        headers=HEADERS,
        content=valid_archive,
    )
    assert resp_retry.status_code == 200
    assert resp_retry.json()["uploaded"] is True


# ==============================================================================
# Pre-Body Authorization Bounds
# ==============================================================================


def test_pre_body_auth_on_package_set_endpoint(tmp_path: Path):
    """Posting to /package-set without valid auth headers returns 403 Forbidden."""
    app = create_app(tmp_path)
    client = TestClient(app)
    draft = create_draft(client)
    draft_id = draft["id"]

    # No X-PrivacyTrace-Local header
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=b"some bytes",
    )
    assert resp.status_code == 403


# ==============================================================================
# Multi-Package DEX Scanning & Evidence Split Attribution
# ==============================================================================


def test_scan_package_set_evidence_and_dex_namespacing(tmp_path: Path):
    """Multi-package scan namespaces DEX files, tags evidence with package_split, and aggregates."""
    base_apk = tmp_path / "base.apk"
    split_apk = tmp_path / "split_audio.apk"

    build_apk(
        base_apk,
        package_name="org.privacytrace.attribution",
        version_code="1",
        split=False,
        permission="android.permission.CAMERA",
        camera=True,
    )

    build_apk(
        split_apk,
        package_name="org.privacytrace.attribution",
        version_code="1",
        split="config.audio",
        split_name="config.audio",
        permission="android.permission.RECORD_AUDIO",
        kind="microphone",
    )

    rules = taxonomy()
    result = scan_package_set(
        base_path=base_apk,
        splits=[("config.audio", split_apk)],
        rules=rules,
    )

    # 1. Coverage
    assert result["coverage"]["completeness"] == "COMPLETE"
    assert "base:classes.dex" in result["coverage"]["scanned_dex"]
    assert "split:config.audio:classes.dex" in result["coverage"]["scanned_dex"]

    # 2. Permissions aggregation
    assert "android.permission.CAMERA" in result["permissions"]
    assert "android.permission.RECORD_AUDIO" in result["permissions"]

    # 3. Evidence split attribution
    base_ev = [e for e in result["evidence"] if e.get("package_split") == "base"]
    split_ev = [e for e in result["evidence"] if e.get("package_split") == "config.audio"]
    assert len(base_ev) >= 1, "Base evidence must be tagged package_split='base'"
    assert len(split_ev) >= 1, "Split evidence must be tagged package_split='config.audio'"

    # Check locator format
    for ev in base_ev:
        assert "split=base;" in ev["locator"]
    for ev in split_ev:
        assert "split=config.audio;" in ev["locator"]

    # Validate that Evidence model accepts package_split
    for ev in result["evidence"]:
        validated = Evidence.model_validate(ev)
        assert validated.package_split in ("base", "config.audio")


def test_evidence_model_rejects_policy_split_attribution():
    """Policy evidence cannot have package_split set (invariant enforcement)."""
    with pytest.raises(ValueError, match="Policy evidence must not reference a package split"):
        Evidence(
            id="ev-policy-1",
            kind="POLICY_SENTENCE",
            status="DECLARED",
            source="policy.html",
            locator="sentence=1",
            excerpt="some policy excerpt",
            document_id="doc-1",
            start_offset=0,
            end_offset=20,
            package_split="base",  # Invalid on policy evidence!
        )


def test_backward_compatibility_single_apk_scan(tmp_path: Path):
    """Standalone single APK scan maintains backward-compatible structure and attributes."""
    single_apk = tmp_path / "single.apk"

    build_apk(
        single_apk,
        package_name="org.privacytrace.standalone",
        version_code="7",
        split=False,
        permission="android.permission.CAMERA",
        camera=True,
    )

    rules = taxonomy()
    result = scan(single_apk, rules)

    assert result["coverage"]["completeness"] in ("COMPLETE", "PARTIAL")
    assert "classes.dex" in result["coverage"]["scanned_dex"]
    for ev in result["evidence"]:
        assert ev.get("package_split") is None
        assert "split=" not in ev["locator"]
