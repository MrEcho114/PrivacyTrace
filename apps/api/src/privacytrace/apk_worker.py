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
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

MAX_APK = 150 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_ENTRY = 128 * 1024 * 1024
MAX_ENTRIES = 20000


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
        coverage=dict(completeness="PARTIAL", scanned_dex=[], failed_dex=[], limitations=[]),
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


def scan(path, rules, inventory=False):
    from androguard.core.apk import APK
    from androguard.core.dex import DEX, Operand
    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level="WARNING")
    result = empty_result()
    inventory_calls = []
    inventory_truncated = False
    result["tools"] = {
        "androguard": importlib.metadata.version("androguard"),
        "ruleset": rules["version"],
    }
    with checked_entries(path) as archive:
        result["apk_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if "AndroidManifest.xml" not in archive.namelist():
            raise ScanError("MANIFEST_MISSING", "AndroidManifest.xml is required")
        apk = APK(str(path))
        if not apk.is_valid_APK() or apk.get_android_manifest_xml() is None:
            raise ScanError("MANIFEST_INVALID", "Binary Android manifest could not be parsed")
        try:
            raw_version_code = apk.get_androidversion_code()
            version_code = int(raw_version_code, 16 if raw_version_code.startswith("0x") else 10)
            if version_code < 0:
                raise ValueError("negative versionCode")
        except (AttributeError, TypeError, ValueError) as exc:
            raise ScanError("MANIFEST_INVALID", "Manifest versionCode must be an integer") from exc
        android_ns = "{http://schemas.android.com/apk/res/android}"
        declarations = sorted({
            (element.get(android_ns + "name"), tag, element.get(android_ns + "maxSdkVersion", ""))
            for tag in ("uses-permission", "uses-permission-sdk-23")
            for element in apk.get_android_manifest_xml().findall(tag)
            if element.get(android_ns + "name")
        })
        result.update(
            package_name=apk.get_package(),
            version_code=version_code,
            version_name=apk.get_androidversion_name(),
            permissions=sorted({name for name, _, _ in declarations}),
        )
        if not result["package_name"]:
            raise ScanError("MANIFEST_INVALID", "Manifest package is missing")
        result["coverage"]["limitations"] = [
            "Static potential only; runtime access, reflection, native code, dynamic loading, "
            "and interprocedural argument resolution are not proven."
        ]

        def add(kind, source, locator, excerpt, data_type, action="ACCESS", api_call=None):
            identity = hashlib.sha256((kind + locator).encode()).hexdigest()[:24]
            evidence = dict(
                id="ev-" + identity,
                kind=kind,
                status="STATIC_POTENTIAL",
                source=source,
                locator=locator,
                excerpt=excerpt,
            )
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
            for permission, tag, max_sdk in declarations:
                if permission != mapping["permission"]:
                    continue
                bounds = ""
                if tag == "uses-permission-sdk-23":
                    bounds += ";tag=uses-permission-sdk-23;min_sdk=23"
                if max_sdk:
                    bounds += ";max_sdk=" + max_sdk
                add(
                    "MANIFEST",
                    "AndroidManifest.xml",
                    "apk_sha256=" + result["apk_sha256"] + ";permission=" + permission + bounds,
                    permission + bounds,
                    mapping["data_type"],
                    "CAPABILITY",
                )
        names = sorted(n for n in archive.namelist() if re.fullmatch(r"classes(?:[0-9]+)?\.dex", n))
        result["dex_entries"] = names
        if "classes.dex" not in names:
            result["coverage"]["limitations"].append(
                "Primary classes.dex missing; split or incomplete APK"
            )
        if apk.get_android_manifest_xml().get("split"):
            result["coverage"]["limitations"].append(
                "Split manifest; other package splits unavailable"
            )
        for name in names:
            try:
                vm = DEX(archive.read(name))
                for cls in vm.get_classes():
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
                                        f"apk_sha256={result['apk_sha256']};dex={name};"
                                        f"caller={caller};offset_bytes={offset};target={target}"
                                    )
                                    add(
                                        "API",
                                        name,
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
                result["coverage"]["scanned_dex"].append(name)
            except Exception as exc:
                result["coverage"]["failed_dex"].append(name)
                result["errors"].append(
                    dict(code="DEX_PARSE_FAILED", message=name + ": " + type(exc).__name__)
                )
        if (
            "classes.dex" in names
            and not result["coverage"]["failed_dex"]
            and not apk.get_android_manifest_xml().get("split")
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
    return result


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
        "--jadx", nargs="?", const="jadx", help="Optional reference decompiler binary"
    )
    args = parser.parse_args()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = (
                isolation_probe(args.apk)
                if args.probe
                else scan(
                    args.apk,
                    json.loads(args.rules.read_text(encoding="utf-8")),
                    inventory=args.inventory,
                )
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
