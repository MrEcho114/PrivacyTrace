"""Acceptance at the agreed APK scan CLI seam, with real compiled-format fixtures."""

import json
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from apk_fixture_builder import apk, dex


def scan(path, *args):
    result = subprocess.run(
        [sys.executable, "-m", "privacytrace.apk_worker", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    return result, json.loads(result.stdout)


def test_cli_reads_binary_manifest_and_real_dex_invocation(tmp_path):
    result, report = scan(apk(tmp_path / "fixture.apk"))
    assert result.returncode == 0
    assert report["package_name"] == "org.privacytrace.fixture"
    assert report["version_code"] == 7
    assert report["permissions"] == ["android.permission.CAMERA"]
    assert report["coverage"]["scanned_dex"] == ["classes.dex"]
    assert {b["data_type"] for b in report["behaviors"]} >= {"PRECISE_LOCATION", "CAMERA"}
    call = next(e for e in report["evidence"] if e["kind"] == "API")
    assert call["api_call"]["context"] == {"provider": "gps"}
    assert "offset_bytes=6" in call["locator"]


@pytest.mark.parametrize("tag", ["uses-permission", "uses-permission-sdk-23"])
@pytest.mark.parametrize("max_sdk", [None, 28])
def test_permission_tags_preserve_sdk_bounds_as_capabilities(tmp_path, tag, max_sdk):
    result, report = scan(apk(
        tmp_path / "permission.apk", invoke=False,
        manifest_options={"permission_tag": tag, "max_sdk": max_sdk},
    ))
    assert result.returncode == 0, result.stderr
    assert report["permissions"] == ["android.permission.CAMERA"]
    assert len(report["behaviors"]) == 1
    behavior = report["behaviors"][0]
    assert behavior["action"] == "CAPABILITY"
    assert behavior["data_type"] == "CAMERA"
    assert behavior["purpose"] == "UNKNOWN"
    evidence = report["evidence"][0]
    assert evidence["kind"] == "MANIFEST"
    assert behavior["evidence_ids"] == [evidence["id"]]
    for field in ("locator", "excerpt"):
        assert ("min_sdk=23" in evidence[field]) == (tag == "uses-permission-sdk-23")
        assert ("max_sdk=28" in evidence[field]) == (max_sdk == 28)


@pytest.mark.parametrize(
    "version, encoding", [(7, 0x10), (7, 0x11), (2147483647, 0x11), ("007", None)]
)
def test_binary_manifest_integer_version_encodings(tmp_path, version, encoding):
    result, report = scan(apk(
        tmp_path / "version.apk", invoke=False,
        manifest_options={"version_code": version, "version_code_type": encoding},
    ))
    assert result.returncode == 0, result.stderr
    assert report["version_code"] == int(version)


@pytest.mark.parametrize("version", ["-1", "not-an-integer", "1.5"])
def test_invalid_version_code_remains_a_structured_error(tmp_path, version):
    result, report = scan(apk(
        tmp_path / "invalid-version.apk", manifest_options={"version_code": version},
    ))
    assert result.returncode != 0
    assert report["errors"][0]["code"] == "MANIFEST_INVALID"


def test_cli_scans_multidex_and_rejects_corrupted_dex_without_losing_good_evidence(tmp_path):
    damaged = bytearray(dex(camera=True))
    damaged[8] ^= 1  # Independently break the DEX header checksum.
    result, report = scan(
        apk(
            tmp_path / "multi.apk",
            entries={
                "classes.dex": dex(),
                "classes2.dex": dex(camera=True),
                "classes3.dex": bytes(damaged),
            },
        )
    )
    assert result.returncode == 0
    assert report["coverage"]["completeness"] == "PARTIAL"
    assert report["coverage"]["scanned_dex"] == ["classes.dex", "classes2.dex"]
    assert report["coverage"]["failed_dex"] == ["classes3.dex"]
    assert any(e["source"] == "classes2.dex" and e["kind"] == "API" for e in report["evidence"])


def test_missing_jadx_is_explicit_fallback_and_preserves_bytecode_evidence(tmp_path):
    result, report = scan(apk(tmp_path / "jadx.apk"), "--jadx", "missing-jadx-fixture-binary")
    assert result.returncode == 0
    assert report["tools"]["jadx"] == "UNAVAILABLE_BYTECODE_FALLBACK"
    assert any(e["kind"] == "API" for e in report["evidence"])
    assert any("JADX" in line for line in report["coverage"]["limitations"])


@pytest.mark.parametrize(
    "options, expected",
    [
        ({"invoke": False}, set()),
        ({"provider": "network"}, {"COARSE_LOCATION"}),
        ({"provider": "unknown"}, {"LOCATION"}),
        ({"branch": True}, {"LOCATION"}),
        ({"camera": True}, {"CAMERA"}),
        ({"kind": "android_id"}, {"ANDROID_ID"}),
        ({"kind": "imei"}, {"IMEI"}),
        ({"kind": "microphone"}, {"MICROPHONE"}),
        ({"kind": "contacts"}, {"CONTACTS"}),
        ({"kind": "media"}, {"FILES_MEDIA"}),
        ({"kind": "arbitrary_uri"}, set()),
    ],
)
def test_only_real_invocations_and_proven_straight_line_arguments_match(
    tmp_path, options, expected
):
    result, report = scan(apk(tmp_path / "case.apk", **options))
    assert result.returncode == 0
    assert {b["data_type"] for b in report["behaviors"] if b["action"] == "ACCESS"} == expected


def test_split_without_primary_dex_is_not_complete(tmp_path):
    result, report = scan(
        apk(tmp_path / "split.apk", split=True, entries={"classes2.dex": dex(camera=True)})
    )
    assert result.returncode == 0
    assert report["coverage"]["completeness"] == "PARTIAL"
    assert len(report["coverage"]["limitations"]) >= 3


@pytest.mark.parametrize("entry", ["../escape", "/absolute", "C:/drive", "folder\\escape"])
def test_zip_escape_entries_fail_before_parsing(tmp_path, entry):
    path = apk(tmp_path / "unsafe.apk", entries={entry.replace("\\", "/"): b"x"})
    if "\\" in entry:
        path.write_bytes(path.read_bytes().replace(b"folder/escape", b"folder\\escape"))
    result, report = scan(path)
    assert result.returncode != 0
    assert report["errors"][0]["code"] == "UNSAFE_ZIP"
    assert report["evidence"] == []


def test_bad_manifest_fails_with_structured_error(tmp_path):
    path = tmp_path / "bad.apk"
    with ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"not binary XML")
        archive.writestr("classes.dex", dex())
    result, report = scan(path)
    assert result.returncode != 0
    assert report["errors"][0]["code"] == "MANIFEST_INVALID"


@pytest.mark.parametrize(
    "kind, rule_id",
    [
        ("accessibility_screenshot", "android.screen.accessibility-screenshot"),
        ("automation_screenshot", "android.screen.automation-screenshot"),
    ],
)
def test_screen_capture_is_only_trusted_full_descriptor_static_invocation(tmp_path, kind, rule_id):
    result, positive = scan(apk(tmp_path / "screen.apk", kind=kind))
    assert result.returncode == 0
    access = [b for b in positive["behaviors"] if b["action"] == "ACCESS"]
    assert [b["data_type"] for b in access] == ["SCREEN_CAPTURE"]
    assert access[0]["purpose"] == "UNKNOWN"
    api = next(e for e in positive["evidence"] if e["kind"] == "API")
    assert api["api_call"]["rule_id"] == rule_id
    assert api["api_call"]["context"] == {}
    _, negative = scan(apk(tmp_path / "screen-string.apk", kind=kind, invoke=False))
    assert not any(e["kind"] == "API" for e in negative["evidence"])


def test_same_bytes_produce_same_ids_and_locators(tmp_path):
    path = apk(tmp_path / "stable.apk")
    _, first = scan(path)
    _, second = scan(path)
    assert first == second


def test_external_storage_declaration_is_legacy_capability_not_access(tmp_path):
    result, report = scan(
        apk(
            tmp_path / "legacy.apk",
            invoke=False,
            permission="android.permission.WRITE_EXTERNAL_STORAGE",
        )
    )
    assert result.returncode == 0
    assert [b["data_type"] for b in report["behaviors"]] == ["FILES_MEDIA"]
    assert report["behaviors"][0]["action"] == "CAPABILITY"
    assert report["behaviors"][0]["purpose"] == "UNKNOWN"
    assert report["evidence"][0]["kind"] == "MANIFEST"


def test_inventory_is_bounded_real_method_references_not_signature_strings(tmp_path):
    _, positive = scan(apk(tmp_path / "invoke.apk", kind="android_id"), "--inventory")
    calls = json.loads(positive["tools"]["unmapped_android_invokes"])
    assert len(calls) == 1
    assert calls[0]["target_descriptor"] == (
        "Landroid/provider/Settings$Secure;->getString"
        "(Landroid/content/ContentResolver;Ljava/lang/String;)Ljava/lang/String;"
    )
    assert calls[0]["dex"] == "classes.dex"
    assert calls[0]["offset_bytes"] == 6
    _, negative = scan(apk(tmp_path / "string.apk", kind="android_id", invoke=False), "--inventory")
    assert json.loads(negative["tools"]["unmapped_android_invokes"]) == []


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("duplicate", "UNSAFE_ZIP"),
        ("symlink", "UNSAFE_ZIP"),
        ("bomb", "ZIP_SIZE_LIMIT"),
        ("crc", "ZIP_INVALID"),
    ],
)
def test_untrusted_zip_integrity_checks_are_structured_cli_failures(tmp_path, mode, expected):
    path = apk(tmp_path / "integrity.apk", entries={"extra": b"UNIQUE_CORRUPTION"})
    if mode == "duplicate":
        with pytest.warns(UserWarning), ZipFile(path, "a") as archive:
            archive.writestr("extra", b"duplicate")
    elif mode == "symlink":
        info = ZipInfo("link")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        with ZipFile(path, "a") as archive:
            archive.writestr(info, b"/outside")
    elif mode == "bomb":
        with ZipFile(path, "a", compression=ZIP_DEFLATED) as archive:
            archive.writestr("bomb", b"0" * 1000000)
    else:
        path.write_bytes(path.read_bytes().replace(b"UNIQUE_CORRUPTION", b"UNIQUE_CORRUPTIOX"))
    result, report = scan(path)
    assert result.returncode != 0
    assert report["errors"][0]["code"] == expected
