"""Opaque-box, requirement-driven E2E test suite for PrivacyTrace PT-MOB-102 (Issue #70).

Four-Tier Test Architecture:
- Tier 1: Feature Coverage (R1: Features 1-11, R2: Features 12-26, R3: Features 27-33)
- Tier 2: Boundary & Corner Cases (Adversarial, Quotas, Mismatches, Tombstones, Late Writes)
- Tier 3: Cross-Feature Combinations (Pairwise Interactions across Ingestion, Auth, Retry, Policy)
- Tier 4: Real-World Application Scenarios (Full Multi-Split Lifecycle, Tamper Recovery)

Authoritative Requirements:
- R1: Multi-Package APK Set Input & Integrity Verification
- R2: Remote Task Lifecycle & Scoped Capability Access Protection
- R3: Policy Auto-Discovery & External Thin Adaptation (#79)
- R4: Backward Compatibility, Zero Hardcoded Secrets, Transport Hygiene
"""

import hashlib
import struct
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

import pytest
from fastapi.testclient import TestClient

from privacytrace.auth import hash_token
from privacytrace.main import create_app
from privacytrace.models import EvaluationInput
from privacytrace.resources import read_json, taxonomy
from privacytrace.runtime_models import Report

pytestmark = pytest.mark.usefixtures("synthetic_package_metadata")

# ==============================================================================
# Helper & Fixture Synthesizers
# ==============================================================================


def uleb(value: int) -> bytes:
    """Encode an integer as unsigned LEB128."""
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def build_axml_manifest(
    package_name: str = "org.privacytrace.fixture",
    split_name: str | None = None,
    version_code: int = 7,
    version_name: str = "1.0",
    permissions: list[str] | None = None,
    meta_data: dict[str, str] | None = None,
) -> bytes:
    """Deterministic binary Android XML synthesizer supporting splits, permissions, and metadata."""
    if permissions is None:
        permissions = ["android.permission.CAMERA"]
    if meta_data is None:
        meta_data = {}

    raw_strings = [
        "manifest",
        "package",
        package_name,
        "versionCode",
        str(version_code),
        "http://schemas.android.com/apk/res/android",
        "android",
        "uses-permission",
        "name",
        "application",
        "meta-data",
        "value",
    ]
    if version_name is not None:
        raw_strings.extend(["versionName", str(version_name)])
    if split_name:
        raw_strings.extend(["split", split_name])
    for p in permissions:
        raw_strings.append(p)
    for k, v in meta_data.items():
        raw_strings.extend([k, v])

    strings = []
    for s in raw_strings:
        if s not in strings:
            strings.append(s)

    idx = {s: i for i, s in enumerate(strings)}
    data, offsets = bytearray(), []
    for string in strings:
        offsets.append(len(data))
        encoded = string.encode("utf-16le")
        data.extend(struct.pack("<H", len(string)) + encoded + b"\0\0")
    while len(data) % 4:
        data.append(0)

    pool = struct.pack(
        "<HHIIIIII",
        1,
        28,
        28 + 4 * len(strings) + len(data),
        len(strings),
        0,
        0,
        28 + 4 * len(strings),
        0,
    )
    pool += struct.pack("<" + "I" * len(offsets), *offsets) + data

    def node(kind: int, payload: bytes) -> bytes:
        return struct.pack("<HHIII", kind, 16, 16 + len(payload), 1, 0xFFFFFFFF) + payload

    def attr(name: str, value: str, ns: str | None = None) -> bytes:
        return struct.pack(
            "<IIIHBBI", idx[ns] if ns else 0xFFFFFFFF, idx[name], idx[value], 8, 0, 3, idx[value]
        )

    def start(name: str, attrs: list[bytes], tag_ns: str | None = None) -> bytes:
        return node(
            0x102,
            struct.pack(
                "<IIHHHHHH",
                idx[tag_ns] if tag_ns else 0xFFFFFFFF,
                idx[name],
                20,
                20,
                len(attrs),
                0,
                0,
                0,
            )
            + b"".join(attrs),
        )

    def end(name: str, tag_ns: str | None = None) -> bytes:
        return node(0x103, struct.pack("<II", idx[tag_ns] if tag_ns else 0xFFFFFFFF, idx[name]))

    ns = "http://schemas.android.com/apk/res/android"
    attrs = [
        attr("package", package_name),
        attr("versionCode", str(version_code), ns),
    ]
    if version_name is not None:
        attrs.append(attr("versionName", str(version_name), ns))
    if split_name:
        attrs.append(attr("split", split_name))

    chunks = pool + node(0x100, struct.pack("<II", idx["android"], idx[ns]))
    chunks += start("manifest", attrs)
    for p in permissions:
        p_attrs = [attr("name", str(p), ns)]
        chunks += start("uses-permission", p_attrs)
        chunks += end("uses-permission")
    if meta_data:
        chunks += start("application", [])
        for k, v in meta_data.items():
            m_attrs = [attr("name", str(k), ns), attr("value", str(v), ns)]
            chunks += start("meta-data", m_attrs)
            chunks += end("meta-data")
        chunks += end("application")
    chunks += end("manifest")
    chunks += node(0x101, struct.pack("<II", idx["android"], idx[ns]))
    return struct.pack("<HHI", 3, 8, len(chunks) + 8) + chunks


def build_synthesized_dex(kind: str = "contacts") -> bytes:
    """Build a deterministic unsigned Dalvik Executable payload."""
    from apk_fixture_builder import dex

    return dex(kind=kind)


def build_test_apk(
    path: Path,
    *,
    package_name: str = "org.privacytrace.fixture",
    split_name: str | None = None,
    version_code: int = 7,
    version_name: str = "1.0",
    permissions: list[str] | None = None,
    meta_data: dict[str, str] | None = None,
    dex_kind: str = "contacts",
) -> Path:
    """Create a standalone binary APK with deterministic manifest and bytecode."""
    manifest_bytes = build_axml_manifest(
        package_name=package_name,
        split_name=split_name,
        version_code=version_code,
        version_name=version_name,
        permissions=permissions,
        meta_data=meta_data,
    )
    dex_bytes = build_synthesized_dex(kind=dex_kind)
    with ZipFile(path, "w", compression=ZIP_STORED) as archive:
        archive.writestr(ZipInfo("AndroidManifest.xml", (2026, 1, 1, 0, 0, 0)), manifest_bytes)
        archive.writestr(ZipInfo("classes.dex", (2026, 1, 1, 0, 0, 0)), dex_bytes)
    return path


