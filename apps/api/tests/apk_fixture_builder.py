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


def manifest(
    split=False,
    permission="android.permission.CAMERA",
    sdk_23_permission=None,
    version_code="7",
    version_name="1.0",
    permission_parent=None,
    sdk_23_parent=None,
    permission_namespace="http://schemas.android.com/apk/res/android",
    permission_tag_namespace=None,
    version_code_type=None,
    permission_tag="uses-permission",
    max_sdk=None,
    sdk_23_max_sdk=None,
):
    raw_strings = [
        "manifest",
        "package",
        "org.privacytrace.fixture",
        "versionCode",
        str(version_code),
        "http://schemas.android.com/apk/res/android",
        "android",
        permission_tag,
        "name",
        permission,
        "split",
        "config.en",
    ]
    if version_name is not None:
        raw_strings.extend(["versionName", str(version_name)])
    if sdk_23_permission is not None:
        raw_strings.extend(["uses-permission-sdk-23", str(sdk_23_permission)])
    for bound in (max_sdk, sdk_23_max_sdk):
        if bound is not None:
            raw_strings.extend(["maxSdkVersion", str(bound)])
    raw_strings.extend(
        value
        for value in (
            permission_parent,
            sdk_23_parent,
            permission_namespace,
            permission_tag_namespace,
        )
        if value is not None
    )

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

    def attr(name, value, ns=None):
        if name == "versionCode" and version_code_type is not None:
            return struct.pack(
                "<IIIHBBI", idx[ns], idx[name], 0xFFFFFFFF, 8, 0, version_code_type,
                int(value, 16 if value.lower().startswith("0x") else 10)
            )
        return struct.pack(
            "<IIIHBBI", idx[ns] if ns else 0xFFFFFFFF, idx[name], idx[value], 8, 0, 3, idx[value]
        )

    def start(name, attrs, tag_ns=None):
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

    def end(name, tag_ns=None):
        return node(0x103, struct.pack("<II", idx[tag_ns] if tag_ns else 0xFFFFFFFF, idx[name]))

    ns = "http://schemas.android.com/apk/res/android"
    attrs = [
        attr("package", "org.privacytrace.fixture"),
        attr("versionCode", str(version_code), ns),
    ]
    if version_name is not None:
        attrs.append(attr("versionName", str(version_name), ns))
    if split:
        attrs.append(attr("split", "config.en"))
    chunks = pool + node(0x100, struct.pack("<II", idx["android"], idx[ns]))
    chunks += start("manifest", attrs)
    for tag, value, parent, bound in (
        (permission_tag, permission, permission_parent, max_sdk),
        ("uses-permission-sdk-23", sdk_23_permission, sdk_23_parent, sdk_23_max_sdk),
    ):
        if value is None:
            continue
        if parent is not None:
            chunks += start(parent, [])
        permission_attrs = [attr("name", str(value), permission_namespace)]
        if bound is not None:
            permission_attrs.append(attr("maxSdkVersion", str(bound), permission_namespace))
        chunks += start(tag, permission_attrs, permission_tag_namespace)
        chunks += end(tag, permission_tag_namespace)
        if parent is not None:
            chunks += end(parent)
    chunks += end("manifest")
    chunks += node(0x101, struct.pack("<II", idx["android"], idx[ns]))
    return struct.pack("<HHI", 3, 8, len(chunks) + 8) + chunks


def dex(*, invoke=True, camera=False, provider="gps", branch=False, kind=None, invoke_count=1):
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
    elif kind in {"contacts", "media", "arbitrary_uri", "sget_contacts", "sget_media"}:
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
            "sget_contacts": "",
            "sget_media": "",
        }[kind]
    fields = []
    if kind == "sget_contacts":
        fields = [
            (
                "Landroid/provider/ContactsContract$Contacts;",
                "Landroid/net/Uri;",
                "CONTENT_URI",
            )
        ]
    elif kind == "sget_media":
        fields = [
            (
                "Landroid/provider/MediaStore$Images$Media;",
                "Landroid/net/Uri;",
                "EXTERNAL_CONTENT_URI",
            )
        ]
    sget_case = bool(fields)
    uri_case = kind in {"contacts", "media", "arbitrary_uri"}
    type_set = {
        "Lorg/privacytrace/fixture/Main;",
        "Ljava/lang/Object;",
        owner,
        ret,
        "Ljava/lang/String;",
        "V",
        *params,
    }
    for f_cls, f_type, _ in fields:
        type_set.add(f_cls)
        type_set.add(f_type)
    types = sorted(type_set)
    signature = owner + "->" + target_name + "(" + "".join(params) + ")" + ret
    shorty = ("V" if ret == "V" else "L") + "".join(
        "L" if p.startswith(("L", "[")) else p for p in params
    )
    extra_items = ["run", "parse", target_name, provider, "V", "L", "LL", shorty, signature]
    string_set = set(types + extra_items)
    for _, _, f_name in fields:
        string_set.add(f_name)
    strings = sorted(string_set)
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
    field_off = proto_off + len(protos) * 12
    method_off = field_off + len(fields) * 8
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
    if sget_case:
        words += [0x0012]  # const/4 v0, null receiver / ContentResolver argument
        words += [(1 << 8) | 0x62, 0]  # sget-object v1, field@0
        if branch:
            words += [0x0212]  # const/4 v2, zero branch condition
            words += [0x0238, 2]  # if-eqz v2, next block: constant cannot cross join
        words += [0x0212, 0x0312, 0x0412, 0x0512]  # nullable query filter arguments
        words += [0x0674, target_i, 0]  # invoke-virtual/range {v0..v5}
        words += [0x000E]
    else:
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
                ] * invoke_count
        else:
            words += [0x001A, si[signature]]  # ordinary string, not a method invoke
        words += [0x000E]
    registers = 6 if (uri_case or sget_case) else 4 if kind == "accessibility_screenshot" else 3
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
    if fields:
        maps.append((4, len(fields), field_off))
    if any(param_offsets):
        maps.append(
            (0x1001, sum(bool(x) for x in param_offsets), min(x for x in param_offsets if x))
        )
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
        len(protos),
        proto_off,
        len(fields),
        field_off if fields else 0,
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
    for cls, f_type, name in fields:
        body += struct.pack("<HHI", ti[cls], ti[f_type], si[name])
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
    path: Path,
    *,
    entries=None,
    split=False,
    permission="android.permission.CAMERA",
    sdk_23_permission=None,
    version_code="7",
    version_name="1.0",
    manifest_options=None,
    **dex_options,
):
    if entries is None:
        entries = {"classes.dex": dex(**dex_options)}
    options = dict(split=split, permission=permission, sdk_23_permission=sdk_23_permission,
                   version_code=version_code, version_name=version_name)
    options.update(manifest_options or {})
    with ZipFile(path, "w", compression=ZIP_STORED) as archive:
        for name, payload in {
            "AndroidManifest.xml": manifest(**options),
            **entries,
        }.items():
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            archive.writestr(info, payload)
    return path
