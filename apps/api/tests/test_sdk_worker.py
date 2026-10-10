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
from privacytrace.sdk_attribution import load_index


def minimal_dex(class_descriptor, *extra_descriptors):
    """A valid DEX containing one class with a ``run()V`` method and no calls.

    Only the class descriptors vary, so any difference in attribution must come
    from the package path and not from unrelated bytecode. ``extra_descriptors``
    add further classes that share the same trivial method shape.
    """
    descriptors = [class_descriptor, *extra_descriptors]
    owners = ["L" + d.strip("L;").replace(".", "/") + ";" for d in descriptors]
    strings = sorted({"Lorg/privacytrace/fixture/Main;", "V", "run", *owners})
    types = sorted({*owners, "V"})
    si = {s: i for i, s in enumerate(strings)}
    ti = {t: i for i, t in enumerate(types)}
    n_methods = len(owners)
    n_classes = len(owners)
    string_off, type_off = 112, 112 + len(strings) * 4
    proto_off = type_off + len(types) * 4
    method_off = proto_off + 12
    class_off = method_off + n_methods * 8
    data_off = class_off + n_classes * 32
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
    class_data_offsets = []
    for _ in owners:
        class_data_offsets.append(data_off + len(data))
        data.extend(
            bytes([0, 0, 1, 0])
            + bytes([si["run"]])
            + bytes([1])
            + struct.pack("<I", code_off)
        )
    align()
    map_off = data_off + len(data)
    maps = [
        (0, 1, 0),
        (1, len(strings), string_off),
        (2, len(types), type_off),
        (3, 1, proto_off),
        (5, n_methods, method_off),
        (6, n_classes, class_off),
        (0x2002, len(strings), data_off),
        (0x2001, 1, code_off),
        (0x2000, n_classes, class_data_offsets[0]),
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
        n_methods,
        method_off,
        n_classes,
        class_off,
        len(data),
        data_off,
    )
    body = struct.pack("<" + "I" * len(strings), *string_offsets)
    body += struct.pack("<" + "I" * len(types), *(si[t] for t in types))
    body += struct.pack("<III", si["V"], ti["V"], 0)
    method_ids = b"".join(struct.pack("<HHI", ti[owner], 0, si["run"]) for owner in owners)
    body += method_ids
    for owner, class_data_off in zip(owners, class_data_offsets):
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

# `minimal_dex` builds its class_def_item map from a single class-data offset, so
# it only carries four classes reliably; past that the DEX fails to parse, every
# class is dropped, and SDK assertions silently degenerate to "no evidence".
FIXTURE_MAX_CLASSES = 4


def test_minimal_dex_fixture_capacity_matches_what_the_tests_assume(tmp_path):
    """Guard the fixture bound so an over-long fixture is never read as a pass."""
    descriptors = [
        f"Lcom/tencent/bugly/crashreport/C{i};" for i in range(FIXTURE_MAX_CLASSES)
    ]
    path = write_apk(tmp_path, "capacity.apk", minimal_dex(*descriptors))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    assert report["coverage"]["failed_dex"] == []
    assert len([i for i in report["evidence"] if i["kind"] == "SDK"]) == FIXTURE_MAX_CLASSES
    # One more class than the fixture supports must not be used by any test.
    over = minimal_dex(*(descriptors + ["Lcn/jpush/android/api/JPushInterface;"]))
    over_path = write_apk(tmp_path, "over.apk", over)
    over_report = scan(over_path, RULES, sdk_rules=SDK_RULES)
    assert over_report["coverage"]["failed_dex"] == ["classes.dex"]