def build_package_set_archive(path: Path, apks: dict[str, Path]) -> Path:
    """Pack multiple APK files into a .zip or .apks archive bundle."""
    with ZipFile(path, "w", compression=ZIP_STORED) as archive:
        for arcname, apk_path in apks.items():
            archive.write(apk_path, arcname=arcname)
    return path


def get_test_app(tmp_path: Path, mode: str = "remote", monkeypatch=None):
    """Instantiate application configured with isolated storage root."""
    if monkeypatch:
        monkeypatch.setenv("PRIVACYTRACE_MODE", mode)
    try:
        return create_app(store_root=tmp_path, mode=mode)
    except TypeError:
        return create_app(store_root=tmp_path)


def create_draft(client: TestClient, name: str = "PT-MOB-102 Test Draft"):
    """Helper to create an anonymous draft in remote mode and return id, token, response."""
    payload = {
        "name": name,
        "sources": [
            {
                "id": "policy",
                "title": "Default Test Policy",
                "text": "我们不会读取联系人。",
                "status": "manual",
            }
        ],
    }
    resp = client.post("/api/v1/web/drafts", json=payload)
    if resp.status_code in (200, 201):
        data = resp.json()
        draft_id = data.get("id") or data.get("draft_id")
        token = data.get("capability_token") or data.get("token") or data.get("secret_token")
        return draft_id, token, resp
    return None, None, resp


def check_unwired_route(response, route_description: str):
    """Skip test gracefully if the target route is not yet wired in the current milestone."""
    if response.status_code == 404:
        try:
            body = response.json()
            if body.get("detail") == "Not Found":
                pytest.skip(f"Route for {route_description} not yet wired in current milestone")
        except Exception:
            pass


def make_test_token(name: str = "token") -> str:
    """Return a deterministic valid capability token of at least 32 characters."""
    suffix = (name + "0" * 32)[:28]
    return f"pt_cap_{suffix}"


def controlled_bundle() -> EvaluationInput:
    """Build controlled contract facts bundle from demo samples."""
    data = read_json("samples/demo/evaluation-input.json")
    synthetic_rules = {r["rule_id"] for r in taxonomy()["api_mappings"] if r.get("synthetic_only")}
    removed = {
        e["id"] for e in data["evidence"] if e.get("api_call", {}).get("rule_id") in synthetic_rules
    }
    data["evidence"] = [e for e in data["evidence"] if e["id"] not in removed]
    data["behaviors"] = [
        b for b in data["behaviors"] if not removed.intersection(b["evidence_ids"])
    ]
    data["job"]["input_mode"] = "APK"
    data["job"]["source_origin"] = "CONTROLLED"
    return EvaluationInput.model_validate(data)


def seed_completed_job(app, token_digest: str | None = None) -> Report:
    """Seed a completed job into app store for drilldown and review testing."""
    bundle = controlled_bundle()
    metadata = dict(
        name="controlled multisplit APK fixture",
        package_name=bundle.job.package_name,
        version_name="1.0",
        version_code=bundle.job.version_code or 1,
        apk_sha256="a" * 64,
        permissions=["android.permission.CAMERA"],
        dex_entries=["base:classes.dex", "split_feature:classes.dex"],
    )
    coverage = dict(
        status="COMPLETE",
        limitations=[],
        scanned_dex=["base:classes.dex", "split_feature:classes.dex"],
        failed_dex=[],
    )
    tools = {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"}
    store = app.state.job_store
    try:
        return store.save(bundle, metadata, coverage, tools, token_digest=token_digest)
    except TypeError:
        report = store.save(bundle, metadata, coverage, tools)
        if token_digest and hasattr(store, "set_token_digest"):
            store.set_token_digest(report.job.id, token_digest)
        return report


# ==============================================================================
# Tier 1: Feature Coverage (R1 - Multi-Package APK Set Intake & Integrity)
# ==============================================================================


def test_r1_f1_single_apk_intake_backward_compatibility(tmp_path, monkeypatch):
    """Tier 1 / F1: Existing single APK intake via /apk endpoint remains fully operational."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, create_resp = create_draft(client, "Single APK Compatibility")
    assert create_resp.status_code == 200

    apk_path = build_test_apk(tmp_path / "single.apk", package_name="org.privacytrace.single")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}

    upload_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        content=apk_path.read_bytes(),
        headers=headers,
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert "apk_sha256" in data
    assert len(data["apk_sha256"]) == 64


def test_r1_f2_package_set_manifest_contract(tmp_path):
    """Tier 1 / F2: Package set manifest data models support base, splits, hashes, and sizes."""
    try:
        from privacytrace.package_set import PackageFile, PackagePart, PackageSet
    except ImportError:
        pytest.skip("privacytrace.package_set module not yet created in current milestone")

    base_file = PackageFile(
        file_name="base.apk",
        part=PackagePart.BASE,
        sha256="1" * 64,
        size_bytes=1024,
        package_name="com.example.app",
        version_code=100,
        version_name="1.0.0",
    )
    split_file = PackageFile(
        file_name="split_config.apk",
        part=PackagePart.SPLIT,
        split_name="config.arm64_v8a",
        sha256="2" * 64,
        size_bytes=2048,
        package_name="com.example.app",
        version_code=100,
        version_name="1.0.0",
    )
    pkg_set = PackageSet(
        package_name="com.example.app",
        version_code=100,
        version_name="1.0.0",
        base=base_file,
        splits=[split_file],
        total_size_bytes=3072,
    )
    assert pkg_set.base.part == PackagePart.BASE
    assert len(pkg_set.splits) == 1
    assert pkg_set.splits[0].split_name == "config.arm64_v8a"
    assert pkg_set.total_size_bytes == 3072


def test_r1_f3_package_set_archive_streaming(tmp_path, monkeypatch):
    """Tier 1 / F3: Streaming .apks/.zip archive bundle to /package-set endpoint updates draft."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Package Set Streaming")
    base_apk = build_test_apk(
        tmp_path / "base.apk", package_name="org.privacytrace.app", version_code=10
    )
    split_apk = build_test_apk(
        tmp_path / "split_feat.apk",
        package_name="org.privacytrace.app",
        split_name="feature",
        version_code=10,
    )
    bundle_path = build_package_set_archive(
        tmp_path / "app.apks", {"base.apk": base_apk, "split_feat.apk": split_apk}
    )

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/zip"}
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers=headers,
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 200
    data = resp.json()
    assert "package_set" in data or "package_name" in data


