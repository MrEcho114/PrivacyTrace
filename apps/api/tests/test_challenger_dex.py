import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest
from apk_fixture_builder import apk, uleb

from privacytrace.apk_worker import scan


def build_custom_dex(
    fields=None,
    words_builder=None,
    registers=6,
):
    """
    Builds a valid Dalvik DEX file containing ContentResolver.query
    and specified fields/instructions.
    """
    if fields is None:
        fields = []

    owner = "Landroid/content/ContentResolver;"
    ret = "Landroid/database/Cursor;"
    target_name = "query"
    params = [
        "Landroid/net/Uri;",
        "[Ljava/lang/String;",
        "Ljava/lang/String;",
        "[Ljava/lang/String;",
        "Ljava/lang/String;",
    ]

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
    extra_items = ["run", "parse", target_name, "", "V", "L", "LL", shorty, signature]
    for _, _, f_name in fields:
        extra_items.append(f_name)

    strings = sorted(set(types + extra_items))
    si, ti = {s: i for i, s in enumerate(strings)}, {s: i for i, s in enumerate(types)}

    # Protos
    protos = sorted({("V", ()), (ret, tuple(params))}, key=lambda p: (ti[p[0]], p[1]))
    pi = {(r, tuple(a)): i for i, (r, a) in enumerate(protos)}

    # Methods
    methods = sorted(
        [
            (owner, target_name, pi[(ret, tuple(params))]),
            ("Lorg/privacytrace/fixture/Main;", "run", pi[("V", ())]),
        ],
        key=lambda x: (ti[x[0]], si[x[1]], x[2]),
    )
    target_i = next(i for i, m in enumerate(methods) if m[1] == target_name)
    run_i = next(i for i, m in enumerate(methods) if m[1] == "run")

    # Fields sorted by (class_idx, type_idx, name_idx) per Dalvik spec
    sorted_fields = sorted(fields, key=lambda f: (ti[f[0]], ti[f[1]], si[f[2]]))
    field_to_idx = {f: i for i, f in enumerate(sorted_fields)}

    string_off, type_off = 112, 112 + len(strings) * 4
    proto_off = type_off + len(types) * 4
    field_off = proto_off + len(protos) * 12
    method_off = field_off + len(sorted_fields) * 8
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

    if words_builder is not None:
        words = words_builder(target_i, field_to_idx)
    else:
        words = [0x000E]  # return-void

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
    if sorted_fields:
        maps.append((4, len(sorted_fields), field_off))
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
        len(sorted_fields),
        field_off if sorted_fields else 0,
        len(methods),
        method_off,
        1,
        class_off,
        len(data),
        data_off,
    )
    body = struct.pack("<" + "I" * len(strings), *string_offsets)
    body += struct.pack("<" + "I" * len(types), *(si[t] for t in types))
    for (ret_type, p_types), offset in zip(protos, param_offsets):
        proto_shorty = ("V" if ret_type == "V" else "L") + "".join(
            "L" if p.startswith(("L", "[")) else p for p in p_types
        )
        body += struct.pack("<III", si[proto_shorty], ti[ret_type], offset)
    for cls, f_type, name in sorted_fields:
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


@pytest.fixture
def rules():
    return json.loads(Path("rules/taxonomy.v0.3.json").read_text(encoding="utf-8"))


# --- Test 1: Flow / Branch instructions invalidate constants ---


def test_sget_object_with_if_branch_invalidates_constant(tmp_path, rules):
    # sget-object followed by if-eqz branch: has_flow must be True and invalidate constant
    fields = [("Landroid/provider/ContactsContract$Contacts;", "Landroid/net/Uri;", "CONTENT_URI")]

    def builder(target_i, field_idx_map):
        f_idx = field_idx_map[fields[0]]
        return [
            0x0012,  # const/4 v0, 0
            (1 << 8) | 0x62,
            f_idx,  # sget-object v1, Contacts.CONTENT_URI
            0x0212,  # const/4 v2, 0
            0x0238,
            2,  # if-eqz v2, +2
            0x0212,
            0x0312,
            0x0412,
            0x0512,  # const/4 v2..v5
            0x0674,
            target_i,
            0,  # invoke-virtual/range {v0..v5}
            0x000E,  # return-void
        ]

    dex_bytes = build_custom_dex(fields=fields, words_builder=builder)
    p = tmp_path / "sget_if.apk"
    apk(p, entries={"classes.dex": dex_bytes})
    res = scan(p, rules)
    # No CONTACTS behavior should be emitted because has_flow invalidated the constant
    assert not any(b["data_type"] == "CONTACTS" for b in res["behaviors"])
    assert not any(e["kind"] == "API" for e in res["evidence"])


