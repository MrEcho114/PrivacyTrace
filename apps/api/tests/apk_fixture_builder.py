"""Deterministic unsigned APK fixtures: real binary AXML and DEX, never installed.

The hand-assembled bytecode is test input, not a mocked parser. Layout follows the
Android DEX/ResXMLTree formats. No Android SDK, binary downloads, or JVM required.
"""

import hashlib
import struct
import zlib
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo


def uleb(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def manifest(split=False, permission="android.permission.CAMERA"):
    strings = [
        "manifest",
        "package",
        "org.privacytrace.fixture",
        "versionCode",
        "7",
        "versionName",
        "1.0",
        "http://schemas.android.com/apk/res/android",
        "android",
        "uses-permission",
        "name",
        permission,
        "split",
        "config.en",
    ]
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

    def attr(name, value, ns=None):
        return struct.pack(
            "<IIIHBBI", idx[ns] if ns else 0xFFFFFFFF, idx[name], idx[value], 8, 0, 3, idx[value]
        )

    def start(name, attrs):
        return node(
            0x102,
            struct.pack("<IIHHHHHH", 0xFFFFFFFF, idx[name], 20, 20, len(attrs), 0, 0, 0)
            + b"".join(attrs),
        )

    def end(name):
        return node(0x103, struct.pack("<II", 0xFFFFFFFF, idx[name]))

    ns = strings[7]
    attrs = [
        attr("package", strings[2]),
        attr("versionCode", "7", ns),
        attr("versionName", "1.0", ns),
    ]
    if split:
        attrs.append(attr("split", "config.en"))
    chunks = pool + node(0x100, struct.pack("<II", idx["android"], idx[ns]))
    chunks += start("manifest", attrs)
    chunks += start("uses-permission", [attr("name", strings[11], ns)])
    chunks += end("uses-permission") + end("manifest")
    chunks += node(0x101, struct.pack("<II", idx["android"], idx[ns]))
    return struct.pack("<HHI", 3, 8, len(chunks) + 8) + chunks


def dex(*, invoke=True, camera=False, provider="gps", branch=False, kind=None):
    owner = "Landroid/hardware/Camera;" if camera else "Landroid/location/LocationManager;"
    ret = "Landroid/hardware/Camera;" if camera else "Landroid/location/Location;"
    target_name = "open" if camera else "getLastKnownLocation"
    params = [] if camera else ["Ljava/lang/String;"]
    if kind == "android_id":
        owner, ret, target_name = (
            "Landroid/provider/Settings$Secure;",
            "Ljava/lang/String;",
            "getString",
        )
        params, provider = ["Landroid/content/ContentResolver;", "Ljava/lang/String;"], "android_id"
    elif kind == "imei":
        owner, ret, target_name, params = (
            "Landroid/telephony/TelephonyManager;",
            "Ljava/lang/String;",
            "getImei",
            [],
        )
    elif kind == "microphone":
        owner, ret, target_name, params = "Landroid/media/AudioRecord;", "V", "startRecording", []
    elif kind == "accessibility_screenshot":
        owner, ret, target_name = (
            "Landroid/accessibilityservice/AccessibilityService;",
            "V",
            "takeScreenshot",
        )
        params = [
            "I",
            "Ljava/util/concurrent/Executor;",
            "Landroid/accessibilityservice/AccessibilityService$TakeScreenshotCallback;",
        ]
    elif kind == "automation_screenshot":
        owner, ret, target_name, params = (
            "Landroid/app/UiAutomation;",
            "Landroid/graphics/Bitmap;",
            "takeScreenshot",
            [],
        )
    elif kind in {"contacts", "media", "arbitrary_uri"}:
        owner, ret, target_name = (
            "Landroid/content/ContentResolver;",
            "Landroid/database/Cursor;",
            "query",
        )
        params = [
            "Landroid/net/Uri;",
            "[Ljava/lang/String;",
            "Ljava/lang/String;",
            "[Ljava/lang/String;",
            "Ljava/lang/String;",
        ]
        provider = {
            "contacts": "content://com.android.contacts/contacts",
            "media": "content://media/external/images/media",
            "arbitrary_uri": "content://unknown/anything",
        }[kind]
    uri_case = kind in {"contacts", "media", "arbitrary_uri"}
    types = sorted(
        {
            "Lorg/privacytrace/fixture/Main;",
            "Ljava/lang/Object;",
            owner,
            ret,
            "Ljava/lang/String;",
            "V",
            *params,
        }
    )
    signature = owner + "->" + target_name + "(" + "".join(params) + ")" + ret
    shorty = ("V" if ret == "V" else "L") + "".join(
        "L" if p.startswith(("L", "[")) else p for p in params
    )
    strings = sorted(
        set(types + ["run", "parse", target_name, provider, "V", "L", "LL", shorty, signature])
    )
    si, ti = {s: i for i, s in enumerate(strings)}, {s: i for i, s in enumerate(types)}
    # Two protos: run()V and platform target. IDs sorted by return type.
    proto_set = {("V", ()), (ret, tuple(params))}
    if uri_case:
        proto_set.add(("Landroid/net/Uri;", ("Ljava/lang/String;",)))
    protos = sorted(proto_set, key=lambda p: (ti[p[0]], p[1]))
    pi = {(r, tuple(a)): i for i, (r, a) in enumerate(protos)}
    method_list = [
        (owner, target_name, pi[(ret, tuple(params))]),
        ("Lorg/privacytrace/fixture/Main;", "run", pi[("V", ())]),
    ]
    if uri_case:
        method_list.append(
            ("Landroid/net/Uri;", "parse", pi[("Landroid/net/Uri;", ("Ljava/lang/String;",))])
        )
    methods = sorted(
        method_list,
        key=lambda x: (ti[x[0]], si[x[1]], x[2]),
    )
    target_i = next(i for i, m in enumerate(methods) if m[1] == target_name)
    run_i = next(i for i, m in enumerate(methods) if m[1] == "run")
    string_off, type_off = 112, 112 + len(strings) * 4
    proto_off = type_off + len(types) * 4
    method_off = proto_off + len(protos) * 12
    class_off = method_off + len(methods) * 8
    data_off = class_off + 32
    data = bytearray()

    def align():
        while (data_off + len(data)) % 4:
            data.append(0)

    string_offsets = []
    for s in strings:
        string_offsets.append(data_off + len(data))
        data.extend(uleb(len(s)) + s.encode() + b"\0")
    param_offsets = []
    for _, proto_params in protos:
        if not proto_params:
            param_offsets.append(0)
            continue
        align()
        param_offsets.append(data_off + len(data))
        data.extend(struct.pack("<I", len(proto_params)))
        data.extend(struct.pack("<" + "H" * len(proto_params), *(ti[p] for p in proto_params)))
    align()
    code_off = data_off + len(data)
    words = []
    if not camera:
        words += [0x0012]  # const/4 v0, null receiver / ContentResolver argument
    if params:
        if kind == "accessibility_screenshot":
            words += [0x0112, 0x0212, 0x0312]  # int displayId 0, null executor/callback
        else:
            words += [0x011A, si[provider]]  # const-string v1, provider
    if branch:
        words += [0x0212]  # const/4 v2, zero branch condition
        words += [0x0238, 2]  # if-eqz v2, next block: constant cannot cross join
    if invoke:
        static = camera or kind == "android_id"
        count = len(params) + (0 if static else 1)
        if uri_case:
            words += [0x0212, 0x0312, 0x0412, 0x0512]  # nullable query filter arguments
            parse_i = next(i for i, m in enumerate(methods) if m[1] == "parse")
            words += [0x1071, parse_i, 1, 0x010C]  # Uri.parse(v1), move-result-object v1
            words += [0x0674, target_i, 0]  # invoke-virtual/range {v0..v5}
        else:
            words += [
                (count << 12) | (0x71 if static else 0x6E),
                target_i,
                {1: 0, 2: 0x10, 3: 0x210, 4: 0x3210}.get(count, 0),
            ]
    else:
        words += [0x001A, si[signature]]  # ordinary string, not a method invoke
    words += [0x000E]
    registers = 6 if uri_case else 4 if kind == "accessibility_screenshot" else 3
    data.extend(struct.pack("<HHHHII", registers, 0, registers, 0, 0, len(words)))
    data.extend(struct.pack("<" + "H" * len(words), *words))
    class_data_off = data_off + len(data)
    data.extend(bytes([0, 0, 1, 0]) + uleb(run_i) + uleb(9) + uleb(code_off))
    align()
    map_off = data_off + len(data)
    maps = [
        (0, 1, 0),
        (1, len(strings), string_off),
        (2, len(types), type_off),
        (3, len(protos), proto_off),
        (5, len(methods), method_off),
        (6, 1, class_off),
        (0x2002, len(strings), data_off),
        (0x2001, 1, code_off),
        (0x2000, 1, class_data_off),
        (0x1000, 1, map_off),
    ]
    if any(param_offsets):
        maps.append(
            (0x1001, sum(bool(x) for x in param_offsets), min(x for x in param_offsets if x))
        )
    maps.sort(key=lambda m: m[2])
    data.extend(struct.pack("<I", len(maps)))
    for kind, count, offset in maps:
        data.extend(struct.pack("<HHII", kind, 0, count, offset))
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
        len(protos),
        proto_off,
        0,
        0,
        len(methods),
        method_off,
        1,
        class_off,
        len(data),
        data_off,
    )
    body = struct.pack("<" + "I" * len(strings), *string_offsets)
    body += struct.pack("<" + "I" * len(types), *(si[t] for t in types))
    for (ret_type, params), offset in zip(protos, param_offsets):
        proto_shorty = ("V" if ret_type == "V" else "L") + "".join(
            "L" if p.startswith(("L", "[")) else p for p in params
        )
        body += struct.pack("<III", si[proto_shorty], ti[ret_type], offset)
    for cls, name, proto in methods:
        body += struct.pack("<HHI", ti[cls], proto, si[name])
    body += struct.pack(
        "<8I",
        ti["Lorg/privacytrace/fixture/Main;"],
        1,
        ti["Ljava/lang/Object;"],
        0,
        0xFFFFFFFF,
        0,
        class_data_off,
        0,
    )
    result = bytearray(header + body + data)
    result[12:32] = hashlib.sha1(result[32:]).digest()
    result[8:12] = struct.pack("<I", zlib.adler32(result[12:]))
    return bytes(result)


def apk(
    path: Path, *, entries=None, split=False, permission="android.permission.CAMERA", **dex_options
):
    if entries is None:
        entries = {"classes.dex": dex(**dex_options)}
    with ZipFile(path, "w", compression=ZIP_STORED) as archive:
        for name, payload in {
            "AndroidManifest.xml": manifest(split, permission),
            **entries,
        }.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            archive.writestr(info, payload)
    return path