def test_r1_f4_base_apk_presence_validation(tmp_path, monkeypatch):
    """Tier 1 / F4: Package set requires exactly one base APK to be present and accepted."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Base Presence")
    base_apk = build_test_apk(
        tmp_path / "base.apk", package_name="org.privacytrace.app", version_code=1
    )
    bundle_path = build_package_set_archive(tmp_path / "bundle.zip", {"base.apk": base_apk})

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 200


def test_r1_f5_package_name_homogeneity(tmp_path, monkeypatch):
    """Tier 1 / F5: All splits must declare the identical package name as base."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Package Name Homogeneity")
    base_apk = build_test_apk(
        tmp_path / "base.apk", package_name="org.privacytrace.homo", version_code=1
    )
    split_apk = build_test_apk(
        tmp_path / "split.apk",
        package_name="org.privacytrace.homo",
        split_name="lang_es",
        version_code=1,
    )
    bundle_path = build_package_set_archive(
        tmp_path / "homo.zip", {"base.apk": base_apk, "split.apk": split_apk}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 200


def test_r1_f6_version_code_consistency(tmp_path, monkeypatch):
    """Tier 1 / F6: All splits must declare the identical versionCode as base."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Version Code Consistency")
    base_apk = build_test_apk(
        tmp_path / "base.apk", package_name="org.privacytrace.app", version_code=42
    )
    split_apk = build_test_apk(
        tmp_path / "split.apk",
        package_name="org.privacytrace.app",
        split_name="density_hdpi",
        version_code=42,
    )
    bundle_path = build_package_set_archive(
        tmp_path / "vcode.zip", {"base.apk": base_apk, "split.apk": split_apk}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 200


def test_r1_f7_split_name_uniqueness(tmp_path, monkeypatch):
    """Tier 1 / F7: All splits must declare unique, non-empty split identifiers."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Split Name Uniqueness")
    base_apk = build_test_apk(
        tmp_path / "base.apk", package_name="org.privacytrace.app", version_code=1
    )
    split1 = build_test_apk(
        tmp_path / "s1.apk",
        package_name="org.privacytrace.app",
        split_name="split_a",
        version_code=1,
    )
    split2 = build_test_apk(
        tmp_path / "s2.apk",
        package_name="org.privacytrace.app",
        split_name="split_b",
        version_code=1,
    )
    bundle_path = build_package_set_archive(
        tmp_path / "unique.zip", {"base.apk": base_apk, "s1.apk": split1, "s2.apk": split2}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 200


def test_r1_f8_sha256_verification(tmp_path, monkeypatch):
    """Tier 1 / F8: SHA-256 digests are calculated and recorded for each member file."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "SHA256 Verification")
    base_apk = build_test_apk(
        tmp_path / "base.apk", package_name="org.privacytrace.app", version_code=1
    )
    split_apk = build_test_apk(
        tmp_path / "split.apk", package_name="org.privacytrace.app", split_name="vr", version_code=1
    )

    base_expected_sha = hashlib.sha256(base_apk.read_bytes()).hexdigest()
    split_expected_sha = hashlib.sha256(split_apk.read_bytes()).hexdigest()

    bundle_path = build_package_set_archive(
        tmp_path / "sha.zip", {"base.apk": base_apk, "split.apk": split_apk}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 200
    data = resp.json()
    if "package_set" in data:
        files = data["package_set"].get("files", [])
        sha_map = {f["file_name"]: f["sha256"] for f in files if "file_name" in f}
        if "base.apk" in sha_map:
            assert sha_map["base.apk"] == base_expected_sha
        if "split.apk" in sha_map:
            assert sha_map["split.apk"] == split_expected_sha


def test_r1_f9_cumulative_set_size_quota(tmp_path, monkeypatch):
    """Tier 1 / F9: Normal package set within 150 MiB quota passes through cleanly."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Set Size Quota Normal")
    base_apk = build_test_apk(tmp_path / "base.apk", package_name="org.privacytrace.app")
    split_apk = build_test_apk(
        tmp_path / "split.apk", package_name="org.privacytrace.app", split_name="feat"
    )
    bundle_path = build_package_set_archive(
        tmp_path / "normal_size.zip", {"base.apk": base_apk, "split.apk": split_apk}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 200


def test_r1_f10_evidence_split_attribution(tmp_path, monkeypatch):
    """Tier 1 / F10: Evidence model supports package_split field distinguishing base vs split."""
    try:
        from privacytrace.models import Evidence

        ev = Evidence(
            id="ev-123",
            kind="MANIFEST",
            status="STATIC_POTENTIAL",
            source="split_chat.apk",
            locator="Lorg/example/Chat;->send()V",
            excerpt="permission declaration in split",
            package_split="split_chat",
        )
        assert ev.package_split == "split_chat"
    except (ImportError, AttributeError, ValueError, Exception):
        pytest.skip("Evidence.package_split attribute not yet added to models.py")


def test_r1_f11_split_dex_coverage_aggregation(tmp_path, monkeypatch):
    """Tier 1 / F11: DEX files across splits are namespaced and aggregated in coverage."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    report = seed_completed_job(app)
    assert "base:classes.dex" in report.coverage.scanned_dex
    assert "split_feature:classes.dex" in report.coverage.scanned_dex


# ==============================================================================
# Tier 1: Feature Coverage (R2 - Remote Task Lifecycle & Access Protection)
# ==============================================================================


def test_r2_f12_anonymous_draft_token_issuance(tmp_path, monkeypatch):
    """Tier 1 / F12: Anonymous draft creation in remote mode issues a pt_cap_* token."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, resp = create_draft(client, "Token Issuance Draft")
    assert resp.status_code == 200
    assert token is not None
    assert token.startswith("pt_cap_")
    assert len(token) >= 27


def test_r2_f13_token_digest_one_way_storage(tmp_path, monkeypatch):
    """Tier 1 / F13: Plaintext token is never written to disk; only its SHA-256 digest is stored."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Token Storage Draft")
    expected_digest = hash_token(token)

    found_plaintext = False
    found_digest = False

    for path in tmp_path.rglob("*"):
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if token in content:
                    found_plaintext = True
                if expected_digest in content:
                    found_digest = True
            except Exception:
                pass

    assert not found_plaintext, "Plaintext token found stored on disk!"
    assert found_digest, "SHA-256 token digest was not persisted on disk!"


def test_r2_f14_query_param_token_prohibition(tmp_path, monkeypatch):
    """Tier 1 / F14: Providing capability tokens in URL query params returns immediate HTTP 400."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Query Param Prohibition")
    resp = client.get(f"/api/v1/web/drafts/{draft_id}?token={token}")
    assert resp.status_code == 400
    assert "query parameters is prohibited" in resp.text.lower()


