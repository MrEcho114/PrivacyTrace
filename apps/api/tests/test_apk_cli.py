"""Acceptance at the agreed APK scan CLI seam, with real compiled-format fixtures."""

import json
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from apk_fixture_builder import apk, dex, manifest


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


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("no_hits", "COMPLETE"),
        ("no_primary", "PARTIAL"),
        ("bad_dex", "PARTIAL"),
        ("split", "PARTIAL"),
    ],
)
def test_dex_completion_never_claims_exhaustive_behavior_detection(tmp_path, mode, expected):
    options = {"permission": "android.permission.INTERNET", "invoke": False}
    if mode == "no_primary":
        options["entries"] = {"classes2.dex": dex(invoke=False)}
    elif mode == "bad_dex":
        options["entries"] = {"classes.dex": dex(invoke=False), "classes2.dex": b"bad dex"}
    elif mode == "split":
        options["split"] = True
    result, report = scan(apk(tmp_path / "scope.apk", **options))
    assert result.returncode == 0
    coverage = report["coverage"]
    assert coverage["completeness"] == expected
    assert coverage["scope"] == "DEX_ENTRIES"
    assert coverage["behavior_detection"] == "LIMITED_RULE_BASED_STATIC"
    assert any("反射" in limitation for limitation in coverage["behavior_limitations"])
    assert any("规则" in limitation for limitation in coverage["behavior_limitations"])
    if mode == "no_hits":
        assert report["behaviors"] == []


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


def test_uses_permission_sdk_23_is_recognized(tmp_path):
    path = apk(
        tmp_path / "sdk23.apk",
        permission="android.permission.CAMERA",
        sdk_23_permission="android.permission.RECORD_AUDIO",
    )
    result, report = scan(path)
    assert result.returncode == 0
    assert "android.permission.RECORD_AUDIO" in report["permissions"]
    assert any(
        e["kind"] == "MANIFEST" and "android.permission.RECORD_AUDIO" in e["excerpt"]
        for e in report["evidence"]
    )
    assert any(
        b["action"] == "CAPABILITY" and b["data_type"] == "MICROPHONE" for b in report["behaviors"]
    )


@pytest.mark.parametrize("tag", ["uses-permission", "uses-permission-sdk-23"])
def test_cli_ignores_nested_permission_declarations(tmp_path, tag):
    options = (
        {"permission": "android.permission.RECORD_AUDIO", "permission_parent": "application"}
        if tag == "uses-permission"
        else {
            "sdk_23_permission": "android.permission.RECORD_AUDIO",
            "sdk_23_parent": "application",
        }
    )
    path = apk(
        tmp_path / "nested.apk",
        entries={"AndroidManifest.xml": manifest(**options), "classes.dex": dex(invoke=False)},
    )
    result, report = scan(path)
    assert result.returncode == 0
    assert "android.permission.RECORD_AUDIO" not in report["permissions"]
    assert not any(b["data_type"] == "MICROPHONE" for b in report["behaviors"])
    assert not any("android.permission.RECORD_AUDIO" in e["excerpt"] for e in report["evidence"])


@pytest.mark.parametrize("namespace", [None, "http://schemas.example.com/apk/res/custom"])
def test_cli_ignores_permission_names_outside_android_namespace(tmp_path, namespace):
    path = apk(
        tmp_path / "wrong-namespace.apk",
        entries={
            "AndroidManifest.xml": manifest(
                permission="android.permission.RECORD_AUDIO", permission_namespace=namespace
            ),
            "classes.dex": dex(invoke=False),
        },
    )
    result, report = scan(path)
    assert result.returncode == 0
    assert report["permissions"] == []
    assert not any(b["data_type"] == "MICROPHONE" for b in report["behaviors"])


@pytest.mark.parametrize(
    "tag_namespace",
    ["http://schemas.android.com/apk/res/android", "http://schemas.example.com/apk/res/custom"],
)
def test_cli_ignores_namespaced_permission_elements(tmp_path, tag_namespace):
    path = apk(
        tmp_path / "namespaced-tags.apk",
        entries={
            "AndroidManifest.xml": manifest(
                permission="android.permission.RECORD_AUDIO",
                sdk_23_permission="android.permission.RECORD_AUDIO",
                permission_tag_namespace=tag_namespace,
            ),
            "classes.dex": dex(invoke=False),
        },
    )
    result, report = scan(path)
    assert result.returncode == 0
    assert report["permissions"] == []
    assert not any(b["data_type"] == "MICROPHONE" for b in report["behaviors"])


@pytest.mark.parametrize("value_type", [0x10, 0x11])
def test_cli_reads_typed_binary_integer_version_code(tmp_path, value_type):
    path = apk(
        tmp_path / "typed-version.apk",
        entries={
            "AndroidManifest.xml": manifest(version_code="7", version_code_type=value_type),
            "classes.dex": dex(invoke=False),
        },
    )
    result, report = scan(path)
    assert result.returncode == 0
    assert report["version_code"] == 7
    assert report["errors"] == []


def test_hex_version_code_parsed_without_manifest_invalid(tmp_path):
    path = apk(tmp_path / "hex_version.apk", version_code="0x00000007")
    result, report = scan(path)
    assert result.returncode == 0
    assert report["version_code"] == 7
    assert report["errors"] == []


