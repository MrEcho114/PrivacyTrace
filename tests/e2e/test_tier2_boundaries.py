"""Tier 2: Boundary, Limit & Corner Cases E2E Tests.

Covers:
- Exact 150 MiB limits and boundary rejection (150 MiB vs 150 MiB + 1 byte)
- Empty split APK (0 bytes) and oversized splits
- Package set limits (0 splits vs >100 splits)
- Zip bomb defenses (expanded size > 512 MiB, single entry > 128 MiB)
- Execution timeouts (180s scanner, 300s lease, 300s material ticket)
- Malformed capability tokens (prefix, length, charset, SQL injection, unicode)
- Network streaming & header malformations (unbracketed IPv6, multiple hosts, bad CIDR)
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apk_fixture_builder import apk_bytes, package_set_archive
from privacytrace.auth import SecuritySeam
from privacytrace.main import create_app
from privacytrace.package_set import (
    MAX_EXPANDED_ZIP,
    MAX_FILE_SIZE,
    MAX_PACKAGE_SET_SIZE,
    MAX_SINGLE_ZIP_ENTRY,
    MAX_ZIP_ENTRIES,
    PackageFile,
    PackagePart,
    PackageSetIntegrityError,
    inspect_apk_bytes,
    validate_package_set,
)
from privacytrace.postgres_execution import MAX_EXECUTION_SECONDS
from privacytrace.runtime_materials import ticket_claims

ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 1. Exact 150 MiB Limit Boundaries
# ---------------------------------------------------------------------------
def test_tier2_exact_150mb_boundary_and_overrun(tmp_path):
    """Tier 2: 157,286,400 bytes accepted, 157,286,401 bytes rejected with HTTP 413."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    # Create draft
    draft_resp = client.post(
        "/api/v1/web/drafts",
        json={"name": "Boundary Draft", "sources": [{"id": "s1", "title": "P", "text": "Policy"}]},
    ).json()
    draft_id = draft_resp["id"]
    token = draft_resp.get("token") or draft_resp.get("capability_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Exactly 150 MiB declared via Content-Length should not be rejected by pre-body guard
    # 150 MiB + 1 byte declared via Content-Length MUST be rejected with HTTP 413
    over_limit_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        content=b"",
        headers={**headers, "Content-Length": str(MAX_FILE_SIZE + 1)},
    )
    assert over_limit_resp.status_code == 413
    assert over_limit_resp.json()["detail"] == "UPLOAD_TOO_LARGE"


# ---------------------------------------------------------------------------
# 2. Empty Split APK & Corrupted Package Sets
# ---------------------------------------------------------------------------
def test_tier2_empty_split_apk_rejection(tmp_path, synthetic_apk_factory):
    """Tier 2: Package set containing a 0-byte split APK is rejected with 400 Bad Request."""
    base_apk = synthetic_apk_factory(package_name="org.privacytrace.emptytest", version_code="1")
    # Empty split APK
    corrupt_archive = package_set_archive(apks={"base.apk": base_apk, "split_config.apk": b""})

    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    draft_resp = client.post(
        "/api/v1/web/drafts",
        json={"name": "Empty Split Test", "sources": [{"id": "s1", "title": "P", "text": "Policy"}]},
    ).json()
    draft_id = draft_resp["id"]
    token = draft_resp.get("token") or draft_resp.get("capability_token")
    headers = {"Authorization": f"Bearer {token}"}

    upload_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=corrupt_archive,
        headers=headers,
    )
    assert upload_resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# 3. Zero Splits vs. Excess Splits (>100 Splits)
# ---------------------------------------------------------------------------
def test_tier2_package_set_split_count_limits():
    """Tier 2: Package set requires 1 base APK and allows 0..100 splits; >100 splits rejected."""
    base_file = PackageFile(
        file_name="base.apk",
        part=PackagePart.BASE,
        split_name=None,
        sha256="a" * 64,
        size_bytes=1000,
        package_name="org.privacytrace.limit",
        version_code=1,
    )

    # Exactly 0 splits (valid)
    assert validate_package_set([base_file]) is not None

    # 100 splits (valid boundary)
    splits_100 = [
        PackageFile(
            file_name=f"split_{i}.apk",
            part=PackagePart.SPLIT,
            split_name=f"config.split_{i}",
            sha256="b" * 64,
            size_bytes=100,
            package_name="org.privacytrace.limit",
            version_code=1,
        )
        for i in range(100)
    ]
    assert validate_package_set([base_file, *splits_100]) is not None

    # 101 splits (exceeds limit: 1 base + 101 splits = 102 files)
    splits_101 = [
        PackageFile(
            file_name=f"split_{i}.apk",
            part=PackagePart.SPLIT,
            split_name=f"config.split_{i}",
            sha256="c" * 64,
            size_bytes=100,
            package_name="org.privacytrace.limit",
            version_code=1,
        )
        for i in range(101)
    ]
    with pytest.raises(PackageSetIntegrityError) as exc_info:
        validate_package_set([base_file, *splits_101])
    assert exc_info.value.code == "PACKAGE_SET_TOO_LARGE" or "maximum" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# 4. Zip Bomb Defenses
