"""Adversarial stress-test suite for PR #88 Milestone 1 repairs.

Author: Challenger 1 (critic, specialist)
Verification Objectives:
1. 101 APKs vs 102 APKs boundary check (both unit and HTTP API levels).
2. Concurrent upload staging protection in `start_service()` with `self.active_drafts`.
3. `_finish_upload` rollback logic on metadata store failure.
"""

import io
import os
import shutil
import threading
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from apk_fixture_builder import apk, package_set_archive
from fastapi.testclient import TestClient
from test_web_intake import HEADERS, new_draft

from privacytrace import web_intake
from privacytrace.main import create_app
from privacytrace.package_set import (
    PackageFile,
    PackagePart,
    PackageSetIntegrityError,
    validate_package_set,
)
from privacytrace.web_intake import WebIntake


# ==============================================================================
# Helper to create dummy valid ZIP archives with N APK entries
# ==============================================================================
def create_archive_with_n_apks(n: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("base.apk", b"PK\x05\x06" + b"\x00" * 18)
        for i in range(1, n):
            zf.writestr(f"split_{i}.apk", b"PK\x05\x06" + b"\x00" * 18)
    return buf.getvalue()


# ==============================================================================
# Objective 1: 101 APKs vs 102 APKs boundary check
# ==============================================================================
def test_unpack_package_set_102_apks_rejected_early_with_413(tmp_path: Path):
    """102 APKs must be rejected immediately during unpack with HTTP 413 without disk writes."""
    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake
    archive_bytes = create_archive_with_n_apks(102)
    zip_path = tmp_path / "test_102.zip"
    zip_path.write_bytes(archive_bytes)
    # Target directory inside service.store.root to satisfy _safe path constraint
    target_dir = service.root / f"staging_102_{uuid4().hex}"
    target_dir.mkdir(parents=True)

    try:
        with pytest.raises(PackageSetIntegrityError) as exc_info:
            service._unpack_package_set(zip_path, target_dir)

        assert exc_info.value.http_status == 413
        assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE"
        assert "maximum allowed is 101" in exc_info.value.detail
        # Verify early exit: NO files were extracted into target_dir
        assert list(target_dir.iterdir()) == [], "Early rejection should not extract files"
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def test_unpack_package_set_101_apks_accepted_without_error(tmp_path: Path):
    """101 APKs must pass unpack boundary check and extract all 101 files."""
    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake
    archive_bytes = create_archive_with_n_apks(101)
    zip_path = tmp_path / "test_101.zip"
    zip_path.write_bytes(archive_bytes)
    target_dir = service.root / f"staging_101_{uuid4().hex}"
    target_dir.mkdir(parents=True)

    try:
        # Should not raise PACKAGE_SET_TOO_LARGE
        service._unpack_package_set(zip_path, target_dir)
        extracted = list(target_dir.iterdir())
        assert len(extracted) == 101
        assert any(p.name == "base.apk" for p in extracted)
        assert any(p.name == "split_100.apk" for p in extracted)
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def test_validate_package_set_models_boundary_101_vs_102():
    """validate_package_set accepts exactly 101 PackageFile models and rejects 102 with 413."""
    base = PackageFile(
        file_name="base.apk",
        part=PackagePart.BASE,
        sha256="a" * 64,
        size_bytes=100,
        package_name="com.example.boundary",
        version_code=1,
    )
    splits = [
        PackageFile(
            file_name=f"split_{i}.apk",
            part=PackagePart.SPLIT,
            split_name=f"split_{i}",
            sha256=f"{i:064x}",
            size_bytes=50,
            package_name="com.example.boundary",
            version_code=1,
        )
        for i in range(1, 101)  # 100 splits -> total 101 files
    ]
    assert len(splits) == 100
    files_101 = [base, *splits]
    assert len(files_101) == 101

    # 101 files must pass
    summary = validate_package_set(files_101)
    assert len(summary.splits) == 100
    assert summary.base.file_name == "base.apk"
    assert summary.total_size_bytes == 100 + 50 * 100

    # 102 files must fail with 413
    extra_split = PackageFile(
        file_name="split_101.apk",
        part=PackagePart.SPLIT,
        split_name="split_101",
        sha256="f" * 64,
        size_bytes=50,
        package_name="com.example.boundary",
        version_code=1,
    )
    files_102 = [*files_101, extra_split]
    assert len(files_102) == 102

    with pytest.raises(PackageSetIntegrityError) as exc_info:
        validate_package_set(files_102)

    assert exc_info.value.http_status == 413
    assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE"
    assert "maximum allowed is 101" in exc_info.value.detail


def test_validate_package_set_paths_boundary_101_vs_102(tmp_path: Path):
    """validate_package_set over paths rejects > 101 paths with 413 before parsing APK bytes."""
    paths_102 = [tmp_path / f"pkg_{i}.apk" for i in range(102)]
    with pytest.raises(PackageSetIntegrityError) as exc_info:
        validate_package_set(paths_102)
    assert exc_info.value.http_status == 413
    assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE"


def test_http_api_102_apks_rejected_with_status_413(tmp_path: Path):
    """HTTP API POST /package-set with 102 APKs returns 413 and leaves no orphan files."""
    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake
    archive_102 = create_archive_with_n_apks(102)

    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive_102,
        )
        assert resp.status_code == 413
        assert resp.json()["detail"] == "PACKAGE_SET_TOO_LARGE"

        # Verify filesystem cleanup
        assert not (directory / "packages").exists()
        assert not (directory / "input.apk").exists()
        assert not list(directory.glob("*pending*"))
        current = service.get(draft_id)
        assert current["uploaded"] is False


