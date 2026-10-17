"""Untrusted-input static worker. Run real APKs only inside the isolated runner.

stdout is one deterministic JSON result; diagnostic parser output stays on stderr.
APK bytes are never executed. ZIP entries are validated and read without extraction.
"""

import argparse
import contextlib
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

from .coverage_scope import behavior_limitations

MAX_APK = 150 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_ENTRY = 128 * 1024 * 1024
MAX_ENTRIES = 20000

# Cap on how many SDK attribution *classes* one scan emits. A Dex can reference
# far more classes than a report can sensibly list; truncation is reported in
# `coverage.sdk_attribution_limitations`, never silently dropped.
MAX_SDK_ATTRIBUTIONS = 500

# Guard rails on the SDK evidence budget. At most one guaranteed representative
# per signature, so a hostile APK cannot inflate the floor past the cap; at least
# one guaranteed representative per signature, so the cap can never empty it.
MAX_SDK_REPRESENTATIVES = min(MAX_SDK_ATTRIBUTIONS, 100)
MIN_SDK_REPRESENTATIVES = 1

FRAMEWORK_STATIC_URIS = {
    (
        "Landroid/provider/ContactsContract$Contacts;",
        "CONTENT_URI",
    ): "content://com.android.contacts/contacts",
    (
        "Landroid/provider/MediaStore$Images$Media;",
        "EXTERNAL_CONTENT_URI",
    ): "content://media/external/images/media",
    (
        "Landroid/provider/MediaStore$Images$Media;",
        "INTERNAL_CONTENT_URI",
    ): "content://media/internal/images/media",
    (
        "Landroid/provider/MediaStore$Video$Media;",
        "EXTERNAL_CONTENT_URI",
    ): "content://media/external/video/media",
    (
        "Landroid/provider/MediaStore$Video$Media;",
        "INTERNAL_CONTENT_URI",
    ): "content://media/internal/video/media",
    (
        "Landroid/provider/MediaStore$Audio$Media;",
        "EXTERNAL_CONTENT_URI",
    ): "content://media/external/audio/media",
    (
        "Landroid/provider/MediaStore$Audio$Media;",
        "INTERNAL_CONTENT_URI",
    ): "content://media/internal/audio/media",
}


class ScanError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def checked_entries(path):
    if path.stat().st_size > MAX_APK:
        raise ScanError("APK_SIZE_LIMIT", "APK exceeds 150 MiB limit")
    archive = ZipFile(path)
    try:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES:
            raise ScanError("ZIP_ENTRY_LIMIT", "Too many ZIP entries")
        seen, total = set(), 0
        for entry in entries:
            name = entry.filename
            if (
                name in seen
                or "\\" in entry.orig_filename
                or name.startswith("/")
                or ":" in name
                or ".." in PurePosixPath(name).parts
                or stat.S_ISLNK(entry.external_attr >> 16)
            ):
                raise ScanError("UNSAFE_ZIP", "Duplicate, escaping, or symbolic ZIP entry")
            seen.add(name)
            total += entry.file_size
            if (
                entry.file_size > MAX_ENTRY
                or total > MAX_EXPANDED
                or entry.file_size > max(1, entry.compress_size) * 200
            ):
                raise ScanError(
                    "ZIP_SIZE_LIMIT", "Expanded size or compression ratio exceeds limit"
                )
            if entry.flag_bits & 1:
                raise ScanError("ENCRYPTED_ZIP", "Encrypted ZIP entries are unsupported")
        # Streaming CRC verification, including entries not consumed by the parsers.
        for entry in entries:
            with archive.open(entry) as stream:
                while stream.read(1024 * 1024):
                    pass
        return archive
    except Exception:
        archive.close()
        raise


def empty_result():
    return dict(
        apk_sha256=None,
        package_name=None,
        version_code=None,
        version_name=None,
        permissions=[],
        dex_entries=[],
        coverage=dict(
            completeness="PARTIAL",
            scope="DEX_ENTRIES",
            behavior_detection="LIMITED_RULE_BASED_STATIC",
            behavior_limitations=behavior_limitations(),
            sdk_attribution_limitations=[],
            scanned_dex=[],
            failed_dex=[],
            limitations=[],
        ),
        tools={},
        evidence=[],
        behaviors=[],
        errors=[],
    )