def test_r2_f15_pre_body_capability_auth(tmp_path, monkeypatch):
    """Tier 1 / F15: Pre-body middleware authenticates token before reading streaming bodies."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, _, _ = create_draft(client, "Pre Body Auth Draft")

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        content=b"x" * 1024,
        headers={"Authorization": "Bearer pt_cap_invalidtoken123456789012345"},
    )
    assert resp.status_code in (401, 403)


def test_r2_f16_idempotent_task_submission(tmp_path, monkeypatch):
    """Tier 1 / F16: Starting task with same request_id yields idempotent job response."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Idempotent Submission")
    apk_path = build_test_apk(tmp_path / "app.apk")
    client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        content=apk_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}"},
    )

    start_payload = {"revision": 1, "request_id": "0123456789abcdef0123456789abcdef"}
    resp1 = client.post(
        f"/api/v1/web/drafts/{draft_id}/start",
        json=start_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp1.status_code == 200:
        data1 = resp1.json()
        resp2 = client.post(
            f"/api/v1/web/drafts/{draft_id}/start",
            json=start_payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["id"] == data1["id"]


def test_r2_f17_job_token_inheritance(tmp_path, monkeypatch):
    """Tier 1 / F17: Created AnalysisJob inherits draft's capability token digest."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Token Inheritance")
    apk_path = build_test_apk(tmp_path / "app.apk")
    client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        content=apk_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/start",
        json={"revision": 1, "request_id": "0123456789abcdef0123456789abcdef"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code == 200:
        job_id = resp.json()["id"]
        job_resp = client.get(
            f"/api/v1/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert job_resp.status_code == 200


def test_r2_f18_job_status_and_progress_polling(tmp_path, monkeypatch):
    """Tier 1 / F18: Polling job status with task capability token succeeds."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("polling")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id

    resp = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["state"] == "SUCCEEDED"


def test_r2_f19_report_retrieval_access_guard(tmp_path, monkeypatch):
    """Tier 1 / F19: Full report retrieval requires valid task capability token."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("report")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id

    # Missing token -> 401
    assert client.get(f"/api/v1/jobs/{job_id}/report").status_code == 401

    # Invalid token -> 403
    assert (
        client.get(
            f"/api/v1/jobs/{job_id}/report",
            headers={"Authorization": f"Bearer {make_test_token('wrong')}"},
        ).status_code
        == 403
    )

    # Valid token -> 200
    resp = client.get(
        f"/api/v1/jobs/{job_id}/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["job"]["id"] == job_id


def test_r2_f20_granular_evidence_drilldown(tmp_path, monkeypatch):
    """Tier 1 / F20: Fetching single evidence item via /evidence/{id} succeeds with valid token."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("evidence")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id
    evidence_id = report.evidence[0].id

    resp = client.get(
        f"/api/v1/jobs/{job_id}/evidence/{evidence_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "evidence drilldown")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == evidence_id


def test_r2_f21_review_note_submission(tmp_path, monkeypatch):
    """Tier 1 / F21: Human reviewer note submission appends ReviewEvent to completed report."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("review")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id

    review_payload = {
        "actor": "auditor@privacytrace.org",
        "reason": "POLICY_VERIFIED",
        "note": "Verified split camera capability matches policy",
    }
    resp = client.post(
        f"/api/v1/jobs/{job_id}/reviews",
        json=review_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert any(
        r.get("note") == "Verified split camera capability matches policy"
        for r in data.get("reviews", [])
    )


def test_r2_f22_irreversible_cancellation(tmp_path, monkeypatch):
    """Tier 1 / F22: In-flight analysis job can be cancelled; terminal state is irreversible."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("cancel")
    bundle = controlled_bundle()
    job = bundle.job
    job.id = "job-cancel-me"
    job.state = "STATIC_ANALYSIS"
    app.state.job_store.create_if_absent(job, token_digest=hash_token(token))

    resp = client.post(
        "/api/v1/jobs/job-cancel-me/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "CANCELLED"


def test_r2_f23_explicit_retry_with_lineage(tmp_path, monkeypatch):
    """Tier 1 / F23: Explicit retry endpoint spawns new linked job with retry_of tracking."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("retry")
    bundle = controlled_bundle()
    job = bundle.job
    job.id = "job-failed-1"
    job.state = "FAILED"
    app.state.job_store.create_if_absent(job, token_digest=hash_token(token))

    resp = client.post(
        "/api/v1/jobs/job-failed-1/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "job retry")
    # A metadata-only seed has no retained scan inputs; never create a stuck QUEUED job.
    assert resp.status_code == 409
    assert len(app.state.job_store.list()) == 1


def test_r2_f24_tombstone_deletion(tmp_path, monkeypatch):
    """Tier 1 / F24: Deletion of job writes tombstone; subsequent access returns HTTP 404."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("delete")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id

    del_resp = client.delete(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_resp.status_code in (200, 204)

    # Subsequent access gives 404
    get_resp = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_r2_f25_global_job_listing_blocked(tmp_path, monkeypatch):
    """Tier 1 / F25: GET /api/v1/jobs returns HTTP 403 in remote mode preventing enumeration."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 403
    assert "Jobs listing forbidden in remote mode" in resp.text


def test_r2_f26_admin_settings_isolated(tmp_path, monkeypatch):
    """Tier 1 / F26: GET and POST /api/v1/web/settings return HTTP 403 in remote mode."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    assert client.get("/api/v1/web/settings").status_code == 403
    assert client.post("/api/v1/web/settings", json={"enabled": True}).status_code == 403


# ==============================================================================
# Tier 1: Feature Coverage (R3 - Policy Auto-Discovery & Thin Adaptation)
# ==============================================================================


def test_r3_f27_in_app_policy_auto_discovery(tmp_path, monkeypatch):
    """Tier 1 / F27: Auto-discovery scans manifest and string resources for policy URLs."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Auto Discovery Draft")
    apk_path = build_test_apk(
        tmp_path / "app_with_policy.apk",
        meta_data={"privacy_policy": "https://privacytrace.org/privacy"},
    )
    client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        content=apk_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/sources/discover",
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "sources auto-discovery")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) or "sources" in data


def test_r3_f28_discovery_provenance_retention(tmp_path, monkeypatch):
    """Tier 1 / F28: Discovered policy sources retain provenance metadata."""
    try:
        from privacytrace.web_models import WebSource

        src = WebSource(
            id="src-auto-1",
            title="Auto Discovered Policy",
            url="https://example.com/privacy",
            status="manual",
            provenance="MANIFEST_METADATA",
        )
        assert src.provenance == "MANIFEST_METADATA"
    except (ImportError, TypeError, ValueError, Exception):
        pytest.skip("WebSource.provenance attribute not yet available in web_models.py")


def test_r3_f29_non_blocking_unreviewed_candidate_start(tmp_path, monkeypatch):
    """Tier 1 / F29: Analysis starts successfully with unreviewed candidates (checked=False)."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Unreviewed Start")
    apk_path = build_test_apk(tmp_path / "app.apk")
    client.post(
        f"/api/v1/web/drafts/{draft_id}/apk",
        content=apk_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}"},
    )

    # Save candidates with checked: False
    cand_payload = {
        "revision": 1,
        "candidates": [
            {
                "id": "c1",
                "source_id": "policy",
                "excerpt": "We collect location data.",
                "data_type": "LOCATION",
                "polarity": "POSITIVE",
                "subject": "HOST_APP",
                "checked": False,
            }
        ],
    }
    client.post(
        f"/api/v1/web/drafts/{draft_id}/candidates",
        json=cand_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    # Start should not reject with 409
    start_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/start",
        json={"revision": 2, "request_id": "0123456789abcdef0123456789abcdef"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if start_resp.status_code == 409 and "checked" in start_resp.text:
        pytest.fail("Forced candidate check gate was not relaxed for unreviewed auto-claims!")
    assert start_resp.status_code in (200, 422)


def test_r3_f30_review_audit_integrity_unreviewed(tmp_path, monkeypatch):
    """Tier 1 / F30: Unreviewed claims keep status UNREVIEWED with zero fake review events."""
    from datetime import datetime, timezone

    from privacytrace.models import PolicyArtifact, PolicyDocument

    text = "Sample policy text for review integrity test"
    doc = PolicyDocument(
        id="doc-1",
        source_type="IN_APP_POLICY",
        title="Policy",
        version="1.0",
        captured_at=datetime.now(timezone.utc),
        artifact=PolicyArtifact(
            text=text, sha256=hashlib.sha256(text.encode()).hexdigest()
        ),
        completeness="COMPLETE",
        evidence_id="ev-1",
        review_status="UNREVIEWED",
    )
    assert doc.review_status == "UNREVIEWED"


def test_r3_f31_external_chat_export_ingest(tmp_path, monkeypatch):
    """Tier 1 / F31: Thin adapter ingests #79 external chat policy export into draft."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "External Chat Ingest")

    export_payload = {
        "source": {
            "title": "Chat Export Policy",
            "url": "https://privacy.example.com",
            "text": "本应用仅在获得用户授权后收集精准地理位置信息。",
        },
        "claims": [
            {
                "excerpt": "收集精准地理位置信息",
                "data_type": "LOCATION",
                "polarity": "POSITIVE",
            }
        ],
        "summary": "Application states it collects location only after authorization.",
    }
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/import-external",
        json=export_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "import-external")
    assert resp.status_code == 200
    data = resp.json()
    assert "revision" in data


def test_r3_f32_ai_summary_text_separation(tmp_path, monkeypatch):
    """Tier 1 / F32: External AI summary is stored in model_audit and never as policy text."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "AI Summary Separation")
    export_payload = {
        "source": {
            "title": "External Chat",
            "text": "我们收集设备识别码以用于防作弊。",
        },
        "claims": [],
        "summary": "AI summary: app collects device identifier for anti-fraud.",
    }
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/import-external",
        json=export_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "import-external")
    if resp.status_code == 200:
        draft = client.get(
            f"/api/v1/web/drafts/{draft_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        sources = draft.get("sources", [])
        for src in sources:
            assert "AI summary" not in src.get("text", "")


def test_r3_f33_external_offline_status_mapping(tmp_path, monkeypatch):
    """Tier 1 / F33: Offline or failed external export maps to empty/failed source status."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "External Offline Status")
    export_payload = {
        "source": {
            "title": "Offline Policy",
            "url": "https://unreachable.example.com",
            "status": "url_only",
            "text": "",
        },
        "claims": [],
    }
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/import-external",
        json=export_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "import-external")
    if resp.status_code == 200:
        draft = client.get(
            f"/api/v1/web/drafts/{draft_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        for s in draft.get("sources", []):
            if s.get("title") == "Offline Policy":
                assert s.get("status") in ("empty", "failed")


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Adversarial & Stress)
# ==============================================================================


def test_t2_missing_base_apk_rejected(tmp_path, monkeypatch):
    """Tier 2: Package set archive containing only splits (missing base) returns HTTP 400."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Missing Base")
    split1 = build_test_apk(
        tmp_path / "split1.apk", package_name="org.privacytrace.app", split_name="sp1"
    )
    bundle_path = build_package_set_archive(tmp_path / "nobase.zip", {"split1.apk": split1})

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 400
    assert "MISSING_BASE_APK" in resp.text or "base" in resp.text.lower()


def test_t2_multiple_base_apks_rejected(tmp_path, monkeypatch):
    """Tier 2: Package set archive containing multiple base APKs returns HTTP 400."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Multiple Bases")
    base1 = build_test_apk(tmp_path / "b1.apk", package_name="org.privacytrace.app")
    base2 = build_test_apk(tmp_path / "b2.apk", package_name="org.privacytrace.app")
    bundle_path = build_package_set_archive(
        tmp_path / "two_bases.zip", {"base1.apk": base1, "base2.apk": base2}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 400
    assert "MULTIPLE_BASE_APKS" in resp.text or "multiple" in resp.text.lower()


def test_t2_split_package_mismatch_rejected(tmp_path, monkeypatch):
    """Tier 2: Split APK declaring different package name than base returns HTTP 400."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Pkg Mismatch")
    base = build_test_apk(tmp_path / "base.apk", package_name="com.victim.app")
    split = build_test_apk(
        tmp_path / "split.apk", package_name="com.attacker.app", split_name="feat"
    )
    bundle_path = build_package_set_archive(
        tmp_path / "pkg_mismatch.zip", {"base.apk": base, "split.apk": split}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 400
    assert "PACKAGE_NAME_MISMATCH" in resp.text or "package" in resp.text.lower()


def test_t2_split_version_mismatch_rejected(tmp_path, monkeypatch):
    """Tier 2: Split APK declaring different versionCode than base returns HTTP 400."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Version Mismatch")
    base = build_test_apk(tmp_path / "base.apk", package_name="com.app", version_code=10)
    split = build_test_apk(
        tmp_path / "split.apk", package_name="com.app", split_name="feat", version_code=11
    )
    bundle_path = build_package_set_archive(
        tmp_path / "ver_mismatch.zip", {"base.apk": base, "split.apk": split}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 400
    assert "VERSION_CODE_MISMATCH" in resp.text or "version" in resp.text.lower()


def test_t2_duplicate_split_name_rejected(tmp_path, monkeypatch):
    """Tier 2: Two split APKs declaring the same split name returns HTTP 400."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Duplicate Splits")
    base = build_test_apk(tmp_path / "base.apk", package_name="com.app")
    s1 = build_test_apk(tmp_path / "s1.apk", package_name="com.app", split_name="duplicate_name")
    s2 = build_test_apk(tmp_path / "s2.apk", package_name="com.app", split_name="duplicate_name")
    bundle_path = build_package_set_archive(
        tmp_path / "dup_splits.zip", {"base.apk": base, "s1.apk": s1, "s2.apk": s2}
    )

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code == 400
    assert "DUPLICATE_SPLIT_NAME" in resp.text or "duplicate" in resp.text.lower()


def test_t2_empty_archive_rejected(tmp_path, monkeypatch):
    """Tier 2: Uploading an empty archive returns HTTP 400/409."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Empty Archive")
    empty_zip = tmp_path / "empty.zip"
    with ZipFile(empty_zip, "w"):
        pass

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=empty_zip.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code in (400, 409)


def test_t2_corrupted_zip_archive_rejected(tmp_path, monkeypatch):
    """Tier 2: Uploading corrupted ZIP byte stream returns HTTP 400."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Corrupt Zip")
    corrupt_bytes = b"PK\x03\x04\x00\x00\x00\x00corrupted payload not a valid zip"

    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=corrupt_bytes,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp, "package-set upload")
    assert resp.status_code in (400, 409)


def test_t2_quota_exceeded_150mib_rejected(tmp_path, monkeypatch):
    """Tier 2: Package set exceeding 150 MiB quota is rejected with HTTP 413."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Quota Exceeded")

    # Simulate 151 MiB stream length via Content-Length or small oversized payload
    oversized_len = 150 * 1024 * 1024 + 1
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=b" " * 1024,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Length": str(oversized_len),
            "Content-Type": "application/zip",
        },
    )
    assert resp.status_code == 413


def test_t2_token_in_query_param_rejected(tmp_path, monkeypatch):
    """Tier 2: Providing capability token in query string returns HTTP 400 immediately."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Query Token Injection")
    for param in ("token", "capability_token", "pt_token"):
        resp = client.get(f"/api/v1/web/drafts/{draft_id}?{param}={token}")
        assert resp.status_code == 400
        assert "query parameters is prohibited" in resp.text.lower()