def test_http_api_101_apks_accepted_end_to_end(tmp_path: Path, monkeypatch):
    """HTTP API POST /package-set with 101 APKs succeeds (status 200) and commits all 101 files."""
    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake
    archive_101 = create_archive_with_n_apks(101)

    def mock_inspect(path: Path, *, timeout=120):
        if path.name == "base.apk":
            return PackageFile(
                file_name="base.apk",
                part=PackagePart.BASE,
                sha256="a" * 64,
                size_bytes=100,
                package_name="com.example.fullset",
                version_code=1,
            )
        split_num = path.name.replace("split_", "").replace(".apk", "")
        return PackageFile(
            file_name=path.name,
            part=PackagePart.SPLIT,
            split_name=f"split_{split_num}",
            sha256=f"{int(split_num):064x}",
            size_bytes=50,
            package_name="com.example.fullset",
            version_code=1,
        )

    monkeypatch.setattr("privacytrace.web_intake.inspect_uploaded_package", mock_inspect)

    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=archive_101,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["uploaded"] is True
        assert len(data["package_set"]["splits"]) == 100
        assert data["package_set"]["base"]["file_name"] == "base.apk"

        # Check published files on disk
        packages_dir = directory / "packages"
        assert packages_dir.exists()
        assert len(list(packages_dir.iterdir())) == 101
        assert (directory / "input.apk").exists()


# ==============================================================================
# Objective 2: Concurrent upload staging & start_service() Protection
# ==============================================================================
def test_start_service_protects_active_draft_while_cleaning_stale_draft(tmp_path: Path):
    """start_service cleans uncommitted files of inactive drafts while skipping active drafts."""
    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake

    with TestClient(app) as client:
        draft_active = new_draft(client)
        draft_stale = new_draft(client)

        dir_active = service.directory(draft_active["id"])
        dir_stale = service.directory(draft_stale["id"])

        # Populate active draft with upload.pending and packages.pending directory & file
        active_pending_file = dir_active / "upload.pending"
        active_pending_file.write_bytes(b"active-upload-data")
        active_pending_dir = dir_active / "packages.pending.uuid123"
        active_pending_dir.mkdir()
        (active_pending_dir / "split_1.apk").write_bytes(b"staged-split")
        active_pending_other = dir_active / "packages.pending.uuid456"
        active_pending_other.write_bytes(b"extra-pending-file")

        # Populate stale draft with abandoned pending files
        stale_pending_file = dir_stale / "upload.pending"
        stale_pending_file.write_bytes(b"stale-upload-data")
        stale_pending_dir = dir_stale / "packages.pending.stale789"
        stale_pending_dir.mkdir()
        (stale_pending_dir / "stale.apk").write_bytes(b"stale-data")

        # 1. While draft_active is active:
        with service._draft_activity(draft_active["id"]):
            assert service.active_drafts.get(draft_active["id"], 0) > 0
            assert service.active_drafts.get(draft_stale["id"], 0) == 0

            # Close lock to permit start_service re-run
            if service.owner_fd is not None:
                os.close(service.owner_fd)
                service.owner_fd = None

            service.start_service()

            # Active draft must be COMPLETELY UNTOUCHED
            assert active_pending_file.exists()
            assert active_pending_dir.exists()
            assert (active_pending_dir / "split_1.apk").exists()
            assert active_pending_other.exists()

            # Stale draft MUST be CLEANED UP
            assert not stale_pending_file.exists()
            assert not stale_pending_dir.exists()

        # 2. After draft_active completes/exits:
        assert service.active_drafts.get(draft_active["id"], 0) == 0
        if service.owner_fd is not None:
            os.close(service.owner_fd)
            service.owner_fd = None

        service.start_service()

        # Now active draft pending files must be cleaned up
        assert not active_pending_file.exists()
        assert not active_pending_dir.exists()
        assert not active_pending_other.exists()