def isolation_probe(path):
    """Trusted-fixture-only runtime inspection; never parses APK or opens sockets."""
    result = empty_result()
    result["apk_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    probe = {
        "uid": os.getuid() if hasattr(os, "getuid") else None,
        "interfaces": sorted(p.name for p in Path("/sys/class/net").iterdir()),
        "home": os.environ.get("HOME"),
        "input_write_denied": False,
        "root_write_denied": False,
    }
    for key, target, flags in [
        ("input_write_denied", path, os.O_WRONLY | os.O_APPEND),
        ("root_write_denied", Path("/app/probe-write"), os.O_WRONLY | os.O_CREAT | os.O_EXCL),
    ]:
        try:
            descriptor = os.open(target, flags, 0o600)
            os.close(descriptor)
            if key == "root_write_denied":
                target.unlink()  # Own zero-byte probe only; never remove inherited files.
        except OSError as exc:
            probe[key] = True
            probe[key + "_errno"] = exc.errno
    for name in ["memory.max", "cpu.max", "pids.max"]:
        probe[name] = (Path("/sys/fs/cgroup") / name).read_text().strip()
    status = Path("/proc/self/status").read_text().splitlines()
    for key in ["NoNewPrivs", "CapEff"]:
        probe[key] = next(
            line.split(":", 1)[1].strip() for line in status if line.startswith(key + ":")
        )
    result["tools"]["isolation_probe"] = json.dumps(probe, sort_keys=True)
    return result