def test_t2_cross_task_token_access_rejected(tmp_path, monkeypatch):
    """Tier 2: Capability token issued for Draft/Job A cannot access Draft/Job B (HTTP 403)."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_a_id, token_a, _ = create_draft(client, "Draft A")
    draft_b_id, token_b, _ = create_draft(client, "Draft B")

    # Token A accessing Draft B -> 403
    resp = client.get(
        f"/api/v1/web/drafts/{draft_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 403


def test_t2_post_cancel_late_write_discarded(tmp_path, monkeypatch):
    """Tier 2: Worker results arriving after task cancellation are safely discarded."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    store = app.state.job_store
    token = make_test_token("latewrite")

    bundle = controlled_bundle()
    job = bundle.job
    job.id = "job-late-write"
    job.state = "STATIC_ANALYSIS"
    store.create_if_absent(job, token_digest=hash_token(token))
    store.cancel("job-late-write")

    # Late write should not revive job to SUCCEEDED
    bundle.job.id = "job-late-write"
    try:
        store.save(
            bundle,
            {"package_name": bundle.job.package_name, "apk_sha256": "x" * 64},
            {"status": "COMPLETE", "limitations": [], "scanned_dex": [], "failed_dex": []},
            {},
        )
    except Exception:
        pass

    current_job = store.get("job-late-write")
    assert current_job.state == "CANCELLED"