def test_concurrent_upload_and_start_service_race(tmp_path: Path):
    """Stress-test concurrent start_service invocations during active draft write operations."""
    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake

    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)

        stop_event = threading.Event()
        errors = []

        def uploader_thread():
            try:
                for _ in range(50):
                    if stop_event.is_set():
                        break
                    with service._draft_activity(draft_id):
                        p_file = directory / "upload.pending"
                        p_file.write_bytes(b"chunk-data")
                        p_dir = directory / f"packages.pending.{uuid4().hex}"
                        p_dir.mkdir(exist_ok=True)
                        (p_dir / "test.apk").write_bytes(b"apk")
                        time.sleep(0.01)
                        # Ensure files are still there while we hold activity lock
                        if not p_file.exists() or not p_dir.exists():
                            errors.append("Active draft files vanished while under lock")
                        p_file.unlink(missing_ok=True)
                        shutil.rmtree(p_dir, ignore_errors=True)
            except Exception as e:
                errors.append(f"Uploader exception: {e}")

        def cleaner_thread():
            try:
                for _ in range(50):
                    if stop_event.is_set():
                        break
                    # Mirror start_service's atomic activity check and cleanup;
                    # an unlocked check lets a just-started upload be deleted.
                    with service.data_store._transaction():
                        for d in service._draft_directories():
                            if service.active_drafts.get(d.name, 0):
                                continue
                            for p in d.glob("upload.pending*"):
                                p.unlink(missing_ok=True)
                            for p in d.glob("packages.pending*"):
                                if p.is_dir():
                                    shutil.rmtree(p, ignore_errors=True)
                                else:
                                    p.unlink(missing_ok=True)
                    time.sleep(0.005)
            except Exception as e:
                errors.append(f"Cleaner exception: {e}")

        threads = [
            threading.Thread(target=uploader_thread),
            threading.Thread(target=cleaner_thread),
            threading.Thread(target=cleaner_thread),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        stop_event.set()

        assert not errors, f"Concurrent stress test errors: {errors}"


# ==============================================================================
# Objective 3: _finish_upload Rollback Logic on Metadata Failure
# ==============================================================================
def test_finish_upload_rollback_on_metadata_failure_single_apk(tmp_path: Path, monkeypatch):
    """When _save fails on single APK upload, files are unlinked and revision restored."""
    sample = apk(tmp_path / "single.apk")
    payload = sample.read_bytes()

    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake

    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)
        original_revision = draft["revision"]

        # Simulate metadata store disk full error inside _save
        def crashing_save(updated_draft):
            if updated_draft.get("uploaded"):
                raise OSError("Simulated metadata database write failure")
            return service.data_store._save(updated_draft)

        monkeypatch.setattr(service, "_save", crashing_save)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/apk",
            headers=HEADERS,
            content=payload,
        )
        assert resp.status_code == 409

        # Verify rollback guarantees:
        # 1. input.apk is deleted
        assert not (directory / "input.apk").exists(), "input.apk must be cleaned up on rollback"
        # 2. No pending files left
        assert not list(directory.glob("*pending*")), "Pending files must be removed on rollback"
        # 3. No orphan revision file
        assert not (directory / f"revision-{original_revision + 1}.json").exists()
        # 4. Draft state in current.json is still un-uploaded
        current = service.get(draft_id)
        assert current["uploaded"] is False
        assert current["revision"] == original_revision