def test_sget_object_with_goto_invalidates_constant(tmp_path, rules):
    # sget-object followed by goto: has_flow must be True and invalidate constant
    fields = [("Landroid/provider/ContactsContract$Contacts;", "Landroid/net/Uri;", "CONTENT_URI")]

    def builder(target_i, field_idx_map):
        f_idx = field_idx_map[fields[0]]
        return [
            0x0012,  # const/4 v0, 0
            (1 << 8) | 0x62,
            f_idx,  # sget-object v1, Contacts.CONTENT_URI
            0x0128,  # goto +1
            0x0212,
            0x0312,
            0x0412,
            0x0512,  # const/4 v2..v5
            0x0674,
            target_i,
            0,  # invoke-virtual/range {v0..v5}
            0x000E,  # return-void
        ]

    dex_bytes = build_custom_dex(fields=fields, words_builder=builder)
    p = tmp_path / "sget_goto.apk"
    apk(p, entries={"classes.dex": dex_bytes})
    res = scan(p, rules)
    assert not any(b["data_type"] == "CONTACTS" for b in res["behaviors"])


# --- Test 2: Non-framework fields do NOT resolve ---


def test_sget_object_non_framework_field(tmp_path, rules):
    fields = [("Lcom/custom/Provider;", "Landroid/net/Uri;", "MY_URI")]

    def builder(target_i, field_idx_map):
        f_idx = field_idx_map[fields[0]]
        return [
            0x0012,  # const/4 v0, 0
            (1 << 8) | 0x62,
            f_idx,  # sget-object v1, MY_URI
            0x0212,
            0x0312,
            0x0412,
            0x0512,  # const/4 v2..v5
            0x0674,
            target_i,
            0,  # invoke-virtual/range {v0..v5}
            0x000E,  # return-void
        ]

    dex_bytes = build_custom_dex(fields=fields, words_builder=builder)
    p = tmp_path / "sget_non_framework.apk"
    apk(p, entries={"classes.dex": dex_bytes})
    res = scan(p, rules)
    # Neither CONTACTS nor FILES_MEDIA should be emitted
    assert not any(b["data_type"] in {"CONTACTS", "FILES_MEDIA"} for b in res["behaviors"])
    assert not any(e["kind"] == "API" for e in res["evidence"])


# --- Test 3: Multiple consecutive sget-object instructions ---


def test_sget_object_consecutive_overwrite_replaces_constant(tmp_path, rules):
    # sget-object v1, Contacts.CONTENT_URI
    # sget-object v1, MediaStore.Images.Media.EXTERNAL_CONTENT_URI (overwrites v1!)
    # invoke query(v1) -> must match FILES_MEDIA, NOT CONTACTS
    f_contacts = (
        "Landroid/provider/ContactsContract$Contacts;",
        "Landroid/net/Uri;",
        "CONTENT_URI",
    )
    f_media = (
        "Landroid/provider/MediaStore$Images$Media;",
        "Landroid/net/Uri;",
        "EXTERNAL_CONTENT_URI",
    )
    fields = [f_contacts, f_media]

    def builder(target_i, field_idx_map):
        idx_c = field_idx_map[f_contacts]
        idx_m = field_idx_map[f_media]
        return [
            0x0012,  # const/4 v0, 0
            (1 << 8) | 0x62,
            idx_c,  # sget-object v1, Contacts
            (1 << 8) | 0x62,
            idx_m,  # sget-object v1, Media (overwrites v1!)
            0x0212,
            0x0312,
            0x0412,
            0x0512,  # const/4 v2..v5
            0x0674,
            target_i,
            0,  # invoke-virtual/range {v0..v5}
            0x000E,  # return-void
        ]

    dex_bytes = build_custom_dex(fields=fields, words_builder=builder)
    p = tmp_path / "sget_overwrite.apk"
    apk(p, entries={"classes.dex": dex_bytes})
    res = scan(p, rules)
    behaviors = [b["data_type"] for b in res["behaviors"]]
    assert "FILES_MEDIA" in behaviors
    assert "CONTACTS" not in behaviors
    api_ev = next(e for e in res["evidence"] if e["kind"] == "API")
    assert api_ev["api_call"]["context"]["uri"] == "content://media/external/images/media"


