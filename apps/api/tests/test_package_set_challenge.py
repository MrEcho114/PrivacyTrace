"""Adversarial challenge test harness for PT-MOB-102 (Issue #70) Milestone 1.

Empirical stress tests:
1. Extreme boundary tests on cumulative and single file sizes (150 MiB vs 150 MiB + 1 byte)
2. Malicious and damaged ZIP archives (zip slip, backslashes, colons, symlinks, duplicates, CD)
3. Split integrity edge cases (empty split name, whitespace, versionCode 0 vs negative, casing)
4. Transactional intake rollback and zero orphan leaks on disk across every rejection mode
"""

import io
import zipfile
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import pytest
from apk_fixture_builder import apk_bytes, package_set_archive
from fastapi.testclient import TestClient

from privacytrace.apk_worker import scan_package_set
from privacytrace.main import create_app
from privacytrace.package_set import (
    MAX_FILE_SIZE,
    MAX_PACKAGE_SET_SIZE,
    PackageFile,
    PackagePart,
    PackageSetIntegrityError,
    inspect_apk_bytes,
    parse_package_input,
    validate_package_set,
)

HEADERS = {"X-PrivacyTrace-Local": "1"}
pytestmark = pytest.mark.usefixtures("synthetic_package_metadata")


def create_draft(client: TestClient) -> dict:
    resp = client.post(
        "/api/v1/web/drafts",
        headers=HEADERS,
        json={
            "name": "Challenge Test Draft",
            "sources": [
                {
                    "id": "src-challenge",
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
# Group 1: Extreme Boundary Tests on Cumulative and Single Size
# ==============================================================================


class TestCumulativeAndSingleSizeBoundaries:
    def test_cumulative_size_exact_150_mib_passes(self):
        """Cumulative size of exactly 150 MiB (157,286,400 bytes) passes validation."""
        half = 75 * 1024 * 1024
        base = PackageFile(
            file_name="base.apk",
            part=PackagePart.BASE,
            sha256="a" * 64,
            size_bytes=half,
            package_name="org.privacytrace.boundary",
            version_code=1,
        )
        split = PackageFile(
            file_name="split.apk",
            part=PackagePart.SPLIT,
            split_name="config.en",
            sha256="b" * 64,
            size_bytes=half,
            package_name="org.privacytrace.boundary",
            version_code=1,
        )
        pkg_set = validate_package_set([base, split])
        assert pkg_set.total_size_bytes == 150 * 1024 * 1024

    def test_cumulative_size_150_mib_plus_one_byte_fails(self):
        """Cumulative size of 150 MiB + 1 byte fails with PACKAGE_SET_TOO_LARGE (413)."""
        half = 75 * 1024 * 1024
        base = PackageFile(
            file_name="base.apk",
            part=PackagePart.BASE,
            sha256="a" * 64,
            size_bytes=half,
            package_name="org.privacytrace.boundary",
            version_code=1,
        )
        split = PackageFile(
            file_name="split.apk",
            part=PackagePart.SPLIT,
            split_name="config.en",
            sha256="b" * 64,
            size_bytes=half + 1,
            package_name="org.privacytrace.boundary",
            version_code=1,
        )
        with pytest.raises(PackageSetIntegrityError) as exc_info:
            validate_package_set([base, split])
        assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE"
        assert exc_info.value.http_status == 413

    def test_single_file_size_exact_150_mib_passes(self):
        """Single file of exactly 150 MiB passes validation."""
        base = PackageFile(
            file_name="base.apk",
            part=PackagePart.BASE,
            sha256="a" * 64,
            size_bytes=MAX_FILE_SIZE,
            package_name="org.privacytrace.boundary",
            version_code=1,
        )
        pkg_set = validate_package_set([base])
        assert pkg_set.total_size_bytes == MAX_FILE_SIZE

    def test_single_file_size_150_mib_plus_one_byte_fails(self):
        """Single file of 150 MiB + 1 byte fails with UPLOAD_TOO_LARGE (413)."""
        base = PackageFile(
            file_name="base.apk",
            part=PackagePart.BASE,
            sha256="a" * 64,
            size_bytes=MAX_FILE_SIZE + 1,
            package_name="org.privacytrace.boundary",
            version_code=1,
        )
        with pytest.raises(PackageSetIntegrityError) as exc_info:
            validate_package_set([base])
        assert exc_info.value.code == "UPLOAD_TOO_LARGE"
        assert exc_info.value.http_status == 413

    def test_parse_package_input_raw_size_boundary(self):
        """parse_package_input rejects raw input exceeding 150 MiB with 413."""
        with pytest.raises(PackageSetIntegrityError) as exc_info:
            parse_package_input(b"x" * (MAX_PACKAGE_SET_SIZE + 1))
        assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE"
        assert exc_info.value.http_status == 413

    def test_http_content_length_header_boundary(self, tmp_path: Path):
        """Content-Length header of 150 MiB + 1 byte is rejected with 413 before streaming."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        oversized_headers = dict(HEADERS)
        oversized_headers["content-length"] = str(MAX_FILE_SIZE + 1)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=oversized_headers,
            content=b"small_body",
        )
        assert resp.status_code == 413
        assert "UPLOAD_TOO_LARGE" in resp.text


# ==============================================================================
# Group 2: Malicious and Damaged ZIP Archives
# ==============================================================================


class TestMaliciousAndDamagedZipArchives:
    def test_zip_slip_relative_parent_directory(self, tmp_path: Path):
        """Archive with '../../evil.apk' is rejected with 400 and writes nothing outside."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
            zf.writestr("../../evil.apk", b"malicious apk payload")

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=buf.getvalue(),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text
        # Assert no evil.apk was created in parent directories
        assert not (tmp_path / "evil.apk").exists()
        assert not (tmp_path / "web" / "evil.apk").exists()

    def test_zip_slip_nested_parent_traversal(self, tmp_path: Path):
        """Archive with 'sub/dir/../../../../evil.apk' is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
            zf.writestr("sub/dir/../../../../evil.apk", b"malicious payload")

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=buf.getvalue(),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_zip_slip_absolute_path(self, tmp_path: Path):
        """Archive with absolute entry '/etc/evil.apk' is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
            info = ZipInfo("/evil.apk")
            zf.writestr(info, b"malicious payload")

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=buf.getvalue(),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_zip_slip_colon_path(self, tmp_path: Path):
        """Archive with Windows stream 'C:evil.apk' is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
            info = ZipInfo("C:evil.apk")
            zf.writestr(info, b"malicious payload")

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=buf.getvalue(),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_zip_symlink_entry(self, tmp_path: Path):
        """Archive containing a symlink entry is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
            info = ZipInfo("symlink.apk")
            # Set UNIX symlink attribute (0o120777 << 16)
            info.external_attr = 0o120777 << 16
            zf.writestr(info, b"/etc/passwd")

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=buf.getvalue(),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_duplicate_zip_entries(self, tmp_path: Path):
        """Archive with duplicate entry names is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.dup.entry", version_code=1, split=False)
        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
            zf.writestr("base.apk", base)
            zf.writestr("base.apk", base)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=buf.getvalue(),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_corrupted_central_directory(self, tmp_path: Path):
        """Archive with corrupted central directory header is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.corrupt.cd", version_code=1, split=False)
        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("base.apk", base)
        deflated_archive = bytearray(buf.getvalue())
        eocd_idx = deflated_archive.rfind(b"PK\x05\x06")
        assert eocd_idx != -1
        deflated_archive[eocd_idx : eocd_idx + 4] = b"XXXX"

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=bytes(deflated_archive),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_corrupted_central_directory_unhandled_server_error_defect(self, tmp_path: Path):
        """Damaged CD (PK\\x01\\x02) with intact EOCD is rejected with HTTP 400 CORRUPTED_FILE.

        Leaves zero orphan files.
        """
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]
        draft_dir = tmp_path / "web" / draft_id

        base = apk_bytes(package_name="org.corrupt.cd", version_code=1, split=False)
        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("base.apk", base)
        corrupted_cd_archive = bytearray(buf.getvalue())
        cd_idx = corrupted_cd_archive.rfind(b"PK\x01\x02")
        assert cd_idx != -1
        corrupted_cd_archive[cd_idx : cd_idx + 4] = b"XXXX"

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=bytes(corrupted_cd_archive),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

        # Verify zero orphan staging directories or pending files
        assert len(list(draft_dir.glob("packages.pending.*"))) == 0
        assert len(list(draft_dir.glob("upload.pending.*"))) == 0
        assert len(list(draft_dir.glob("*.tmp"))) == 0
        assert not (draft_dir / "packages").exists()
        assert not (draft_dir / "input.apk").exists()

        # Verify draft state is intact and uncorrupted
        fresh_draft = client.get(f"/api/v1/web/drafts/{draft_id}").json()
        assert fresh_draft["uploaded"] is False

    def test_empty_zip_archive_rejected(self, tmp_path: Path):
        """A valid 22-byte empty ZIP (0 entries) is rejected with EMPTY_PACKAGE_SET (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        buf = io.BytesIO()
        with ZipFile(buf, "w"):
            pass
        empty_zip = buf.getvalue()
        assert len(empty_zip) == 22  # Standard EOCD only

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=empty_zip,
        )
        assert resp.status_code == 400
        assert "EMPTY_PACKAGE_SET" in resp.text

    def test_zip_with_only_non_apk_files(self, tmp_path: Path):
        """Archive with non-APK files (txt, png, bin) is rejected with EMPTY_PACKAGE_SET (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        archive = package_set_archive(
            apks={
                "readme.txt": b"Instructions",
                "logo.png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 32,
                "script.sh": b"#!/bin/sh\necho hi\n",
            }
        )
        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "EMPTY_PACKAGE_SET" in resp.text

    def test_encrypted_zip_entry(self, tmp_path: Path):
        """Archive with encrypted entry (flag_bits & 1) is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        buf = io.BytesIO()
        with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
            info = ZipInfo("base.apk")
            info.flag_bits |= 1  # Mark encrypted
            zf.writestr(info, b"encrypted data")

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=buf.getvalue(),
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_nested_apk_internal_zip_slip(self, tmp_path: Path):
        """Archive where internal base.apk contains zip slip is rejected with CORRUPTED_FILE."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        # Craft malicious internal APK with zip slip
        malicious_apk_buf = io.BytesIO()
        with ZipFile(malicious_apk_buf, "w", compression=ZIP_STORED) as zf:
            zf.writestr("AndroidManifest.xml", b"broken")
            zf.writestr("../../evil_classes.dex", b"malicious code")

        archive = package_set_archive(apks={"base.apk": malicious_apk_buf.getvalue()})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text


# ==============================================================================
# Group 3: Split Integrity Edge Cases
# ==============================================================================


class TestSplitIntegrityEdgeCases:
    def test_split_manifest_empty_split_name(self, tmp_path: Path):
        """Split APK with empty split attribute is rejected with DUPLICATE_SPLIT_NAME (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.empty.split", version_code=1, split=False)
        bad_split = apk_bytes(
            package_name="org.empty.split",
            version_code=1,
            split=True,
            split_name="",  # Empty string split attribute
        )
        archive = package_set_archive(apks={"base.apk": base, "split.apk": bad_split})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "DUPLICATE_SPLIT_NAME" in resp.text

    def test_split_manifest_whitespace_split_name(self, tmp_path: Path):
        """Split APK with whitespace split attribute is rejected with DUPLICATE_SPLIT_NAME (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.ws.split", version_code=1, split=False)
        bad_split = apk_bytes(
            package_name="org.ws.split",
            version_code=1,
            split=True,
            split_name="   ",  # Whitespace only
        )
        archive = package_set_archive(apks={"base.apk": base, "split.apk": bad_split})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "DUPLICATE_SPLIT_NAME" in resp.text

    def test_split_claiming_to_be_base_rejected_as_multiple_bases(self, tmp_path: Path):
        """Second APK in archive that omits split attribute -> MULTIPLE_BASE_APKS (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.twobases", version_code=1, split=False)
        pseudo_split = apk_bytes(package_name="org.twobases", version_code=1, split=False)
        archive = package_set_archive(apks={"base.apk": base, "split_feat.apk": pseudo_split})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "MULTIPLE_BASE_APKS" in resp.text

    def test_version_code_boundary_zero_is_valid(self, tmp_path: Path):
        """versionCode=0 is valid on both base and split APKs and succeeds."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.vzero", version_code="0", split=False)
        split = apk_bytes(package_name="org.vzero", version_code="0", split="config.en")
        archive = package_set_archive(apks={"base.apk": base, "split.apk": split})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["uploaded"] is True
        assert updated["package_set"]["version_code"] == 0

    def test_version_code_boundary_max_signed_32bit_is_valid(self, tmp_path: Path):
        """versionCode=2147483647 (0x7FFFFFFF) is valid and succeeds."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        max_vc = 0x7FFFFFFF
        base = apk_bytes(package_name="org.vmax", version_code=str(max_vc), split=False)
        split = apk_bytes(package_name="org.vmax", version_code=str(max_vc), split="config.en")
        archive = package_set_archive(apks={"base.apk": base, "split.apk": split})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["uploaded"] is True
        assert updated["package_set"]["version_code"] == max_vc

    def test_version_code_negative_rejected(self, tmp_path: Path):
        """Negative versionCode is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.vneg", version_code="-1", split=False)
        archive = package_set_archive(apks={"base.apk": base})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_version_code_overflow_signed_32bit_rejected(self, tmp_path: Path):
        """versionCode exceeding 0x7FFFFFFF is rejected with CORRUPTED_FILE (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        overflow_vc = 0x80000000
        base = apk_bytes(package_name="org.voverflow", version_code=str(overflow_vc), split=False)
        archive = package_set_archive(apks={"base.apk": base})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "CORRUPTED_FILE" in resp.text

    def test_package_name_case_sensitivity_mismatch(self, tmp_path: Path):
        """Package name casing mismatch is rejected with SPLIT_PACKAGE_MISMATCH (400)."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        base = apk_bytes(package_name="org.privacytrace.casesensitive", version_code=1, split=False)
        split = apk_bytes(
            package_name="Org.PrivacyTrace.CaseSensitive", version_code=1, split="config.en"
        )
        archive = package_set_archive(apks={"base.apk": base, "split.apk": split})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "SPLIT_PACKAGE_MISMATCH" in resp.text

    def test_split_name_with_safe_special_chars_succeeds(self, tmp_path: Path):
        """Split name with hyphens, underscores, dots succeeds and attributes correctly."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]

        complex_split_name = "config.arm64-v8a_release.v2"
        base = apk_bytes(package_name="org.specialsplit", version_code=1, split=False, camera=True)
        split = apk_bytes(
            package_name="org.specialsplit",
            version_code=1,
            split=complex_split_name,
            provider="network",
        )
        archive = package_set_archive(apks={"base.apk": base, "split.apk": split})

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["package_set"]["splits"][0]["split_name"] == complex_split_name

        # Verify scan_package_set attributes correctly
        draft_dir = tmp_path / "web" / draft_id
        base_path = draft_dir / "packages" / "base.apk"
        split_path = draft_dir / "packages" / "split.apk"
        rules = {"version": "1.0", "permission_mappings": [], "api_mappings": []}
        scan_res = scan_package_set(base_path, [(complex_split_name, split_path)], rules)
        assert f"split:{complex_split_name}:classes.dex" in scan_res["dex_entries"]

    def test_split_named_base_causes_dex_namespace_collision(self, tmp_path: Path):
        """Split APK declaring split='base' is rejected (400 DUPLICATE_SPLIT_NAME).

        Namespaced defensively to prevent collisions.
        """
        base = apk_bytes(
            package_name="org.basecollision", version_code=1, split=False, camera=True
        )
        split_base = apk_bytes(
            package_name="org.basecollision", version_code=1, split="base", provider="network"
        )
        base_path = tmp_path / "base.apk"
        split_path = tmp_path / "split_base.apk"
        base_path.write_bytes(base)
        split_path.write_bytes(split_base)

        with pytest.raises(PackageSetIntegrityError) as exc_inspect:
            inspect_apk_bytes(split_base, "split_base.apk")
        assert exc_inspect.value.code == "DUPLICATE_SPLIT_NAME"
        assert exc_inspect.value.http_status == 400
        assert "Split APK cannot declare reserved split name 'base'" in exc_inspect.value.detail

        # Case-insensitivity check: "BASE", "Base"
        split_upper = apk_bytes(
            package_name="org.basecollision", version_code=1, split="BASE"
        )
        with pytest.raises(PackageSetIntegrityError) as exc_upper:
            inspect_apk_bytes(split_upper, "split_upper.apk")
        assert exc_upper.value.code == "DUPLICATE_SPLIT_NAME"
        assert exc_upper.value.http_status == 400

        # PackageFile validator rejection check
        with pytest.raises(ValueError):
            PackageFile(
                file_name="split.apk",
                part=PackagePart.SPLIT,
                split_name="base",
                sha256="b" * 64,
                size_bytes=500,
                package_name="org.basecollision",
                version_code=1,
            )

        # Layer 2 defense-in-depth: direct scan_package_set call avoids duplicate DEX entries
        rules = {"version": "1.0", "permission_mappings": [], "api_mappings": []}
        scan_res = scan_package_set(base_path, [("base", split_path)], rules)
        dex_entries = scan_res["dex_entries"]
        assert dex_entries == ["base:classes.dex", "split:base:classes.dex"], (
            f"Expected namespaced 'split:base:classes.dex', got: {dex_entries}"
        )

        # HTTP upload rejection check
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        archive = package_set_archive(apks={"base.apk": base, "split.apk": split_base})
        resp = client.post(
            f"/api/v1/web/drafts/{draft['id']}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "DUPLICATE_SPLIT_NAME" in resp.text

    @pytest.mark.parametrize(
        "invalid_split_name",
        [
            "config;injected=true",
            "feature:chat",
            "config arm",
            "config/sub",
            "config\\sub",
            "config=value",
            "split@feature",
            "split#1",
            "split$bad",
        ],
    )
    def test_split_name_with_invalid_characters_rejected(
        self, tmp_path: Path, invalid_split_name: str
    ):
        """Split names with semicolons, colons, spaces, slashes etc. are rejected (400)."""
        base = apk_bytes(package_name="org.invalidsplit", version_code=1, split=False)
        bad_split = apk_bytes(
            package_name="org.invalidsplit",
            version_code=1,
            split=invalid_split_name,
        )
        with pytest.raises(PackageSetIntegrityError) as exc_info:
            inspect_apk_bytes(bad_split, "bad_split.apk")
        assert exc_info.value.code == "DUPLICATE_SPLIT_NAME"
        assert exc_info.value.http_status == 400

        # HTTP upload test
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        archive = package_set_archive(apks={"base.apk": base, "bad_split.apk": bad_split})
        resp = client.post(
            f"/api/v1/web/drafts/{draft['id']}/package-set",
            headers=HEADERS,
            content=archive,
        )
        assert resp.status_code == 400
        assert "DUPLICATE_SPLIT_NAME" in resp.text


# ==============================================================================
# Group 4: Transactional Intake Rollback & Zero Orphan Leaks across EVERY Mode
# ==============================================================================


class TestTransactionalIntakeRollbackAndZeroLeaks:
    @pytest.mark.parametrize(
        "rejection_name,bad_payload_factory,expected_status,expected_code",
        [
            ("zero_bytes", lambda: b"", 400, "EMPTY_PACKAGE_SET"),
            ("empty_zip_archive", lambda: package_set_archive(), 400, "EMPTY_PACKAGE_SET"),
            (
                "non_apk_files_only",
                lambda: package_set_archive(apks={"README.txt": b"no apks"}),
                400,
                "EMPTY_PACKAGE_SET",
            ),
            ("corrupt_raw_bytes", lambda: b"NON_ZIP_CORRUPT_BYTES", 400, "CORRUPTED_FILE"),
            (
                "corrupted_central_directory",
                lambda: b"PK\x03\x04" + b"\x00" * 30 + b"TRUNCATED_NO_EOCD",
                400,
                "CORRUPTED_FILE",
            ),
            (
                "zip_slip_attempt",
                lambda: _make_zip_slip_archive(),
                400,
                "CORRUPTED_FILE",
            ),
            (
                "duplicate_zip_entry",
                lambda: _make_duplicate_entry_archive(),
                400,
                "CORRUPTED_FILE",
            ),
            (
                "missing_base_apk",
                lambda: package_set_archive(
                    apks={
                        "split1.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split="s1"
                        )
                    }
                ),
                400,
                "MISSING_BASE_APK",
            ),
            (
                "multiple_base_apks",
                lambda: package_set_archive(
                    apks={
                        "base1.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split=False
                        ),
                        "base2.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split=False
                        ),
                    }
                ),
                400,
                "MULTIPLE_BASE_APKS",
            ),
            (
                "split_package_mismatch",
                lambda: package_set_archive(
                    apks={
                        "base.apk": apk_bytes(
                            package_name="org.rb.correct", version_code=1, split=False
                        ),
                        "split.apk": apk_bytes(
                            package_name="org.rb.wrong", version_code=1, split="s1"
                        ),
                    }
                ),
                400,
                "SPLIT_PACKAGE_MISMATCH",
            ),
            (
                "split_version_code_mismatch",
                lambda: package_set_archive(
                    apks={
                        "base.apk": apk_bytes(
                            package_name="org.rb.test", version_code=10, split=False
                        ),
                        "split.apk": apk_bytes(
                            package_name="org.rb.test", version_code=11, split="s1"
                        ),
                    }
                ),
                400,
                "VERSION_CODE_MISMATCH",
            ),
            (
                "duplicate_split_name",
                lambda: package_set_archive(
                    apks={
                        "base.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split=False
                        ),
                        "split1.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split="dup_split"
                        ),
                        "split2.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split="dup_split"
                        ),
                    }
                ),
                400,
                "DUPLICATE_SPLIT_NAME",
            ),
            (
                "corrupt_manifest_in_split",
                lambda: _make_split_with_corrupt_manifest(),
                400,
                "CORRUPTED_FILE",
            ),
            (
                "split_manifest_empty_split",
                lambda: package_set_archive(
                    apks={
                        "base.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split=False
                        ),
                        "split.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split=True, split_name=""
                        ),
                    }
                ),
                400,
                "DUPLICATE_SPLIT_NAME",
            ),
            (
                "corrupted_central_directory_intact_eocd",
                lambda: _make_corrupted_cd_archive(),
                400,
                "CORRUPTED_FILE",
            ),
            (
                "split_named_base",
                lambda: package_set_archive(
                    apks={
                        "base.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split=False
                        ),
                        "split.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split="base"
                        ),
                    }
                ),
                400,
                "DUPLICATE_SPLIT_NAME",
            ),
            (
                "split_semicolon_injection",
                lambda: package_set_archive(
                    apks={
                        "base.apk": apk_bytes(
                            package_name="org.rb.test", version_code=1, split=False
                        ),
                        "split.apk": apk_bytes(
                            package_name="org.rb.test",
                            version_code=1,
                            split="config;injected=1",
                        ),
                    }
                ),
                400,
                "DUPLICATE_SPLIT_NAME",
            ),
        ],
    )
    def test_rejection_mode_rolls_back_and_leaves_zero_leaks(
        self,
        tmp_path: Path,
        rejection_name: str,
        bad_payload_factory,
        expected_status: int,
        expected_code: str,
    ):
        """Stress-test rollback across failures: verify HTTP 4xx, zero leaks, clean retry."""
        app = create_app(tmp_path)
        client = TestClient(app)
        draft = create_draft(client)
        draft_id = draft["id"]
        draft_dir = tmp_path / "web" / draft_id

        bad_payload = bad_payload_factory()

        # 1. Execute failing upload
        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=bad_payload,
        )
        assert resp.status_code == expected_status, (
            f"Expected {expected_status} for {rejection_name}, got {resp.status_code}: {resp.text}"
        )
        assert expected_code in resp.text, (
            f"Expected {expected_code} in response for {rejection_name}, got: {resp.text}"
        )

        # 2. Assert zero staging directories leaked
        pending_dirs = list(draft_dir.glob("packages.pending.*"))
        assert len(pending_dirs) == 0, f"[{rejection_name}] Leaked staging dirs: {pending_dirs}"

        # 3. Assert zero pending files leaked
        pending_files = list(draft_dir.glob("upload.pending.*"))
        assert len(pending_files) == 0, f"[{rejection_name}] Leaked pending files: {pending_files}"

        # 4. Assert zero temporary files leaked
        tmp_files = list(draft_dir.glob("*.tmp"))
        assert len(tmp_files) == 0, f"[{rejection_name}] Leaked temporary files: {tmp_files}"

        # 5. Assert target directories and files do not exist
        assert not (draft_dir / "packages").exists(), (
            f"[{rejection_name}] Target packages/ dir should not exist on failure"
        )
        assert not (draft_dir / "input.apk").exists(), (
            f"[{rejection_name}] Target input.apk should not exist on failure"
        )

        # 6. Assert draft state remained unchanged
        fresh_draft = client.get(f"/api/v1/web/drafts/{draft_id}").json()
        assert fresh_draft["uploaded"] is False
        assert fresh_draft.get("package_set") is None

        # 7. Crucial: Assert draft is NOT corrupted and subsequent valid upload succeeds cleanly
        valid_base = apk_bytes(package_name="org.rb.recovery", version_code=1, split=False)
        valid_split = apk_bytes(
            package_name="org.rb.recovery", version_code=1, split="config.en"
        )
        valid_archive = package_set_archive(
            apks={"base.apk": valid_base, "split.apk": valid_split}
        )

        retry_resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=valid_archive,
        )
        assert retry_resp.status_code == 200, (
            f"[{rejection_name}] Subsequent valid upload failed: {retry_resp.text}"
        )
        retry_data = retry_resp.json()
        assert retry_data["uploaded"] is True
        assert retry_data["package_set"]["package_name"] == "org.rb.recovery"
        assert (draft_dir / "packages" / "base.apk").is_file()
        assert (draft_dir / "packages" / "split.apk").is_file()
        assert (draft_dir / "input.apk").is_file()


# ==============================================================================
# Helpers for payload construction
# ==============================================================================


def _make_zip_slip_archive() -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
        zf.writestr("../../evil.apk", b"evil content")
    return buf.getvalue()


def _make_duplicate_entry_archive() -> bytes:
    base = apk_bytes(package_name="org.rb.test", version_code=1, split=False)
    buf = io.BytesIO()
    with ZipFile(buf, "w", compression=ZIP_STORED) as zf:
        zf.writestr("base.apk", base)
        zf.writestr("base.apk", base)
    return buf.getvalue()


def _make_split_with_corrupt_manifest() -> bytes:
    base = apk_bytes(package_name="org.rb.test", version_code=1, split=False)
    bad_split = bytearray(apk_bytes(package_name="org.rb.test", version_code=1, split="s1"))
    idx = bad_split.find(b"AndroidManifest.xml")
    if idx != -1:
        bad_split[idx : idx + 10] = b"DamagedXml"
    return package_set_archive(apks={"base.apk": base, "split.apk": bytes(bad_split)})


def _make_corrupted_cd_archive() -> bytes:
    base = apk_bytes(package_name="org.rb.test", version_code=1, split=False)
    buf = io.BytesIO()
    with ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("base.apk", base)
    corrupted_cd_archive = bytearray(buf.getvalue())
    cd_idx = corrupted_cd_archive.rfind(b"PK\x01\x02")
    assert cd_idx != -1
    corrupted_cd_archive[cd_idx : cd_idx + 4] = b"XXXX"
    return bytes(corrupted_cd_archive)