def scan(
    path,
    rules,
    inventory=False,
    sdk_rules=None,
    package_split=None,
    behavior_count=0,
    is_split: bool = False,
):
    from androguard.core.apk import APK
    from androguard.core.dex import DEX, Operand
    from loguru import logger

    from .sdk_attribution import SdkAttributionCollector, load_index

    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    result = empty_result()
    if is_split:
        # Defense-in-depth: Splits are ALWAYS prefixed with f"split:{split_name}:" and never "base:"
        # Semicolons are sanitized to prevent locator key-value injection.
        s_name = (package_split or "unknown").replace(";", "_")
        split_prefix = f";split={s_name}"
        source_prefix = f"split:{s_name}:"
        recorded_split = s_name
    elif package_split == "base":
        split_prefix = ";split=base"
        source_prefix = "base:"
        recorded_split = "base"
    elif package_split:
        s_name = str(package_split).replace(";", "_")
        split_prefix = f";split={s_name}"
        source_prefix = f"split:{s_name}:"
        recorded_split = s_name
    else:
        split_prefix = ""
        source_prefix = ""
        recorded_split = None
    inventory_calls = []
    inventory_truncated = False
    sdk_index = load_index(sdk_rules) if sdk_rules else None
    # Matches go straight into a bounded collector rather than a growing dict: the
    # number of matching classes is attacker-controlled, so holding them all would
    # let one APK drive unbounded memory.
    sdk_collector = (
        SdkAttributionCollector(
            MAX_SDK_ATTRIBUTIONS, MIN_SDK_REPRESENTATIVES, MAX_SDK_REPRESENTATIVES
        )
        if sdk_index is not None
        else None
    )
    result["tools"] = {
        "androguard": importlib.metadata.version("androguard"),
        "ruleset": rules["version"],
    }
    if sdk_index is not None:
        result["tools"]["sdk_signatures"] = sdk_index.version
    with checked_entries(path) as archive:
        result["apk_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if "AndroidManifest.xml" not in archive.namelist():
            raise ScanError("MANIFEST_MISSING", "AndroidManifest.xml is required")
        apk = APK(str(path))
        if not apk.is_valid_APK() or apk.get_android_manifest_xml() is None:
            raise ScanError("MANIFEST_INVALID", "Binary Android manifest could not be parsed")
        raw_code = apk.get_androidversion_code()
        if raw_code is None:
            raise ScanError("MANIFEST_INVALID", "Manifest versionCode must be an integer")
        try:
            if isinstance(raw_code, str):
                raw_code = raw_code.strip()
                version_code = int(raw_code, 16 if raw_code.lower().startswith("0x") else 10)
            else:
                version_code = int(raw_code)
            # Support the nonnegative range of Android's signed 32-bit field.
            # TYPE_INT_HEX must not turn negative bit patterns into large positives.
            if not 0 <= version_code <= 0x7fffffff:
                raise ValueError("versionCode outside supported signed 32-bit range")
        except (TypeError, ValueError) as exc:
            raise ScanError(
                "MANIFEST_INVALID", "Manifest versionCode must be an integer in 0..2147483647"
            ) from exc

        declarations = set()
        android_ns = "{http://schemas.android.com/apk/res/android}"
        manifest_xml = apk.get_android_manifest_xml()
        if manifest_xml is not None and manifest_xml.tag == "manifest":
            # Permission declarations belong directly to <manifest>, not arbitrary
            # descendants. Preserve each tag/SDK condition, not just its name.
            for element in manifest_xml:
                if element.tag in ("uses-permission", "uses-permission-sdk-23"):
                    name = element.get(android_ns + "name")
                    if isinstance(name, str) and name.strip():
                        max_sdk = element.get(android_ns + "maxSdkVersion", "").strip()
                        declarations.add((name.strip(), element.tag, max_sdk))

        raw_version_name = apk.get_androidversion_name()
        version_name = raw_version_name[:1024] if isinstance(raw_version_name, str) else None

        result.update(
            package_name=apk.get_package(),
            version_code=version_code,
            version_name=version_name,
            permissions=sorted({name for name, _, _ in declarations}),
        )
        if not result["package_name"]:
            raise ScanError("MANIFEST_INVALID", "Manifest package is missing")
        result["coverage"]["limitations"] = [
            "Static potential only; runtime access, reflection, native code, dynamic loading, "
            "and interprocedural argument resolution are not proven."
        ]

        def add(kind, source, locator, excerpt, data_type, action="ACCESS", api_call=None):
            if behavior_count + len(result["behaviors"]) >= 500:
                warning = (
                    "Mapped behavior/evidence output truncated at 500; additional hits omitted. "
                    "DEX processing completion does not imply complete behavior coverage."
                )
                if warning not in result["coverage"]["behavior_limitations"]:
                    result["coverage"]["behavior_limitations"].append(warning)
                return
            identity = hashlib.sha256((kind + locator).encode()).hexdigest()[:24]
            evidence = dict(
                id="ev-" + identity,
                kind=kind,
                status="STATIC_POTENTIAL",
                source=source,
                locator=locator,
                excerpt=excerpt,
            )
            if recorded_split is not None:
                evidence["package_split"] = recorded_split
            if api_call:
                evidence["api_call"] = api_call
            result["evidence"].append(evidence)
            result["behaviors"].append(
                dict(
                    id="behavior-" + identity,
                    data_type=data_type,
                    action=action,
                    purpose="UNKNOWN",
                    recipient="UNKNOWN",
                    transfer="UNKNOWN",
                    temporal_scope="UNKNOWN",
                    evidence_ids=[evidence["id"]],
                    contextual_hints=[],
                )
            )

        for mapping in rules["permission_mappings"]:
            for permission, tag, max_sdk in sorted(declarations):
                if permission != mapping["permission"]:
                    continue
                bounds = ";tag=" + tag
                if tag == "uses-permission-sdk-23":
                    bounds += ";min_sdk=23"
                if max_sdk:
                    bounds += ";max_sdk=" + max_sdk
                add(
                    "MANIFEST",
                    f"{source_prefix}AndroidManifest.xml",
                    f"apk_sha256={result['apk_sha256']}{split_prefix};permission={permission}{bounds}",
                    permission + bounds,
                    mapping["data_type"],
                    "CAPABILITY",
                )
        names = sorted(n for n in archive.namelist() if re.fullmatch(r"classes(?:[0-9]+)?\.dex", n))
        result["dex_entries"] = [f"{source_prefix}{n}" for n in names]
        if "classes.dex" not in names:
            result["coverage"]["limitations"].append(
                "Primary classes.dex missing; split or incomplete APK"
            )
        if package_split is None and apk.get_android_manifest_xml().get("split"):
            result["coverage"]["limitations"].append(
                "Split manifest; other package splits unavailable"
            )
        for name in names:
            try:
                vm = DEX(archive.read(name))
                for cls in vm.get_classes():
                    # PT-401: attribute a class to a published vendor package range.
                    # This records a reference label only. It creates no behavior,
                    # because an SDK's static presence is not a collection event.
                    # The collector keeps memory bounded and preserves one
                    # representative per SDK, so a large SDK cannot crowd out
                    # another one from the capped report.
                    if sdk_collector is not None:
                        found = sdk_index.match_descriptor_with_prefix(cls.get_name())
                        if found is not None:
                            sdk_collector.add(replace(found, dex=name))
                    for method in cls.get_methods():
                        caller = (
                            method.get_class_name()
                            + "->"
                            + method.get_name()
                            + method.get_descriptor().replace(" ", "")
                        )
                        instructions = list(method.get_instructions_idx())
                        # Any branch/try means no constant argument claims in this method.
                        # Conservative safe fallback avoids false cross-block propagation.
                        has_flow = any(
                            i.get_name().startswith(
                                ("if-", "goto", "packed-switch", "sparse-switch")
                            )
                            for _, i in instructions
                        )
                        has_flow = has_flow or bool(
                            method.get_code() and method.get_code().get_tries_size()
                        )
                        constants, pending = {}, None
                        for offset, ins in instructions:
                            op, operands = ins.get_name(), ins.get_operands(offset)
                            regs = [v[1] for v in operands if v[0] == Operand.REGISTER]
                            if op.startswith("const-string") and not has_flow:
                                constants[regs[0]] = operands[-1][2]
                            elif op.startswith("move-result"):
                                if regs:
                                    constants.pop(regs[0], None)
                                    if pending is not None and not has_flow:
                                        constants[regs[0]] = pending
                                pending = None
                            elif op.startswith("move-object") and not has_flow:
                                value = constants.get(regs[1])
                                constants.pop(regs[0], None)
                                if value is not None:
                                    constants[regs[0]] = value
                            elif op.startswith("sget-object"):
                                pending = None
                                uri_val = None
                                field_refs = [v for v in operands if v[0] == Operand.KIND + 2]
                                if field_refs and regs:
                                    try:
                                        field_idx = field_refs[-1][1]
                                        owner, proto, field_name = vm.get_cm_field(field_idx)
                                        uri_val = FRAMEWORK_STATIC_URIS.get((owner, field_name))
                                    except Exception:
                                        uri_val = None
                                if uri_val is not None and not has_flow:
                                    constants[regs[0]] = uri_val
                                else:
                                    for register in regs:
                                        constants.pop(register, None)
                            elif op.startswith("invoke-") and not op.startswith(
                                ("invoke-custom", "invoke-polymorphic")
                            ):
                                pending = None
                                # Operand method references, not output text / string scanning.
                                refs = [v for v in operands if v[0] == Operand.KIND + 0]
                                if not refs:
                                    continue
                                owner, target_name, descriptor = vm.get_cm_method(refs[-1][1])
                                target = (
                                    owner
                                    + "->"
                                    + target_name
                                    + "".join(descriptor).replace(" ", "")
                                )
                                if (
                                    inventory
                                    and owner.startswith("Landroid/")
                                    and re.search(
                                        r"screenshot|takescreenshot|createvirtualdisplay|query|"
                                        r"getinstalled|getstring|getdeviceid|getimei",
                                        target_name,
                                        re.IGNORECASE,
                                    )
                                ):
                                    if len(inventory_calls) < 1000:
                                        inventory_calls.append(
                                            dict(
                                                target_descriptor=target,
                                                caller=caller,
                                                dex=name,
                                                offset_bytes=offset,
                                                instruction=op + " " + ins.get_output(offset),
                                            )
                                        )
                                    else:
                                        inventory_truncated = True
                                args = regs if op.startswith("invoke-static") else regs[1:]
                                ctx = {}
                                if (
                                    target.startswith(
                                        "Landroid/location/LocationManager;->getLastKnownLocation"
                                    )
                                    and args
                                    and args[0] in constants
                                ):
                                    if constants[args[0]] in {"gps", "network"}:
                                        ctx = {"provider": constants[args[0]]}
                                elif (
                                    target.startswith(
                                        "Landroid/provider/Settings$Secure;->getString"
                                    )
                                    and len(args) > 1
                                ):
                                    if constants.get(args[1]) == "android_id":
                                        ctx = {"key": "android_id"}
                                elif (
                                    target
                                    == (
                                        "Landroid/net/Uri;->parse(Ljava/lang/String;)"
                                        "Landroid/net/Uri;"
                                    )
                                    and args
                                ):
                                    pending = constants.get(args[0])
                                elif (
                                    target.startswith("Landroid/content/ContentResolver;->query")
                                    and args
                                    and args[0] in constants
                                ):
                                    ctx = {"uri": constants[args[0]]}
                                matches = [
                                    r
                                    for r in rules["api_mappings"]
                                    if not r.get("synthetic_only")
                                    and r["target_descriptor"] == target
                                    and r["context"] == ctx
                                ]
                                for rule in matches:
                                    locator = (
                                        f"apk_sha256={result['apk_sha256']}{split_prefix};dex={name};"
                                        f"caller={caller};offset_bytes={offset};target={target}"
                                    )
                                    add(
                                        "API",
                                        f"{source_prefix}{name}",
                                        locator,
                                        op + " " + ins.get_output(offset),
                                        rule["data_type"],
                                        api_call=dict(
                                            target_descriptor=target,
                                            rule_id=rule["rule_id"],
                                            ruleset_version=rules["version"],
                                            context=ctx,
                                        ),
                                    )
                            else:
                                pending = None
                                # Conservatively invalidate any register operand for unknown ops.
                                for register in regs:
                                    constants.pop(register, None)
                result["coverage"]["scanned_dex"].append(f"{source_prefix}{name}")
            except Exception as exc:
                result["coverage"]["failed_dex"].append(f"{source_prefix}{name}")
                result["errors"].append(
                    dict(
                        code="DEX_PARSE_FAILED",
                        message=(
                            f"{source_prefix}{name}: {type(exc).__name__}: {str(exc)[:200]}"
                        ),
                    )
                )
        if (
            "classes.dex" in names
            and not result["coverage"]["failed_dex"]
            and not (package_split is None and apk.get_android_manifest_xml().get("split"))
        ):
            result["coverage"]["completeness"] = "COMPLETE"
    if inventory:
        result["tools"]["unmapped_android_invokes"] = json.dumps(
            inventory_calls, ensure_ascii=True, sort_keys=True
        )
        result["tools"]["inventory_scope"] = (
            "Candidate Android-owner invocations, includes mapped calls; max 1000; "
            "no subclass-owner/name-only classification"
        )
        result["tools"]["inventory_truncated"] = str(inventory_truncated).lower()
    if sdk_collector is not None:
        for found in sdk_collector.selected():
            sdk_ev = dict(
                id=found.evidence_id,
                kind="SDK",
                status="STATIC_POTENTIAL",
                source=f"{source_prefix}{found.dex}",
                locator=(
                    "apk_sha256="
                    + result["apk_sha256"]
                    + split_prefix
                    + ";dex="
                    + found.dex
                    + ";class="
                    + found.class_name
                ),
                excerpt=(
                    found.class_name
                    + " matches published package prefix "
                    + found.prefix
                    + " of "
                    + found.signature.name
                    + " ("
                    + found.signature.vendor
                    + "); attribution only, not evidence "
                    + "of collection or transfer."
                ),
            )
            if recorded_split is not None:
                sdk_ev["package_split"] = recorded_split
            result["evidence"].append(sdk_ev)
        if sdk_collector.capped:
            # Attribution gaps are not behavior gaps; file them under the SDK
            # coverage list, never behavior ones. `observed` counts match events
            # (duplicates included), so it is not a unique class total.
            note = (
                f"SDK 归属输出上限为 {MAX_SDK_ATTRIBUTIONS} 条类，"
                f"本次共观察到 {sdk_collector.observed} 次命中，"
                f"超出上限的部分未逐条列出；"
            )
            if sdk_collector.per_sdk_floor_is_achievable():
                note += (
                    f"已保证每个命中的 SDK 至少保留 {MIN_SDK_REPRESENTATIVES} "
                    "条代表性类路径；"
                )
            note += "上限截断不代表没有更多 SDK。"
            result["coverage"]["sdk_attribution_limitations"].append(note)
    return result


def scan_package_set(base_path, splits, rules, inventory=False, sdk_rules=None):
    """Scans base APK and all splits in the package set, aggregating permissions,
    namespacing DEX entries, and resolving coverage completeness.

    splits is a list of (split_name, split_path) tuples.
    """
    base_path = Path(base_path)
    splits = [(s_name, Path(s_path)) for s_name, s_path in splits]

    # 1. Scan base APK
    base_result = scan(
        base_path,
        rules,
        inventory=inventory,
        sdk_rules=sdk_rules,
        package_split="base",
        is_split=False,
    )

    # 2. Sequentially scan each split APK
    split_results = []
    current_behavior_count = len(base_result["behaviors"])
    for split_name, split_path in splits:
        split_res = scan(
            split_path,
            rules,
            inventory=inventory,
            sdk_rules=sdk_rules,
            package_split=split_name,
            behavior_count=current_behavior_count,
            is_split=True,
        )
        split_results.append((split_name, split_path, split_res))
        current_behavior_count += len(split_res["behaviors"])

    # 3. Aggregate permissions
    all_perms = set(base_result["permissions"])
    for _, _, s_res in split_results:
        all_perms.update(s_res["permissions"])
    aggregated_permissions = sorted(all_perms)

    # 4. Merge namespaced DEX entries
    all_dex_entries = list(base_result["dex_entries"])
    scanned_dex = list(base_result["coverage"]["scanned_dex"])
    failed_dex = list(base_result["coverage"]["failed_dex"])
    for _, _, s_res in split_results:
        all_dex_entries.extend(s_res["dex_entries"])
        scanned_dex.extend(s_res["coverage"]["scanned_dex"])
        failed_dex.extend(s_res["coverage"]["failed_dex"])

    # 5. Resolve coverage completeness
    completeness = (
        "COMPLETE"
        if "base:classes.dex" in all_dex_entries and not failed_dex
        else "PARTIAL"
    )

    # 6. Deduplicate & merge evidence and behaviors
    all_evidence = list(base_result["evidence"])
    all_behaviors = list(base_result["behaviors"])
    for _, _, s_res in split_results:
        for ev in s_res["evidence"]:
            if ev["kind"] == "MANIFEST":
                perm_in_base = any(
                    bev["kind"] == "MANIFEST" and bev["excerpt"] == ev["excerpt"]
                    for bev in base_result["evidence"]
                )
                if perm_in_base:
                    continue
            all_evidence.append(ev)
        for bh in s_res["behaviors"]:
            ev_id = bh["evidence_ids"][0]
            if any(e["id"] == ev_id for e in all_evidence):
                all_behaviors.append(bh)

    # 7. Package set summary
    base_file = {
        "file_name": base_path.name,
        "part": "BASE",
        "split_name": None,
        "sha256": base_result["apk_sha256"],
        "size_bytes": base_path.stat().st_size,
    }
    split_files = [
        {
            "file_name": s_path.name,
            "part": "SPLIT",
            "split_name": s_name,
            "sha256": s_res["apk_sha256"],
            "size_bytes": s_path.stat().st_size,
        }
        for s_name, s_path, s_res in split_results
    ]
    package_set_summary = {
        "base_file": base_file,
        "splits": split_files,
        "files": [base_file, *split_files],
        "total_size_bytes": base_file["size_bytes"] + sum(s["size_bytes"] for s in split_files),
        "split_count": len(split_files),
        "split_names": [s["split_name"] for s in split_files],
    }

    clean_limitations = [
        lim
        for lim in base_result["coverage"]["limitations"]
        if "other package splits unavailable" not in lim
    ]

    return {
        "apk_sha256": base_result["apk_sha256"],
        "package_name": base_result["package_name"],
        "version_code": base_result["version_code"],
        "version_name": base_result["version_name"],
        "permissions": aggregated_permissions,
        "dex_entries": all_dex_entries,
        "package_set": package_set_summary,
        "coverage": {
            "completeness": completeness,
            "scope": "DEX_ENTRIES",
            "behavior_detection": "LIMITED_RULE_BASED_STATIC",
            "behavior_limitations": base_result["coverage"]["behavior_limitations"],
            "sdk_attribution_limitations": base_result["coverage"]["sdk_attribution_limitations"],
            "limitations": clean_limitations,
            "scanned_dex": scanned_dex,
            "failed_dex": failed_dex,
        },
        "tools": base_result["tools"],
        "evidence": all_evidence,
        "behaviors": all_behaviors,
        "errors": base_result["errors"] + [e for _, _, s in split_results for e in s["errors"]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--probe", action="store_true", help="Trusted fixture isolation inspection")
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="Bounded candidate Android invocation references, not new evidence",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "rules/taxonomy.v0.3.json",
    )
    parser.add_argument(
        "--sdk-rules",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "rules/sdk-signatures.v1.0.json",
        help="Sourced third-party package prefixes (default: the shipped ruleset)",
    )
    parser.add_argument(
        "--no-sdk-attribution",
        action="store_true",
        help=(
            "Disable SDK attribution entirely; wins over --sdk-rules and needs no "
            "empty value for it"
        ),
    )
    parser.add_argument(
        "--jadx", nargs="?", const="jadx", help="Optional reference decompiler binary"
    )
    args = parser.parse_args()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            if args.probe:
                result = isolation_probe(args.apk)
            elif args.apk.is_dir():
                from .package_set import validate_package_set

                pkg_set = validate_package_set(args.apk)
                base_path = args.apk / pkg_set.base.file_name
                splits = [(s.split_name, args.apk / s.file_name) for s in pkg_set.splits]
                rules_data = json.loads(args.rules.read_text(encoding="utf-8"))
                sdk_data = (
                    json.loads(args.sdk_rules.read_text(encoding="utf-8"))
                    if args.sdk_rules is not None and not args.no_sdk_attribution
                    else None
                )
                result = scan_package_set(
                    base_path,
                    splits,
                    rules_data,
                    inventory=args.inventory,
                    sdk_rules=sdk_data,
                )
            else:
                result = scan(
                    args.apk,
                    json.loads(args.rules.read_text(encoding="utf-8")),
                    inventory=args.inventory,
                    sdk_rules=(
                        json.loads(args.sdk_rules.read_text(encoding="utf-8"))
                        if args.sdk_rules is not None and not args.no_sdk_attribution
                        else None
                    ),
                )
        if args.jadx:
            try:
                with tempfile.TemporaryDirectory(prefix="privacytrace-jadx-") as output:
                    version = subprocess.run(
                        [args.jadx, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=True,
                    )
                    reference = subprocess.run(
                        [args.jadx, "--no-res", "-d", output, str(args.apk)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    )
                    result["tools"]["jadx"] = version.stdout.strip()[:100]
                    if reference.returncode:
                        result["tools"]["jadx"] += ":FAILED_BYTECODE_FALLBACK"
                        result["coverage"]["limitations"].append(
                            "JADX reference failed; bytecode evidence retained"
                        )
                    else:
                        result["coverage"]["limitations"].append(
                            "JADX reference completed; authoritative locators "
                            "remain DEX byte offsets"
                        )
            except (OSError, subprocess.SubprocessError):
                result["tools"]["jadx"] = "UNAVAILABLE_BYTECODE_FALLBACK"
                result["coverage"]["limitations"].append(
                    "JADX unavailable or timed out; bytecode evidence retained"
                )
        exit_code = 0
    except Exception as exc:
        result = empty_result()
        if isinstance(exc, BadZipFile):
            exc = ScanError("ZIP_INVALID", "ZIP structure or CRC validation failed")
        result["errors"] = [
            dict(
                code=getattr(exc, "code", "SCAN_FAILED"),
                message=getattr(exc, "message", type(exc).__name__),
            )
        ]
        exit_code = 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