def test_sget_object_overwrite_with_non_framework_field_clears_constant(tmp_path, rules):
    # sget-object v1, Contacts.CONTENT_URI
    # sget-object v1, Custom.MY_URI (overwrites v1 with non-framework!)
    # invoke query(v1) -> constants.pop(v1) should clear v1; must match NOTHING
    f_contacts = (
        "Landroid/provider/ContactsContract$Contacts;",
        "Landroid/net/Uri;",
        "CONTENT_URI",
    )
    f_custom = ("Lcom/custom/Provider;", "Landroid/net/Uri;", "MY_URI")
    fields = [f_contacts, f_custom]

    def builder(target_i, field_idx_map):
        idx_c = field_idx_map[f_contacts]
        idx_custom = field_idx_map[f_custom]
        return [
            0x0012,  # const/4 v0, 0
            (1 << 8) | 0x62,
            idx_c,  # sget-object v1, Contacts
            (1 << 8) | 0x62,
            idx_custom,  # sget-object v1, Custom (clears v1!)
            0x0212,
            0x0312,
            0x0412,
            0x0512,  # const/4 v2..v5
            0x0674,
            target_i,
            0,  # invoke-virtual/range {v0..v5}
            0x000E,  # return-void
        ]

    dex_bytes = build_custom_dex(fields=fields, words_builder=builder)
    p = tmp_path / "sget_cleared.apk"
    apk(p, entries={"classes.dex": dex_bytes})
    res = scan(p, rules)
    assert not any(b["data_type"] in {"CONTACTS", "FILES_MEDIA"} for b in res["behaviors"])
    assert not any(e["kind"] == "API" for e in res["evidence"])


def test_sget_object_multiple_distinct_registers_both_resolve(tmp_path, rules):
    # sget-object v1, Contacts
    # sget-object v2, Media
    # query(v1) -> matches CONTACTS
    # query(v2) -> matches FILES_MEDIA
    f_contacts = (
        "Landroid/provider/ContactsContract$Contacts;",
        "Landroid/net/Uri;",
        "CONTENT_URI",
    )
    f_media = (
        "Landroid/provider/MediaStore$Images$Media;",
        "Landroid/net/Uri;",
        "EXTERNAL_CONTENT_URI",
    )
    fields = [f_contacts, f_media]

    def builder(target_i, field_idx_map):
        idx_c = field_idx_map[f_contacts]
        idx_m = field_idx_map[f_media]
        return [
            0x0012,  # const/4 v0, 0
            (1 << 8) | 0x62,
            idx_c,  # sget-object v1, Contacts
            (2 << 8) | 0x62,
            idx_m,  # sget-object v2, Media
            0x0312,
            0x0412,
            0x0512,
            0x0612,  # const/4 v3..v6 (unused dummy args)
            # 1. query with v1: range {v0..v5} (where v1 is contacts)
            0x0674,
            target_i,
            0,
            # Move v2 to v1 with media (0x2107: move-object v1, v2)
            0x2107,  # move-object v1, v2
            # 2. query with v1 (now media): range {v0..v5}
            0x0674,
            target_i,
            0,
            0x000E,  # return-void
        ]

    dex_bytes = build_custom_dex(fields=fields, words_builder=builder, registers=7)
    p = tmp_path / "sget_both.apk"
    apk(p, entries={"classes.dex": dex_bytes})
    res = scan(p, rules)
    behaviors = [b["data_type"] for b in res["behaviors"]]
    assert "CONTACTS" in behaviors
    assert "FILES_MEDIA" in behaviors
    api_evs = [e for e in res["evidence"] if e["kind"] == "API"]
    assert len(api_evs) == 2
    uris = {e["api_call"]["context"]["uri"] for e in api_evs}
    assert uris == {
        "content://com.android.contacts/contacts",
        "content://media/external/images/media",
    }


# --- Test 4: ContentResolver.query with unresolvable or dynamic URIs ---


def test_query_with_unresolvable_uri(tmp_path, rules):
    # const/4 v1, 0 (null uri passed to query)
    def builder(target_i, field_idx_map):
        return [
            0x0012,  # const/4 v0, 0
            0x0112,  # const/4 v1, 0 (unresolvable null URI)
            0x0212,
            0x0312,
            0x0412,
            0x0512,  # const/4 v2..v5
            0x0674,
            target_i,
            0,  # invoke-virtual/range {v0..v5}
            0x000E,  # return-void
        ]

    dex_bytes = build_custom_dex(fields=[], words_builder=builder)
    p = tmp_path / "query_null.apk"
    apk(p, entries={"classes.dex": dex_bytes})
    res = scan(p, rules)
    assert not any(b["data_type"] in {"CONTACTS", "FILES_MEDIA"} for b in res["behaviors"])
    assert not any(e["kind"] == "API" for e in res["evidence"])