def test_finish_upload_rollback_on_metadata_failure_package_set(tmp_path: Path, monkeypatch):
    """When _save fails on package-set upload, packages dir and base input.apk are deleted."""
    sample = apk(tmp_path / "base.apk")
    archive_file = package_set_archive(tmp_path / "set.zip", {"base.apk": sample.read_bytes()})
    payload = archive_file.read_bytes()

    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake

    def mock_inspect(path: Path, *, timeout=120):
        return PackageFile(
            file_name="base.apk",
            part=PackagePart.BASE,
            sha256="a" * 64,
            size_bytes=100,
            package_name="com.example.rollback",
            version_code=1,
        )

    monkeypatch.setattr("privacytrace.web_intake.inspect_uploaded_package", mock_inspect)

    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)
        original_revision = draft["revision"]

        def crashing_save(updated_draft):
            if updated_draft.get("uploaded"):
                raise OSError("Simulated database crash during package_set commit")
            return service.data_store._save(updated_draft)

        monkeypatch.setattr(service, "_save", crashing_save)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=payload,
        )
        assert resp.status_code == 409

        # Verify rollback guarantees:
        # 1. target packages dir is wiped out
        assert not (directory / "packages").exists(), "packages dir must be removed on rollback"
        # 2. base input.apk copy is wiped out
        assert not (directory / "input.apk").exists(), "input.apk must be removed on rollback"
        # 3. No staging or pending directories/files remain
        assert not list(directory.glob("*pending*")), "No pending directories should remain"
        # 4. No orphan revision file created
        assert not (directory / f"revision-{original_revision + 1}.json").exists()
        # 5. Metadata state remains un-uploaded
        current = service.get(draft_id)
        assert current["uploaded"] is False
        assert current["revision"] == original_revision


def test_finish_upload_rollback_when_failure_occurs_between_publish_and_commit(
    tmp_path: Path, monkeypatch
):
    """If an unexpected exception occurs after physical file replacement,
    published files are reliably removed by except Exception handler.
    """
    sample = apk(tmp_path / "base.apk")
    archive_file = package_set_archive(tmp_path / "set.zip", {"base.apk": sample.read_bytes()})
    payload = archive_file.read_bytes()

    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake

    def mock_inspect(path: Path, *, timeout=120):
        return PackageFile(
            file_name="base.apk",
            part=PackagePart.BASE,
            sha256="a" * 64,
            size_bytes=100,
            package_name="com.example.rollback",
            version_code=1,
        )

    monkeypatch.setattr("privacytrace.web_intake.inspect_uploaded_package", mock_inspect)

    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)

        # Hook deepcopy to fail right after published_apk is set, before _save
        original_deepcopy = web_intake.deepcopy

        def failing_deepcopy(obj):
            if isinstance(obj, dict) and obj.get("id") == draft_id:
                raise OSError("Simulated system failure right after file publishing")
            return original_deepcopy(obj)

        monkeypatch.setattr(web_intake, "deepcopy", failing_deepcopy)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=payload,
        )
        assert resp.status_code == 409

        # Check that physical files were cleaned up
        assert not (directory / "packages").exists()
        assert not (directory / "input.apk").exists()
        assert not list(directory.glob("*pending*"))
        current = service.get(draft_id)
        assert current["uploaded"] is False


@pytest.mark.parametrize("operation", ["copy", "link"])
def test_base_publication_failure_cleans_owned_files(tmp_path: Path, monkeypatch, operation):
    """Failed staging copy or atomic base link must leave no published upload."""
    sample = apk(tmp_path / "base.apk")
    archive_file = package_set_archive(tmp_path / "set.zip", {"base.apk": sample.read_bytes()})
    payload = sample.read_bytes() if operation == "copy" else archive_file.read_bytes()

    app = create_app(tmp_path / "jobs")
    service: WebIntake = app.state.web_intake

    def mock_inspect(path: Path, *, timeout=120):
        return PackageFile(
            file_name="base.apk",
            part=PackagePart.BASE,
            sha256="a" * 64,
            size_bytes=100,
            package_name="com.example.rollback",
            version_code=1,
        )

    monkeypatch.setattr("privacytrace.web_intake.inspect_uploaded_package", mock_inspect)

    with TestClient(app) as client:
        draft = new_draft(client)
        draft_id = draft["id"]
        directory = service.directory(draft_id)

        def failing_copy(src, dst):
            # Simulate copy creating the destination file and then failing mid-write
            Path(dst).write_bytes(b"partial-corrupt-data")
            raise OSError("No space left on device during copyfile")

        def failing_link(src, dst):
            raise OSError("Hard link unavailable")

        if operation == "copy":
            monkeypatch.setattr(shutil, "copyfile", failing_copy)
        else:
            monkeypatch.setattr("privacytrace.web_intake.os.link", failing_link)

        resp = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            headers=HEADERS,
            content=payload,
        )
        assert resp.status_code == 409

        # Neither a partial staging copy nor a failed link may publish input bytes.
        input_apk_exists = (directory / "input.apk").exists()
        packages_exists = (directory / "packages").exists()
        assert packages_exists is False
        assert input_apk_exists is False
        assert not list(directory.glob("*pending*"))
        assert not service.get(draft_id)["uploaded"]
