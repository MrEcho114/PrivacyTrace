import json
import struct
from pathlib import Path

import pytest
from apk_fixture_builder import apk

from privacytrace.apk_worker import ScanError, scan


def build_custom_manifest(
    version_code="7",
    version_name="1.0",
    permissions_spec=None,
    extra_attrs=None,
):
    """
    Builds a flexible binary AXML ResXMLTree.
    permissions_spec is a list of dicts:
      [
        {"tag": "uses-permission", "attr": "name", "val": "...", "ns": "android"},
        {"tag": "uses-permission-sdk-23", "attr": "name", "val": "...", "ns": "android"},
        ...
      ]
    """
    if permissions_spec is None:
        permissions_spec = [
            {
                "tag": "uses-permission",
                "attr": "name",
                "val": "android.permission.CAMERA",
                "ns": "android",
            }
        ]

    ns_android = "http://schemas.android.com/apk/res/android"
    ns_custom = "http://schemas.example.com/apk/res/custom"

    raw_strings = [
        "manifest",
        "package",
        "org.privacytrace.fixture",
        "versionCode",
        str(version_code),
        ns_android,
        "android",
        ns_custom,
        "custom",
    ]
    if version_name is not None:
        raw_strings.extend(["versionName", str(version_name)])

    for p in permissions_spec:
        raw_strings.extend([p["tag"], p["attr"], str(p["val"])])

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

    def node(kind, payload):
        return struct.pack("<HHIII", kind, 16, 16 + len(payload), 1, 0xFFFFFFFF) + payload

    def attr(name, value, ns_uri=None):
        ns_idx = idx[ns_uri] if ns_uri and ns_uri in idx else 0xFFFFFFFF
        return struct.pack("<IIIHBBI", ns_idx, idx[name], idx[value], 8, 0, 3, idx[value])

    def start(name, attrs):
        return node(
            0x102,
            struct.pack("<IIHHHHHH", 0xFFFFFFFF, idx[name], 20, 20, len(attrs), 0, 0, 0)
            + b"".join(attrs),
        )

    def end(name):
        return node(0x103, struct.pack("<II", 0xFFFFFFFF, idx[name]))

    attrs = [
        attr("package", "org.privacytrace.fixture"),
        attr("versionCode", str(version_code), ns_android),
    ]
    if version_name is not None:
        attrs.append(attr("versionName", str(version_name), ns_android))

    chunks = pool + node(0x100, struct.pack("<II", idx["android"], idx[ns_android]))
    chunks += start("manifest", attrs)
    for p in permissions_spec:
        ns_val = None
        if p.get("ns") == "android":
            ns_val = ns_android
        elif p.get("ns") == "custom":
            ns_val = ns_custom
        chunks += start(p["tag"], [attr(p["attr"], str(p["val"]), ns_val)])
        chunks += end(p["tag"])
    chunks += end("manifest")
    chunks += node(0x101, struct.pack("<II", idx["android"], idx[ns_android]))
    return struct.pack("<HHI", 3, 8, len(chunks) + 8) + chunks


@pytest.fixture
def rules():
    return json.loads(Path("rules/taxonomy.v0.3.json").read_text(encoding="utf-8"))


# --- VersionCode Tests ---


@pytest.mark.parametrize(
    "hex_code, expected_int",
    [
        ("0x00000007", 7),
        ("0x10", 16),
        ("0x7fffffff", 2147483647),
        ("0x7FFFFFFF", 2147483647),
        ("0x0", 0),
        ("0", 0),
        ("12345", 12345),
        ("  0x10  ", 16),
    ],
)
def test_version_code_valid_hex_and_integers(tmp_path, rules, hex_code, expected_int):
    p = tmp_path / f"vc_{expected_int}.apk"
    axml = build_custom_manifest(version_code=hex_code)
    apk(p, entries={"AndroidManifest.xml": axml})
    res = scan(p, rules)
    assert res["version_code"] == expected_int
    assert res["errors"] == []


@pytest.mark.parametrize(
    "invalid_code",
    [
        "0xFFFFFFFF",
        "-1",
        "-0x10",
        "-7",
        "-0x7fffffff",
        "not_hex",
        "0xZZ",
        "",
        "   ",
        "1.5",
        "0x",
        "None",
        "null",
        "0x12g",
    ],
)
def test_version_code_rejects_negative_and_malformed(tmp_path, rules, invalid_code):
    p = tmp_path / "vc_invalid.apk"
    axml = build_custom_manifest(version_code=invalid_code)
    apk(p, entries={"AndroidManifest.xml": axml})
    with pytest.raises(ScanError) as exc_info:
        scan(p, rules)
    assert exc_info.value.code == "MANIFEST_INVALID"
    assert "versionCode" in exc_info.value.message


def test_version_code_large_number(tmp_path, rules):
    # versionCode is not versionCodeMajor/longVersionCode: reject unsupported 64-bit values.
    large_val = "9223372036854775807"
    p = tmp_path / "vc_large.apk"
    axml = build_custom_manifest(version_code=large_val)
    apk(p, entries={"AndroidManifest.xml": axml})
    with pytest.raises(ScanError) as exc_info:
        scan(p, rules)
    assert exc_info.value.code == "MANIFEST_INVALID"


# --- Permissions & SDK-23 Tests ---


