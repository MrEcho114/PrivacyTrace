"""PT-401 acceptance: known signatures are labelled, lookalikes are not.

Positive cases prove the sourced ruleset reaches the classes it claims.
Negative cases prove a structurally similar custom class or a platform
namespace never receives a vendor attribution.
"""

import pytest

from privacytrace.resources import ROOT, sdk_signatures, taxonomy
from privacytrace.sdk_attribution import descriptor_to_class, load_index

RULES = sdk_signatures()
INDEX = load_index(RULES)


@pytest.mark.parametrize(
    "class_name,expected",
    [
        ("com.amap.api.location.AMapLocationClient", "sdk-amap-location"),
        ("com.amap.api.location.core.GeoLocation", "sdk-amap-location"),
        ("com.amap.api.maps.MapView", "sdk-amap-maps"),
        ("com.umeng.analytics.MobclickAgent", "sdk-umeng-analytics"),
        ("com.umeng.commonsdk.UMConfigure", "sdk-umeng-analytics"),
        ("com.tencent.bugly.crashreport.CrashReport", "sdk-bugly"),
        ("cn.jpush.android.api.JPushInterface", "sdk-jpush"),
        ("cn.jiguang.verifysdk.api.JVerificationInterface", "sdk-jiguang-core"),
        ("com.tencent.tencentmap.mapsdk.maps.TencentMap", "sdk-tencent-map"),
        ("com.tencent.mm.opensdk.openapi.WXAPIFactory", "sdk-wechat-opensdk"),
        ("com.mob.tools.utils.SharePrefrenceHelper", "sdk-mob"),
        ("com.tencent.turingfd.sdk.tbs.TuringManager", "sdk-turingfd"),
        ("com.tencent.smtt.sdk.WebView", "sdk-tencent-tbs"),
        # The prefix itself is the whole package: still a match.
        ("com.tencent.bugly", "sdk-bugly"),
    ],
)
def test_known_signatures_are_labelled(class_name, expected):
    match = INDEX.match(class_name)
    assert match is not None, class_name
    assert match["id"] == expected


@pytest.mark.parametrize(
    "class_name",
    [
        # Sibling package differing by one trailing letter: not the same package.
        "com.amap.api.locationx.Fake",
        "com.tencent.buglyx.Fake",
        "cn.jpush.androidx.Fake",
        # Prefix appearing only as a name fragment, not a package boundary.
        "com.example.myamap.api.location.Fake",
        "org.example.tencent.bugly.Fake",
        # Host-app classes that merely resemble a vendor namespace.
        "com.example.app.bugly.CrashHandler",
        "com.example.app.jpush.PushHelper",
    ],
)
def test_structurally_similar_custom_classes_are_not_labelled(class_name):
    assert INDEX.match(class_name) is None


@pytest.mark.parametrize(
    "class_name",
    [
        "androidx.core.app.ActivityCompat",
        "android.app.Activity",
        "com.android.internal.telephony.Phone",
        "java.lang.String",
        "kotlin.collections.MapsKt",
        "org.jetbrains.annotations.NotNull",
        "org.apache.http.client.HttpClient",
        "org.json.JSONObject",
        "dalvik.system.DexClassLoader",
    ],
)
def test_platform_and_runtime_namespaces_are_excluded(class_name):
    assert INDEX.match(class_name) is None


def test_descriptor_conversion_handles_objects_and_arrays():
    assert descriptor_to_class("Lcom/tencent/bugly/crashreport/CrashReport;") == (
        "com.tencent.bugly.crashreport.CrashReport"
    )
    assert descriptor_to_class("[[Lcn/jpush/android/api/JPushInterface;") == (
        "cn.jpush.android.api.JPushInterface"
    )
    # Primitives and malformed descriptors are not class names.
    assert descriptor_to_class("I") is None
    assert descriptor_to_class("") is None
    assert descriptor_to_class("com/tencent/bugly") is None
    labelled = INDEX.match_descriptor("Lcom/tencent/bugly/crashreport/CrashReport;")
    assert labelled is not None and labelled["id"] == "sdk-bugly"


def test_signature_prefixes_do_not_overlap_across_vendors():
    """Two rules claiming one prefix would make attribution ambiguous."""
    seen: dict[str, str] = {}
    for signature in RULES["signatures"]:
        for prefix in signature["package_prefixes"]:
            assert prefix not in seen, (
                f"{prefix} claimed by {seen.get(prefix)} and {signature['id']}"
            )
            seen[prefix] = signature["id"]


def test_every_signature_is_sourced_and_versioned():
    assert RULES["version"] == "1.0.0"
    assert RULES["status"] == "LIMITED_SOURCED_SEED"
    for signature in RULES["signatures"]:
        assert signature["source"], signature["id"]
        assert signature["source_url"].startswith("https://"), signature["id"]
        assert signature["license"], signature["id"]
        assert signature["verified_at"], signature["id"]
        # A vendor attribution without a real vendor is not an attribution.
        assert "synthetic" not in signature["vendor"].lower(), signature["id"]


def test_signature_data_types_resolve_in_the_taxonomy():
    known = {item["id"] for item in taxonomy()["data_types"]}
    for signature in RULES["signatures"]:
        assert signature["potential_data_types"], signature["id"]
        assert set(signature["potential_data_types"]) <= known, signature["id"]


def test_boundaries_state_the_limits_of_attribution():
    text = " ".join(RULES["boundaries"])
    assert "不等于实际收集" in text
    assert "不能替代宿主" in text
    assert "不构成法律主体认定" in text
    assert "不承诺覆盖全国产生态" in text


def test_ruleset_is_reachable_from_the_source_checkout():
    assert (ROOT / "rules/sdk-signatures.v1.0.json").is_file()


def test_malformed_rulesets_are_rejected():
    broken = {
        "version": "1.0.0",
        "signatures": [{"id": "x", "vendor": "v"}],
        "excluded_namespaces": ["a"],
    }
    with pytest.raises(ValueError):
        load_index(broken)
    bad_prefix = {
        "version": "1.0.0",
        "signatures": [
            {
                "id": "x",
                "vendor": "v",
                "package_prefixes": [".com.foo"],
                "potential_data_types": ["LOCATION"],
            }
        ],
        "excluded_namespaces": ["a"],
    }
    with pytest.raises(ValueError):
        load_index(bad_prefix)
    no_exclusions = {
        "version": "1.0.0",
        "signatures": [
            {
                "id": "x",
                "vendor": "v",
                "package_prefixes": ["com.foo"],
                "potential_data_types": ["LOCATION"],
            }
        ],
        "excluded_namespaces": [],
    }
    with pytest.raises(ValueError):
        load_index(no_exclusions)