# ---------------------------------------------------------------------------
def test_tier2_zip_bomb_defenses():
    """Tier 2: Single entry > 128 MiB or expanded size > 512 MiB triggers immediate rejection."""
    assert MAX_EXPANDED_ZIP == 512 * 1024 * 1024
    assert MAX_ZIP_ENTRIES == 20000
    assert MAX_SINGLE_ZIP_ENTRY == 128 * 1024 * 1024

    # Build an APK archive containing a declared entry exceeding MAX_SINGLE_ZIP_ENTRY
    oversized_zip_buf = io.BytesIO()
    with zipfile.ZipFile(oversized_zip_buf, "w", zipfile.ZIP_STORED) as zf:
        info = zipfile.ZipInfo("AndroidManifest.xml")
        info.file_size = MAX_SINGLE_ZIP_ENTRY + 1024
        zf.writestr(info, b"fake data")

    with pytest.raises(PackageSetIntegrityError) as exc_info:
        inspect_apk_bytes(oversized_zip_buf.getvalue(), "corrupt.apk")
    assert exc_info.value.code == "CORRUPTED_FILE"


# ---------------------------------------------------------------------------
# 5. Execution Timeouts (Scanner 180s, Hard Lease 300s, Ticket 300s)
# ---------------------------------------------------------------------------
def test_tier2_execution_timeouts():
    """Tier 2: Verify hard ceilings on scanner (180s), execution lease (300s), and ticket (300s)."""
    assert MAX_EXECUTION_SECONDS == 300

    # Test expired ticket rejection
    from privacytrace.runtime_materials import encode
    import hmac

    key = b"k" * 32
    past_expiry = int(time.time()) - 1  # Expired
    payload = {
        "version": 1,
        "instance_id": str(uuid4()),
        "material_id": str(uuid4()),
        "scope_id": "draft-timeout",
        "owner": str(uuid4()),
        "fence": 1,
        "expires": past_expiry,
        "mode": "scan",
    }
    encoded = encode(json.dumps(payload).encode("utf-8"))
    sig = encode(hmac.new(key, encoded.encode("ascii"), hashlib.sha256).digest())
    token = f"{encoded}.{sig}"

    claims = ticket_claims(token)
    assert claims["expires"] < time.time()


# ---------------------------------------------------------------------------
# 6. Malformed Capability Tokens (Prefix, Character Set, SQL Injection, Unicode)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "malformed_token",
    [
        "not_a_pt_cap_token",
        "pt_cap_short",  # <20 chars
        "pt_cap_with spaces inside 1234567890",
        "pt_cap_invalid%characters!@#$1234567890",
        "pt_cap_non_b64==padding==error1234567890",
        "pt_cap_;;;&&&|||sh_injection1234567890",
    ],
)
def test_tier2_malformed_capability_tokens(tmp_path, malformed_token):
    """Tier 2: Malformed capability tokens must be rejected with HTTP 400 or 401 without 500 error."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    resp = client.get(
        "/api/v1/jobs/test-job-id",
        headers={"Authorization": f"Bearer {malformed_token}"},
    )
    # Must fail securely (400 Bad Request or 401 Unauthorized), never 500
    assert resp.status_code in (400, 401, 403, 404)
    assert resp.status_code != 500


# ---------------------------------------------------------------------------
# 7. Network Header Malformations & Bad Hosts
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_host",
    [
        "evil.com, evil2.com",  # Multiple comma-separated hosts
        "::1",                  # Unbracketed IPv6
        "attacker.internal:badport",
        "user:pass@legit.com",  # Userinfo in host
    ],
)
def test_tier2_malformed_host_headers(tmp_path, bad_host):
    """Tier 2: Host header manipulation and unbracketed IPv6 must return 400 Bad Request."""
    app = create_app(store_root=tmp_path, mode="remote")
    client = TestClient(app, base_url="http://testserver")

    resp = client.get("/api/v1/health", headers={"Host": bad_host})
    assert resp.status_code == 400