@pytest.mark.parametrize(
    "package,expected_vendor",
    [
        ("com.tencent.bugly.crashreport.CrashReport", "深圳市腾讯计算机系统有限公司"),
        ("cn.jpush.android.api.JPushInterface", "深圳市和讯华谷信息技术有限公司"),
        ("com.amap.api.location.AMapLocationClient", "北京高德图强科技有限公司"),
        ("com.amap.api.maps.AMap", "北京高德图强科技有限公司"),
        ("com.umeng.analytics.MobclickAgent", "友盟同欣（北京）科技有限公司"),
        ("com.umeng.commonsdk.UMConfigure", "友盟同欣（北京）科技有限公司"),
        ("cn.jiguang.verifysdk.api.JVerificationInterface", "深圳市和讯华谷信息技术有限公司"),
        ("cn.jiguang.sdk.api.JPushInterface", "深圳市和讯华谷信息技术有限公司"),
        ("com.tencent.tencentmap.mapsdk.maps.TencentMap", "深圳市腾讯计算机系统有限公司"),
        ("com.tencent.mm.opensdk.openapi.WXAPIFactory", "深圳市腾讯计算机系统有限公司"),
        ("com.mob.MobSDK", "上海游昆信息技术有限公司"),
        ("cn.sharesdk.framework.ShareSDK", "上海游昆信息技术有限公司"),
        ("com.tencent.turingfd.sdk.ams.ga.QQCaptcha", "深圳市腾讯计算机系统有限公司"),
        ("com.tencent.smtt.sdk.WebView", "深圳市腾讯计算机系统有限公司"),
        ("com.tencent.tbs.core.webkit.WebView", "深圳市腾讯计算机系统有限公司"),
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


def test_every_shipped_signature_has_a_worker_level_positive(tmp_path):
    """Guard the acceptance criterion: no signature ships without a real positive."""
    index = load_index(SDK_RULES)
    exercised = {
        "sdk-amap-location": "com.amap.api.location.AMapLocationClient",
        "sdk-amap-maps": "com.amap.api.maps.AMap",
        "sdk-umeng-analytics": "com.umeng.analytics.MobclickAgent",
        "sdk-bugly": "com.tencent.bugly.crashreport.CrashReport",
        "sdk-jpush": "cn.jpush.android.api.JPushInterface",
        "sdk-jiguang-core": "cn.jiguang.sdk.api.JPushInterface",
        "sdk-tencent-map": "com.tencent.tencentmap.mapsdk.maps.TencentMap",
        "sdk-wechat-opensdk": "com.tencent.mm.opensdk.openapi.WXAPIFactory",
        "sdk-mob": "com.mob.MobSDK",
        "sdk-turingfd": "com.tencent.turingfd.sdk.ams.ga.QQCaptcha",
        "sdk-tencent-tbs": "com.tencent.smtt.sdk.WebView",
    }
    signature_ids = {signature.id for signature in index.signatures}
    assert signature_ids == set(exercised), (
        "every shipped signature needs a positive fixture here: "
        f"{sorted(signature_ids ^ set(exercised))}"
    )
    for signature_id, package in exercised.items():
        # The ruleset must claim it, and the worker must emit it end to end.
        assert index.match(package) is not None, signature_id
        assert index.match(package).id == signature_id, signature_id
        path = write_apk(tmp_path, f"{signature_id}.apk", minimal_dex(package))
        report = scan(path, RULES, sdk_rules=SDK_RULES)
        sdk_evidence = [item for item in report["evidence"] if item["kind"] == "SDK"]
        assert len(sdk_evidence) == 1, f"{signature_id}: {report['evidence']}"
        assert sdk_evidence[0]["locator"].endswith("class=" + package)


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


def test_attribution_limitations_are_filed_apart_from_behavior_limitations(tmp_path):
    """SP1: an SDK gap must never be reported as a behavior gap.

    This module produces no behavior, so reporting an attribution limit under
    `behavior_limitations` would mislabel it in the coverage card.
    """
    path = write_apk(tmp_path, "sdk.apk", minimal_dex("com.tencent.bugly.crashreport.CrashReport"))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    coverage = report["coverage"]
    assert "sdk_attribution_limitations" in coverage
    assert coverage["sdk_attribution_limitations"] == []
    # Behavior limitations keep their own, behavior-specific wording.
    assert not any("SDK" in item for item in coverage["behavior_limitations"])


def test_attribution_truncation_is_reported_under_sdk_limitations(tmp_path, monkeypatch):
    """A truncation gap is an SDK coverage gap, so it belongs to the SDK list."""
    from privacytrace import apk_worker

    monkeypatch.setattr(apk_worker, "MAX_SDK_ATTRIBUTIONS", 1)
    classes = [
        "Lcom/tencent/bugly/crashreport/CrashReport;",
        "Lcom/tencent/bugly/crashreport/CrashHandler;",
        "Lcom/tencent/bugly/crashreport/BuglyLog;",
    ]
    path = write_apk(tmp_path, "many.apk", minimal_dex(*classes))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    sdk_evidence = [item for item in report["evidence"] if item["kind"] == "SDK"]
    assert len(sdk_evidence) == 1
    truncation = report["coverage"]["sdk_attribution_limitations"]
    assert len(truncation) == 1
    assert "上限" in truncation[0]
    # The behavior list must stay clean of an SDK concern.
    assert not any("SDK 归属" in item for item in report["coverage"]["behavior_limitations"])


def test_a_large_sdk_cannot_crowd_a_second_sdk_out_of_the_cap(tmp_path, monkeypatch):
    """P1: a representative per SDK is reserved before class-level detail.

    Filling the cap in DEX order let a 500-class SDK read as the only vendor
    present, so a second flagged SDK vanished from the report.
    """
    from privacytrace import apk_worker

    monkeypatch.setattr(apk_worker, "MAX_SDK_ATTRIBUTIONS", 4)
    monkeypatch.setattr(apk_worker, "MAX_SDK_REPRESENTATIVES", 1)
    # Bugly's classes come first and alone would exhaust a 4-slot budget.
    dex_bytes = minimal_dex(
        "Lcom/tencent/bugly/crashreport/CrashReport;",
        "Lcom/umeng/analytics/MobclickAgent;",
        "Lcn/jpush/android/api/JPushInterface;",
    )
    path = write_apk(tmp_path, "crowded.apk", dex_bytes)
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    labelled = [
        item["locator"] for item in report["evidence"] if item["kind"] == "SDK"
    ]
    assert len(labelled) == 3
    # Every flagged vendor survives, including the one reached last.
    assert any("com.umeng.analytics" in locator for locator in labelled), report["evidence"]
    assert any("cn.jpush.android" in locator for locator in labelled), report["evidence"]
    assert any("com.tencent.bugly" in locator for locator in labelled), report["evidence"]


def test_cap_below_the_sdk_count_does_not_claim_an_unpayable_guarantee(
    tmp_path, monkeypatch
):
    """With more flagged SDKs than slots, the note must not promise each one a slot.

    ``MIN_SDK_REPRESENTATIVES == 1`` stays in force (that is the shipped value);
    monkeypatching it to zero would make the floor vacuous and the test would
    assert a guarantee nobody can keep.
    """
    from privacytrace import apk_worker

    monkeypatch.setattr(apk_worker, "MAX_SDK_ATTRIBUTIONS", 2)
    monkeypatch.setattr(apk_worker, "MAX_SDK_REPRESENTATIVES", 1)
    path = write_apk(
        tmp_path,
        "three.apk",
        minimal_dex(
            "Lcom/tencent/bugly/crashreport/CrashReport;",
            "Lcom/umeng/analytics/MobclickAgent;",
            "Lcn/jiguang/verifysdk/api/JVerificationInterface;",
        ),
    )
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    labelled = [item["locator"] for item in report["evidence"] if item["kind"] == "SDK"]
    # The cap is honoured: three flagged SDKs cannot all fit in two slots.
    assert len(labelled) == 2
    note = report["coverage"]["sdk_attribution_limitations"]
    assert len(note) == 1
    assert "3" in note[0]
    # 3 signatures x 1 slot > 2 slots, so no per-SDK guarantee may be advertised.
    assert "已保证" not in note[0]
    assert not apk_worker._per_sdk_floor_is_achievable(3)
    assert apk_worker._per_sdk_floor_is_achievable(2)


def test_truncation_note_advertises_the_floor_only_when_the_budget_allows_it(
    tmp_path, monkeypatch
):
    """One SDK with many classes still fits a floor of one, so the note may claim it."""
    from privacytrace import apk_worker

    monkeypatch.setattr(apk_worker, "MAX_SDK_ATTRIBUTIONS", 2)
    monkeypatch.setattr(apk_worker, "MAX_SDK_REPRESENTATIVES", 1)
    path = write_apk(
        tmp_path,
        "one.apk",
        minimal_dex(
            "Lcom/tencent/bugly/crashreport/CrashReport;",
            "Lcom/tencent/bugly/crashreport/CrashHandler;",
            "Lcom/tencent/bugly/crashreport/BuglyLog;",
        ),
    )
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    note = report["coverage"]["sdk_attribution_limitations"]
    assert len(note) == 1
    assert "已保证" in note[0]
    assert len([i for i in report["evidence"] if i["kind"] == "SDK"]) == 2


def test_evidence_excerpt_names_the_prefix_that_actually_matched(tmp_path):
    """P2: the excerpt must cite the matched prefix, not ``package_prefixes[0]``.

    Umeng publishes two prefixes. A ``com.umeng.commonsdk`` class matches the
    second one, so claiming the first would make the label untraceable.
    """
    path = write_apk(tmp_path, "second.apk", minimal_dex("com.umeng.commonsdk.UMConfigure"))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    excerpt = next(item["excerpt"] for item in report["evidence"] if item["kind"] == "SDK")
    assert "com.umeng.commonsdk" in excerpt
    assert "com.umeng.analytics" not in excerpt


def test_the_prefix_cited_is_always_a_published_prefix_of_the_labelled_sdk(tmp_path):
    """Whatever the excerpt names must be one of the signature's own prefixes.

    The fixture's ``class_def_item`` map is built from a single class-data offset,
    so it carries up to five classes; this stays within that bound.
    """
    index = load_index(SDK_RULES)
    packages = [
        "com.umeng.commonsdk.UMConfigure",
        "com.umeng.analytics.MobclickAgent",
        "cn.jiguang.verifysdk.api.JVerificationInterface",
        "com.tencent.tbs.core.webkit.WebView",
    ]
    path = write_apk(tmp_path, "prefixes.apk", minimal_dex(*packages))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    sdk_evidence = [item for item in report["evidence"] if item["kind"] == "SDK"]
    assert len(sdk_evidence) == len(packages)
    cited = []
    for item in sdk_evidence:
        class_name = item["locator"].split("class=", 1)[1]
        matched = index.match_prefix(class_name)
        assert matched is not None
        assert "prefix " + matched.prefix + " of " in item["excerpt"]
        assert matched.prefix in matched.signature.package_prefixes
        cited.append(matched.prefix)
    # The second prefix of a multi-prefix signature appears as itself, rather
    # than collapsing onto the signature's index-0 prefix.
    assert "com.umeng.analytics" in cited and "com.umeng.commonsdk" in cited
    assert "com.tencent.tbs" in cited


def test_prefix_level_match_reports_the_prefix_it_used():
    """The seam the worker relies on: the match carries its own prefix."""
    index = load_index(SDK_RULES)
    second = index.match_prefix("com.umeng.commonsdk.UMConfigure")
    assert second is not None
    assert second.prefix == "com.umeng.commonsdk"
    assert second.signature.package_prefixes[0] != second.prefix
    assert second.class_name == "com.umeng.commonsdk.UMConfigure"
    assert index.match_prefix("androidx.core.app.ActivityCompat") is None


def test_attribution_selection_is_stable_across_runs(tmp_path):
    """Selection must not depend on hashing order, or reports would drift.

    The fixture's ``class_def_item`` map carries up to four classes, so this
    stays at that bound while still spanning three signatures.
    """
    classes = [
        "Lcom/tencent/bugly/crashreport/C0;",
        "Lcom/tencent/bugly/crashreport/C1;",
        "Lcom/umeng/analytics/MobclickAgent;",
        "Lcn/jpush/android/api/JPushInterface;",
    ]
    path = write_apk(tmp_path, "stable.apk", minimal_dex(*classes))
    first = scan(path, RULES, sdk_rules=SDK_RULES)
    second = scan(path, RULES, sdk_rules=SDK_RULES)
    assert first["evidence"] == second["evidence"]
    assert len([i for i in first["evidence"] if i["kind"] == "SDK"]) == len(classes)


def test_a_truncated_scan_still_produces_a_valid_report_contract(tmp_path, monkeypatch):
    """Truncation changes coverage notes, never the report's shape."""
    from privacytrace import apk_worker
    from privacytrace.resources import ROOT

    monkeypatch.setattr(apk_worker, "MAX_SDK_ATTRIBUTIONS", 1)
    monkeypatch.setattr(apk_worker, "MAX_SDK_REPRESENTATIVES", 1)
    path = write_apk(
        tmp_path,
        "cut.apk",
        minimal_dex(
            "Lcom/tencent/bugly/crashreport/CrashReport;",
            "Lcom/umeng/analytics/MobclickAgent;",
        ),
    )
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    schema = json.loads(
        (ROOT / "packages/contracts/report.schema.json").read_text(encoding="utf-8")
    )
    allowed = set(schema["$defs"]["ScanCoverage"]["properties"])
    assert set(report["coverage"]) <= allowed | {"completeness"}
    # One slot cannot hold both vendors, so the gap must be stated, not hidden.
    assert len(report["coverage"]["sdk_attribution_limitations"]) == 1
    assert json.loads(json.dumps(report, ensure_ascii=True, sort_keys=True))


def test_sdk_attribution_limitations_survive_the_report_contract(tmp_path):
    """The new coverage field must be a first-class part of the report contract."""
    from privacytrace.resources import ROOT

    path = write_apk(tmp_path, "sdk.apk", minimal_dex("com.tencent.bugly.crashreport.CrashReport"))
    report = scan(path, RULES, sdk_rules=SDK_RULES)
    # The worker emits the field on every scan, even when nothing is truncated.
    assert report["coverage"]["sdk_attribution_limitations"] == []
    # The generated report contract exposes it, so the frontend reads rather
    # than silently drops an unknown field.
    schema = json.loads(
        (ROOT / "packages/contracts/report.schema.json").read_text(encoding="utf-8")
    )
    coverage = schema["$defs"]["ScanCoverage"]["properties"]
    assert "sdk_attribution_limitations" in coverage
