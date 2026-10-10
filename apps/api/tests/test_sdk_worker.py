"""PT-401 acceptance at the worker seam: SDK packages are labelled, lookalikes are not.

These tests drive the real ``scan`` over real DEX bytes. They assert the two
things the issue asks for: a known SDK package range reaches an SDK evidence
record, and a structurally similar custom class does not. They also assert the
hard boundary that an SDK label never becomes a privacy behavior.
"""

import hashlib
import json
import struct
import zlib

import pytest

from privacytrace.apk_worker import scan
from privacytrace.resources import read_json


def minimal_dex(class_descriptor):
    """A valid DEX containing one class with a ``run()V`` method and no calls.

    Only the class descriptor varies, so any difference in attribution must come
    from the package path and not from unrelated bytecode.
    """
    owner = "L" + class_descriptor.strip("L;").replace(".", "/") + ";"
    strings = sorted({"Lorg/privacytrace/fixture/Main;", "V", "run", owner})
    types = sorted({owner, "V"})
    si = {s: i for i, s in enumerate(strings)}
    ti = {t: i for i, t in enumerate(types)}
    string_off, type_off = 112, 112 + len(strings) * 4
    proto_off = type_off + len(types) * 4
    method_off = proto_off + 12
    class_off = method_off + 8
    data_off = class_off + 32
    data = bytearray()

    def align():
        while (data_off + len(data)) % 4:
            data.append(0)

    string_offsets = []
    for s in strings:
        string_offsets.append(data_off + len(data))
        data.extend(bytes([len(s)]) + s.encode() + b"\0")
    align()
    code_off = data_off + len(data)
    words = [0x000E]  # return-void
    data.extend(struct.pack("<HHHHII", 1, 0, 1, 0, 0, len(words)))
    data.extend(struct.pack("<" + "H" * len(words), *words))
    class_data_off = data_off + len(data)
    data.extend(bytes([0, 0, 1, 0]) + bytes([si["run"]]) + bytes([1]) + struct.pack("<I", code_off))
    align()
    map_off = data_off + len(data)
    maps = [
        (0, 1, 0),
        (1, len(strings), string_off),
        (2, len(types), type_off),
        (3, 1, proto_off),
        (5, 1, method_off),
        (6, 1, class_off),
        (0x2002, len(strings), data_off),
        (0x2001, 1, code_off),
        (0x2000, 1, class_data_off),
        (0x1000, 1, map_off),
    ]
    maps.sort(key=lambda m: m[2])
    data.extend(struct.pack("<I", len(maps)))
    for kind_id, count, offset in maps:
        data.extend(struct.pack("<HHII", kind_id, 0, count, offset))
    header = b"dex\n035\0" + bytes(24)
    header += struct.pack(
        "<20I",
        data_off + len(data),
        112,
        0x12345678,
        0,
        0,
        map_off,
        len(strings),
        string_off,
        len(types),
        type_off,
        1,
        proto_off,
        0,
        0,
        1,
        method_off,
        1,
        class_off,
        len(data),
        data_off,
    )
    body = struct.pack("<" + "I" * len(strings), *string_offsets)
    body += struct.pack("<" + "I" * len(types), *(si[t] for t in types))
    body += struct.pack("<III", si["V"], ti["V"], 0)
    body += struct.pack("<HHI", ti[owner], 0, si["run"])
    body += struct.pack(
        "<8I", ti[owner], 1, ti["V"], 0, 0xFFFFFFFF, 0, class_data_off, 0
    )
    result = bytearray(header + body + data)
    result[12:32] = hashlib.sha1(result[32:]).digest()
    result[8:12] = struct.pack("<I", zlib.adler32(result[12:]))
    return bytes(result)


def write_apk(tmp_path, name, dex_bytes, package="org.privacytrace.fixture"):
    """A minimal APK carrying one DEX and a manifest the worker can parse."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from apk_fixture_builder import apk

    return apk(
        tmp_path / name,
        entries={"classes.dex": dex_bytes},
        permission="android.permission.INTERNET",
    )


RULES = read_json("rules/taxonomy.v0.3.json")
SDK_RULES = read_json("rules/sdk-signatures.v1.0.json")


@pytest.mark.parametrize(
    "package,expected_vendor",
    [
        ("com.tencent.bugly.crashreport.CrashReport", "腾讯 Bugly"),
        ("cn.jpush.android.api.JPushInterface", "深圳市和讯华谷信息技术有限公司"),
        ("com.amap.api.location.AMapLocationClient", "北京高德图强科技有限公司"),
        ("com.umeng.analytics.MobclickAgent", "友盟同欣（北京）科技有限公司"),
    ],
)
def test_worker_labels_known_sdk_packages(tmp_path, package, expected_vendor):
    path = write_apk(tmp_path, "sdk.apk", minimal_dex(package))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    sdk_evidence = [item for item in report["evidence"] if item["kind"] == "SDK"]
    assert len(sdk_evidence) == 1, report["evidence"]
    locator = sdk_evidence[0]["locator"]
    assert "class=" + package in locator
    assert expected_vendor in sdk_evidence[0]["excerpt"]
    assert report["tools"]["sdk_signatures"] == "1.0.0"


@pytest.mark.parametrize(
    "package",
    [
        # Sibling package, one trailing character apart.
        "com.tencent.buglyx.Fake",
        "cn.jpush.androidx.Fake",
        # Vendor name as a package segment of a different owner.
        "com.example.bugly.CrashHandler",
        # Platform namespace that must never be attributed.
        "androidx.core.app.ActivityCompat",
        "com.android.internal.telephony.Phone",
        # Ordinary host-app class: no rule should claim it.
        "org.privacytrace.fixture.Main",
    ],
)
def test_worker_does_not_label_lookalikes(tmp_path, package):
    path = write_apk(tmp_path, "fake.apk", minimal_dex(package))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    assert [item for item in report["evidence"] if item["kind"] == "SDK"] == []


def test_sdk_attribution_creates_no_privacy_behavior(tmp_path):
    """The issue's core boundary: presence of an SDK is not a collection event."""
    path = write_apk(tmp_path, "sdk.apk", minimal_dex("com.tencent.bugly.crashreport.CrashReport"))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    assert [item for item in report["evidence"] if item["kind"] == "SDK"]
    # No behavior references SDK evidence, and no behavior is fabricated.
    sdk_ids = {item["id"] for item in report["evidence"] if item["kind"] == "SDK"}
    for behavior in report["behaviors"]:
        assert not sdk_ids & set(behavior["evidence_ids"])
    assert all(item["status"] == "STATIC_POTENTIAL" for item in report["evidence"])


def test_attribution_is_disabled_without_a_ruleset(tmp_path):
    path = write_apk(tmp_path, "sdk.apk", minimal_dex("com.tencent.bugly.crashreport.CrashReport"))
    report = scan(path, RULES)
    assert [item for item in report["evidence"] if item["kind"] == "SDK"] == []
    assert "sdk_signatures" not in report["tools"]


def test_sdk_evidence_locator_carries_the_apk_hash(tmp_path):
    path = write_apk(tmp_path, "sdk.apk", minimal_dex("com.tencent.bugly.crashreport.CrashReport"))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    for item in report["evidence"]:
        if item["kind"] == "SDK":
            assert "apk_sha256=" + digest in item["locator"]


def test_scan_output_remains_json_serialisable(tmp_path):
    path = write_apk(tmp_path, "sdk.apk", minimal_dex("cn.jpush.android.api.JPushInterface"))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    assert json.loads(json.dumps(report, ensure_ascii=True, sort_keys=True))