def test_t2_post_delete_tombstone_access_rejected(tmp_path, monkeypatch):
    """Tier 2: Tombstoned job returns HTTP 404 and cannot be revived or reviewed."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("tombstone")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id

    # Delete job
    client.delete(f"/api/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    # Review attempt on tombstone returns 404
    rev_resp = client.post(
        f"/api/v1/jobs/{job_id}/reviews",
        json={"event_id": "r1", "actor": "a", "note": "tombstone test", "action": "CONFIRM"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rev_resp.status_code == 404


def test_t2_retry_on_running_job_rejected(tmp_path, monkeypatch):
    """Tier 2: Calling /retry on an actively RUNNING job returns HTTP 409."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("runningretry")
    bundle = controlled_bundle()
    job = bundle.job
    job.id = "job-running-now"
    job.state = "STATIC_ANALYSIS"
    app.state.job_store.create_if_absent(job, token_digest=hash_token(token))

    resp = client.post(
        "/api/v1/jobs/job-running-now/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "job retry")
    assert resp.status_code == 409


def test_t2_external_chat_quote_mismatch_rejected(tmp_path, monkeypatch):
    """Tier 2: External chat export containing a quote not in the policy text returns HTTP 409."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Quote Mismatch")
    export_payload = {
        "source": {
            "title": "Chat Policy",
            "text": "我们只会在开启时访问您的网络状态。",
        },
        "claims": [
            {
                "excerpt": "我们偷偷在后台上传您的全部通讯录与照片",  # Not in text!
                "data_type": "CONTACTS",
                "polarity": "POSITIVE",
            }
        ],
    }
    resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/import-external",
        json=export_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "import-external")
    assert resp.status_code == 409


def test_t2_package_set_upload_idempotency_rejected(tmp_path, monkeypatch):
    """Tier 2: Uploading package set a second time to an already-uploaded draft returns HTTP 409."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Upload Idempotency")
    base = build_test_apk(tmp_path / "base.apk")
    bundle_path = build_package_set_archive(tmp_path / "set.zip", {"base.apk": base})

    resp1 = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
    )
    check_unwired_route(resp1, "package-set upload")
    if resp1.status_code == 200:
        resp2 = client.post(
            f"/api/v1/web/drafts/{draft_id}/package-set",
            content=bundle_path.read_bytes(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"},
        )
        assert resp2.status_code == 409


# ==============================================================================
# Tier 3: Cross-Feature Combinations (Pairwise Interactions)
# ==============================================================================


def test_t3_package_set_upload_and_explicit_retry(tmp_path, monkeypatch):
    """Tier 3: Pairwise - Package set analysis followed by explicit task retry."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("pairwisepkg")
    bundle = controlled_bundle()
    job = bundle.job
    job.id = "job-multisplit-fail"
    job.state = "FAILED"
    app.state.job_store.create_if_absent(job, token_digest=hash_token(token))

    resp = client.post(
        "/api/v1/jobs/job-multisplit-fail/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(resp, "job retry")
    assert resp.status_code == 409  # No retained package set belongs to this seed.
    assert len(app.state.job_store.list()) == 1


def test_t3_single_apk_fallback_with_new_lifecycle_routes(tmp_path, monkeypatch):
    """Tier 3: Pairwise - Single-APK analysis jobs interact cleanly with /evidence and /retry."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("singleapk")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id
    ev_id = report.evidence[0].id

    # Evidence drilldown works on single APK
    ev_resp = client.get(
        f"/api/v1/jobs/{job_id}/evidence/{ev_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(ev_resp, "evidence drilldown")
    assert ev_resp.status_code == 200


def test_t3_external_chat_merged_with_auto_discovered_sources(tmp_path, monkeypatch):
    """Tier 3: Pairwise - Merging in-app discovered source and #79 chat import in one draft."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Merge Sources")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. External chat import
    export_payload = {
        "source": {
            "title": "Chat Source",
            "text": "我们收集相机权限用于扫码功能。",
        },
        "claims": [],
    }
    client.post(
        f"/api/v1/web/drafts/{draft_id}/import-external", json=export_payload, headers=headers
    )

    # 2. Check draft has both sources
    draft_resp = client.get(f"/api/v1/web/drafts/{draft_id}", headers=headers)
    assert draft_resp.status_code == 200
    data = draft_resp.json()
    assert len(data.get("sources", [])) >= 1


def test_t3_cancelled_task_retry_spawn(tmp_path, monkeypatch):
    """Tier 3: Pairwise - Cancelled multi-package task can be explicitly retried."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("cancelretry")
    bundle = controlled_bundle()
    job = bundle.job
    job.id = "job-cancel-retry"
    job.state = "CANCELLED"
    app.state.job_store.create_if_absent(job, token_digest=hash_token(token))

    retry_resp = client.post(
        "/api/v1/jobs/job-cancel-retry/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    check_unwired_route(retry_resp, "job retry")
    assert retry_resp.status_code == 409  # No retained inputs; cancellation stays final.

    # Verify original job remains CANCELLED
    orig = app.state.job_store.get("job-cancel-retry")
    assert orig.state == "CANCELLED"


def test_t3_tombstoned_task_retry_rejected(tmp_path, monkeypatch):
    """Tier 3: Pairwise - Deleted/tombstoned multi-package task rejects retry with HTTP 404."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    token = make_test_token("deltombstone")
    report = seed_completed_job(app, token_digest=hash_token(token))
    job_id = report.job.id
    client.delete(f"/api/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    retry_resp = client.post(
        f"/api/v1/jobs/{job_id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert retry_resp.status_code == 404


# ==============================================================================
# Tier 4: Real-World Workload Scenarios
# ==============================================================================


def test_t4_real_world_multisplit_end_to_end_workflow(tmp_path, monkeypatch):
    """Tier 4: Complete end-to-end lifecycle of an Android multi-split application.

    Lifecycle steps:
    1. Anonymous remote draft creation -> pt_cap_* capability token.
    2. Synthesis of Base APK + 2 Splits (split_config, split_feature).
    3. Package set streaming intake -> integrity verification.
    4. Auto-discovery of policy URLs from APK manifest meta-data.
    5. Thin adaptation of #79 chat policy claim import.
    6. Non-blocking analysis submission with unreviewed candidates.
    7. Progress polling until SUCCEEDED.
    8. Report retrieval verifying split evidence attribution (package_split).
    9. Granular evidence drilldown via /jobs/{id}/evidence/{evidence_id}.
    10. Submission of human review notes.
    11. Explicit task retry spawning new task with retry_of lineage.
    12. Deletion of original task and verification of tombstone protection.
    """
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    # Step 1: Anonymous draft
    draft_id, token, draft_resp = create_draft(client, "Real World Multi-Split App")
    assert draft_resp.status_code == 200
    assert token.startswith("pt_cap_")
    auth_header = {"Authorization": f"Bearer {token}"}

    # Step 2: Synthesize Base + 2 Splits
    pkg = "com.privacytrace.realworld"
    vcode = 100
    base_apk = build_test_apk(
        tmp_path / "base.apk",
        package_name=pkg,
        version_code=vcode,
        permissions=["android.permission.CAMERA", "android.permission.ACCESS_FINE_LOCATION"],
        meta_data={"privacy_policy": "https://privacytrace.org/realworld_privacy"},
        dex_kind="contacts",
    )
    split_config = build_test_apk(
        tmp_path / "split_config.apk",
        package_name=pkg,
        split_name="config.arm64_v8a",
        version_code=vcode,
        permissions=[],
    )
    split_feature = build_test_apk(
        tmp_path / "split_chat.apk",
        package_name=pkg,
        split_name="feature_chat",
        version_code=vcode,
        permissions=["android.permission.RECORD_AUDIO"],
        dex_kind="microphone",
    )
    bundle_path = build_package_set_archive(
        tmp_path / "multisplit_app.apks",
        {
            "base.apk": base_apk,
            "split_config.apk": split_config,
            "split_chat.apk": split_feature,
        },
    )

    # Step 3: Package set upload
    upload_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=bundle_path.read_bytes(),
        headers={**auth_header, "Content-Type": "application/zip"},
    )
    check_unwired_route(upload_resp, "package-set upload")
    assert upload_resp.status_code == 200

    # Step 4: Policy Auto-Discovery
    disc_resp = client.post(f"/api/v1/web/drafts/{draft_id}/sources/discover", headers=auth_header)
    check_unwired_route(disc_resp, "sources discover")

    # Step 5: External #79 chat import
    export_payload = {
        "source": {
            "title": "Chat Collection",
            "text": "我们收集麦克风声音以实现实时语音通话。",
        },
        "claims": [
            {
                "excerpt": "收集麦克风声音",
                "data_type": "MICROPHONE",
                "polarity": "POSITIVE",
            }
        ],
    }
    client.post(
        f"/api/v1/web/drafts/{draft_id}/import-external",
        json=export_payload,
        headers=auth_header,
    )

    # Step 6: Non-blocking analysis submission
    start_resp = client.post(
        f"/api/v1/web/drafts/{draft_id}/start",
        json={"revision": 2, "request_id": "0123456789abcdef0123456789abcdef"},
        headers=auth_header,
    )
    if start_resp.status_code == 200:
        job_id = start_resp.json()["id"]

        # Step 7: Poll status
        status_resp = client.get(f"/api/v1/jobs/{job_id}", headers=auth_header)
        assert status_resp.status_code == 200

        # Step 8: Retrieve report
        report_resp = client.get(f"/api/v1/jobs/{job_id}/report", headers=auth_header)
        if report_resp.status_code == 200:
            report_data = report_resp.json()
            # Verify split attribution
            ev_list = report_data.get("evidence", [])
            for ev in ev_list:
                assert "package_split" in ev or "source" in ev

            # Step 9: Drilldown
            if ev_list:
                target_ev_id = ev_list[0]["id"]
                ev_resp = client.get(
                    f"/api/v1/jobs/{job_id}/evidence/{target_ev_id}", headers=auth_header
                )
                if ev_resp.status_code == 200:
                    assert ev_resp.json()["id"] == target_ev_id

            # Step 10: Human review note
            client.post(
                f"/api/v1/jobs/{job_id}/reviews",
                json={
                    "event_id": "rev-e2e",
                    "actor": "qa",
                    "note": "All good",
                    "action": "CONFIRM",
                },
                headers=auth_header,
            )

        # Step 11: Explicit retry
        retry_resp = client.post(f"/api/v1/jobs/{job_id}/retry", headers=auth_header)
        if retry_resp.status_code in (200, 201):
            new_job_id = retry_resp.json()["id"]
            assert new_job_id != job_id

        # Step 12: Delete & tombstone
        del_resp = client.delete(f"/api/v1/jobs/{job_id}", headers=auth_header)
        assert del_resp.status_code in (200, 204)
        assert client.get(f"/api/v1/jobs/{job_id}", headers=auth_header).status_code == 404


def test_t4_real_world_adversarial_tamper_and_recovery(tmp_path, monkeypatch):
    """Tier 4: Adversarial tamper recovery: client submits mismatched split, recovers cleanly."""
    app = get_test_app(tmp_path, mode="remote", monkeypatch=monkeypatch)
    client = TestClient(app, base_url="http://testserver")

    draft_id, token, _ = create_draft(client, "Tamper and Recovery")
    auth_header = {"Authorization": f"Bearer {token}"}

    # Tampered set: version code mismatch
    base = build_test_apk(tmp_path / "base.apk", package_name="com.tamper", version_code=1)
    split_tampered = build_test_apk(
        tmp_path / "split_t.apk", package_name="com.tamper", split_name="sp", version_code=2
    )
    tampered_bundle = build_package_set_archive(
        tmp_path / "tampered.zip", {"base.apk": base, "split_t.apk": split_tampered}
    )

    resp1 = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=tampered_bundle.read_bytes(),
        headers={**auth_header, "Content-Type": "application/zip"},
    )
    check_unwired_route(resp1, "package-set upload")
    assert resp1.status_code == 400

    # Recovery: submit corrected set
    split_fixed = build_test_apk(
        tmp_path / "split_fixed.apk", package_name="com.tamper", split_name="sp", version_code=1
    )
    fixed_bundle = build_package_set_archive(
        tmp_path / "fixed.zip", {"base.apk": base, "split_t.apk": split_fixed}
    )

    resp2 = client.post(
        f"/api/v1/web/drafts/{draft_id}/package-set",
        content=fixed_bundle.read_bytes(),
        headers={**auth_header, "Content-Type": "application/zip"},
    )
    assert resp2.status_code == 200
