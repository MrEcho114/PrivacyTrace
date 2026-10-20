"""Pytest configuration and shared fixtures for PrivacyTrace Issue #81 E2E test suite.

Provides:
- sys.path setup for project packages (apps/api/src, apps/api/tests, deploy).
- Synthetic APK and Base+Splits package set builders.
- In-memory / isolated test stores, mock Celery/outbox queues, and mTLS test certificates.
- Opaque-box client factories for remote and local modes.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import pytest

# Ensure project source and test helpers are importable
ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / "apps" / "api" / "src"
API_TESTS = ROOT / "apps" / "api" / "tests"
DEPLOY_DIR = ROOT / "deploy"

for p in (str(API_SRC), str(API_TESTS), str(DEPLOY_DIR), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from apk_fixture_builder import apk_bytes, package_set_archive, dex
from privacytrace.auth import generate_capability_token
from privacytrace.package_set import PackagePart, SplitDependencies, PackageFile


@pytest.fixture
def synthetic_apk_factory():
    """Factory fixture generating valid binary Android APKs with configurable permissions and packages."""

    def _create(
        package_name: str = "org.privacytrace.testapp",
        version_code: str = "100",
        version_name: str = "1.0.0",
        permission: str = "android.permission.CAMERA",
        split: Optional[str] = None,
        is_feature_split: bool = False,
        uses_split: Optional[str] = None,
        config_for_split: Optional[str] = None,
    ) -> bytes:
        manifest_opts = {}
        if is_feature_split:
            manifest_opts["is_feature_split"] = True
        if uses_split:
            manifest_opts["uses_split"] = uses_split
        if config_for_split:
            manifest_opts["config_for_split"] = config_for_split

        is_camera = "camera" in permission.lower()
        return apk_bytes(
            package_name=package_name,
            version_code=version_code,
            version_name=version_name,
            permission=permission,
            split=bool(split),
            split_name=split or "config.en",
            manifest_options=manifest_opts if manifest_opts else None,
            camera=is_camera,
        )

    return _create


@pytest.fixture
def split_package_set_factory(synthetic_apk_factory):
    """Factory fixture generating a valid base APK and split APKs packaged in a zip/apks archive."""

    def _create(
        package_name: str = "org.privacytrace.splitapp",
        version_code: str = "200",
        split_names: Optional[List[str]] = None,
    ) -> bytes:
        if split_names is None:
            split_names = ["config.en", "config.xxhdpi", "feature_camera"]

        # Base APK
        base_apk = synthetic_apk_factory(
            package_name=package_name,
            version_code=version_code,
            permission="android.permission.INTERNET",
            split=None,
        )

        apks = {"base.apk": base_apk}
        for sname in split_names:
            is_feature = sname.startswith("feature_")
            perm = "android.permission.CAMERA" if "camera" in sname else "android.permission.ACCESS_FINE_LOCATION"
            apks[f"{sname}.apk"] = synthetic_apk_factory(
                package_name=package_name,
                version_code=version_code,
                permission=perm,
                split=sname,
                is_feature_split=is_feature,
            )

        return package_set_archive(apks=apks)

    return _create


@pytest.fixture
def test_capability_token():
    """Generates a valid capability token tuple (plaintext, sha256_digest)."""
    return generate_capability_token()