def test_sget_object_static_uri_resolves_and_matches_query(tmp_path):
    path_contacts = apk(tmp_path / "contacts_sget.apk", kind="sget_contacts")
    res_c, report_c = scan(path_contacts)
    assert res_c.returncode == 0
    assert any(
        b["action"] == "ACCESS" and b["data_type"] == "CONTACTS" for b in report_c["behaviors"]
    )
    call_c = next(e for e in report_c["evidence"] if e["kind"] == "API")
    assert call_c["api_call"]["context"] == {"uri": "content://com.android.contacts/contacts"}

    path_media = apk(tmp_path / "media_sget.apk", kind="sget_media")
    res_m, report_m = scan(path_media)
    assert res_m.returncode == 0
    assert any(
        b["action"] == "ACCESS" and b["data_type"] == "FILES_MEDIA" for b in report_m["behaviors"]
    )
    call_m = next(e for e in report_m["evidence"] if e["kind"] == "API")
    assert call_m["api_call"]["context"] == {"uri": "content://media/external/images/media"}


def test_apk_version_name_none_and_long_are_valid(tmp_path):
    path_none = apk(tmp_path / "none_version.apk", version_name=None)
    res_none, report_none = scan(path_none)
    assert res_none.returncode == 0
    assert report_none["version_name"] is None

    long_name = "v" * 250
    path_long = apk(tmp_path / "long_version.apk", version_name=long_name)
    res_long, report_long = scan(path_long)
    assert res_long.returncode == 0
    assert report_long["version_name"] == long_name

    huge_name = "w" * 1200
    path_huge = apk(tmp_path / "huge_version.apk", version_name=huge_name)
    res_huge, report_huge = scan(path_huge)
    assert res_huge.returncode == 0
    assert len(report_huge["version_name"]) == 1024


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


@pytest.mark.parametrize("version,encoding", [
    (0x80000000, 0x11), (0xffffffff, 0x11), (0x80000000, 0x10),
    ("2147483648", None), ("9223372036854775807", None),
])
def test_version_code_outside_nonnegative_signed_32_bit_range_is_rejected(
    tmp_path, version, encoding
):
    result, report = scan(apk(
        tmp_path / "outside-range.apk", invoke=False,
        manifest_options={"version_code": version, "version_code_type": encoding},
    ))
    assert result.returncode != 0
    assert report["errors"][0]["code"] == "MANIFEST_INVALID"
    assert report["version_code"] is None
    assert report["behaviors"] == []
    assert report["evidence"] == []


@pytest.mark.parametrize("version,encoding", [(0, 0x10), (0, 0x11), (2147483647, 0x10)])
def test_version_code_supported_range_endpoints(tmp_path, version, encoding):
    result, report = scan(apk(
        tmp_path / "endpoint.apk", invoke=False,
        manifest_options={"version_code": version, "version_code_type": encoding},
    ))
    assert result.returncode == 0, result.stderr
    assert report["version_code"] == version


def test_same_permission_dual_declarations_keep_distinct_sdk_evidence(tmp_path):
    result, report = scan(apk(
        tmp_path / "dual-permission.apk", invoke=False,
        sdk_23_permission="android.permission.CAMERA",
        manifest_options={"max_sdk": 22, "sdk_23_max_sdk": 28},
    ))
    assert result.returncode == 0, result.stderr
    assert report["permissions"] == ["android.permission.CAMERA"]
    assert len(report["evidence"]) == len(report["behaviors"]) == 2
    evidence = {e["id"]: e for e in report["evidence"]}
    assert len(evidence) == 2
    assert len({b["id"] for b in report["behaviors"]}) == 2
    ordinary = next(e for e in evidence.values() if ";tag=uses-permission;" in e["locator"])
    sdk23 = next(e for e in evidence.values() if ";tag=uses-permission-sdk-23;" in e["locator"])
    for field in ("locator", "excerpt"):
        assert "max_sdk=22" in ordinary[field]
        assert "min_sdk=" not in ordinary[field]
        assert "min_sdk=23" in sdk23[field] and "max_sdk=28" in sdk23[field]
    for behavior in report["behaviors"]:
        assert behavior["action"] == "CAPABILITY"
        assert behavior["data_type"] == "CAMERA"
        assert behavior["purpose"] == "UNKNOWN"
        assert len(behavior["evidence_ids"]) == 1
        ev = evidence[behavior["evidence_ids"][0]]
        assert ev["kind"] == "MANIFEST" and ev["status"] == "STATIC_POTENTIAL"


@pytest.mark.parametrize("count", [500, 501, 600])
def test_mapped_output_is_bounded_without_losing_the_report(tmp_path, count):
    result, report = scan(
        apk(tmp_path / "many.apk", camera=True, invoke_count=count,
            permission="android.permission.INTERNET")
    )
    assert result.returncode == 0
    assert len(report["behaviors"]) == 500
    assert len(report["evidence"]) == 500
    assert len({e["id"] for e in report["evidence"]}) == 500
    assert report["coverage"]["completeness"] == "COMPLETE"
    assert report["coverage"]["scanned_dex"] == ["classes.dex"]
    truncated = " ".join(report["coverage"]["behavior_limitations"])
    assert ("output truncated at 500" in truncated) == (count > 500)