def test_sdk_23_with_no_namespace_is_ignored(tmp_path, rules):
    # The manifest syntax requires android:name, not an unqualified name.
    spec = [
        {
            "tag": "uses-permission-sdk-23",
            "attr": "name",
            "val": "android.permission.RECORD_AUDIO",
            "ns": None,
        }
    ]
    p = tmp_path / "sdk23_no_ns.apk"
    axml = build_custom_manifest(permissions_spec=spec)
    apk(p, entries={"AndroidManifest.xml": axml})
    res = scan(p, rules)
    assert res["permissions"] == []
    assert not any(
        b["action"] == "CAPABILITY" and b["data_type"] == "MICROPHONE" for b in res["behaviors"]
    )


def test_sdk_23_coexistence_and_deduplication(tmp_path, rules):
    # Both declare same permission + another distinct permission
    spec = [
        {
            "tag": "uses-permission",
            "attr": "name",
            "val": "android.permission.CAMERA",
            "ns": "android",
        },
        {
            "tag": "uses-permission-sdk-23",
            "attr": "name",
            "val": "android.permission.CAMERA",
            "ns": "android",
        },
        {
            "tag": "uses-permission-sdk-23",
            "attr": "name",
            "val": "android.permission.RECORD_AUDIO",
            "ns": "android",
        },
        {
            "tag": "uses-permission",
            "attr": "name",
            "val": "android.permission.ACCESS_FINE_LOCATION",
            "ns": "android",
        },
    ]
    p = tmp_path / "sdk23_coexist.apk"
    axml = build_custom_manifest(permissions_spec=spec)
    apk(p, entries={"AndroidManifest.xml": axml})
    res = scan(p, rules)
    assert res["permissions"] == [
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.CAMERA",
        "android.permission.RECORD_AUDIO",
    ]
    behavior_types = {b["data_type"] for b in res["behaviors"]}
    assert "CAMERA" in behavior_types
    assert "MICROPHONE" in behavior_types
    assert "LOCATION" in behavior_types or "PRECISE_LOCATION" in behavior_types


def test_sdk_23_multiple_entries(tmp_path, rules):
    spec = [
        {
            "tag": "uses-permission-sdk-23",
            "attr": "name",
            "val": "android.permission.CAMERA",
            "ns": "android",
        },
        {
            "tag": "uses-permission-sdk-23",
            "attr": "name",
            "val": "android.permission.RECORD_AUDIO",
            "ns": "android",
        },
        {
            "tag": "uses-permission-sdk-23",
            "attr": "name",
            "val": "android.permission.READ_CONTACTS",
            "ns": "android",
        },
    ]
    p = tmp_path / "sdk23_multiple.apk"
    axml = build_custom_manifest(permissions_spec=spec)
    apk(p, entries={"AndroidManifest.xml": axml})
    res = scan(p, rules)
    assert set(res["permissions"]) == {
        "android.permission.CAMERA",
        "android.permission.RECORD_AUDIO",
        "android.permission.READ_CONTACTS",
    }


def test_sdk_23_empty_names_are_filtered(tmp_path, rules):
    spec = [
        {"tag": "uses-permission-sdk-23", "attr": "name", "val": "", "ns": "android"},
        {
            "tag": "uses-permission-sdk-23",
            "attr": "name",
            "val": "android.permission.CAMERA",
            "ns": "android",
        },
    ]
    p = tmp_path / "sdk23_empty.apk"
    axml = build_custom_manifest(permissions_spec=spec)
    apk(p, entries={"AndroidManifest.xml": axml})
    res = scan(p, rules)
    assert res["permissions"] == ["android.permission.CAMERA"]


def test_sdk_23_namespaces_and_casing(tmp_path, rules):
    # Standard android namespace works
    p1 = tmp_path / "ns_android.apk"
    axml1 = build_custom_manifest(
        permissions_spec=[
            {
                "tag": "uses-permission-sdk-23",
                "attr": "name",
                "val": "android.permission.RECORD_AUDIO",
                "ns": "android",
            }
        ]
    )
    apk(p1, entries={"AndroidManifest.xml": axml1})
    assert scan(p1, rules)["permissions"] == ["android.permission.RECORD_AUDIO"]

    # Bare name attribute (no namespace) is not android:name.
    p2 = tmp_path / "ns_bare.apk"
    axml2 = build_custom_manifest(
        permissions_spec=[
            {
                "tag": "uses-permission-sdk-23",
                "attr": "name",
                "val": "android.permission.RECORD_AUDIO",
                "ns": None,
            }
        ]
    )
    apk(p2, entries={"AndroidManifest.xml": axml2})
    assert scan(p2, rules)["permissions"] == []

    # Custom namespace is ignored (aligns with Android OS PackageParser)
    p3 = tmp_path / "ns_custom.apk"
    axml3 = build_custom_manifest(
        permissions_spec=[
            {
                "tag": "uses-permission-sdk-23",
                "attr": "name",
                "val": "android.permission.RECORD_AUDIO",
                "ns": "custom",
            }
        ]
    )
    apk(p3, entries={"AndroidManifest.xml": axml3})
    assert scan(p3, rules)["permissions"] == []

    # Tag casing: uppercase/mixed-case tags are ignored (AXML tags are case-sensitive in Android OS)
    p4 = tmp_path / "casing_upper.apk"
    axml4 = build_custom_manifest(
        permissions_spec=[
            {
                "tag": "USES-PERMISSION-SDK-23",
                "attr": "name",
                "val": "android.permission.RECORD_AUDIO",
                "ns": "android",
            }
        ]
    )
    apk(p4, entries={"AndroidManifest.xml": axml4})
    assert scan(p4, rules)["permissions"] == []
