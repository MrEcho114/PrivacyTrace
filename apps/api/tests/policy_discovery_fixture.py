"""Unsigned synthetic APKs with actual binary AXML and resources.arsc tables.

The minimal ResTable chunks are consumed by the production Androguard parser;
no parser doubles, SDK downloads or committed APK binaries are required.
"""

import struct
from zipfile import ZIP_STORED, ZipFile

from test_e2e_pt_mob_102 import build_axml_manifest


def _string_pool(strings):
    data, offsets = bytearray(), []
    for value in strings:
        offsets.append(len(data))
        encoded = value.encode("utf-16le")
        data.extend(struct.pack("<H", len(encoded) // 2) + encoded + b"\0\0")
    data.extend(b"\0" * (-len(data) % 4))
    start = 28 + 4 * len(strings)
    return (
        struct.pack("<HHIIIIII", 1, 28, start + len(data), len(strings), 0, 0, start, 0)
        + b"".join(struct.pack("<I", offset) for offset in offsets) + data
    )


def resource_table(values, localized=None):
    """String resource IDs are 0x7f010000 + index; integer values are aliases."""
    keys = list(values)
    configurations = [("", values), *((localized or {}).items())]
    strings = list(dict.fromkeys(
        value for _, config in configurations for value in config.values()
        if isinstance(value, str)
    ))
    types, names = _string_pool(["string"]), _string_pool(keys)
    spec = struct.pack("<HHIBBHI", 0x202, 16, 16 + 4 * len(keys), 1, 0, 0, len(keys))
    spec += b"\0" * (4 * len(keys))
    chunks = types + names + spec
    for language, config_values in configurations:
        # ResTable_config (64 bytes): mcc/mnc, language/country, then defaults.
        config = struct.pack("<II", 64, 0) + language.encode().ljust(4, b"\0") + b"\0" * 52
        entries, offsets = b"", []
        for index, key in enumerate(keys):
            if key not in config_values:
                offsets.append(0xFFFFFFFF)
                continue
            value = config_values[key]
            offsets.append(len(entries))
            kind, data = (1, value) if isinstance(value, int) else (3, strings.index(value))
            entries += struct.pack("<HHIHBBI", 8, 0, index, 8, 0, kind, data)
        header_size = 20 + len(config)
        start = header_size + 4 * len(keys)
        chunks += (
            struct.pack("<HHIBB HII", 0x201, header_size, start + len(entries),
                        1, 0, 0, len(keys), start)
            + config + b"".join(struct.pack("<I", offset) for offset in offsets) + entries
        )
    package = struct.pack(
        "<HHII256sIIIII", 0x200, 288, 288 + len(chunks), 0x7F,
        "org.privacytrace.fixture".encode("utf-16le"), 288, 1, 288 + len(types), len(keys), 0
    ) + chunks
    contents = _string_pool(strings) + package
    return struct.pack("<HHII", 2, 12, 12 + len(contents), 1) + contents


def policy_resource_apk(path, *, attribute="value", reference=0x7F010000, values=None,
                        localized=None, split=None):
    manifest = build_axml_manifest(
        split_name=split, meta_data={"privacy_policy": reference}, meta_data_attribute=attribute
    )
    with ZipFile(path, "w", compression=ZIP_STORED) as archive:
        archive.writestr("AndroidManifest.xml", manifest)
        if values is not None:
            archive.writestr("resources.arsc", resource_table(values, localized))
    return path
