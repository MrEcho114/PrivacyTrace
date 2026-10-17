"""Freeze callsites from pinned Android dexdump, independently of the APK scanner.

Run only on the hash-locked authored APKs inside the networkless builder.
Neither Androguard nor benchmark predictions are imported or read here.
"""

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_dump(text):
    """dexdump PCs count 16-bit code units; ordinals count decoded instructions."""
    owner = name = descriptor = None
    ordinal = 0
    calls = []
    for line in text.splitlines():
        field = re.search(r"(Class descriptor|name|type)\s*:\s*'([^']+)'", line)
        if field:
            key, value = field.groups()
            if key == "Class descriptor":
                owner = value
            elif key == "name":
                name, ordinal = value, 0
            else:
                descriptor = value
        instruction = re.match(r"^([0-9a-f]+):\s+([0-9a-f ]+)\|([0-9a-f]+): (\S+)(.*)", line)
        if not instruction:
            continue
        file_offset, raw, pc, opcode, operands = instruction.groups()
        if opcode.startswith("invoke-"):
            target = re.search(r", (L[^ ]+;)\.([^: ]+):(\([^ ]+) // method@", operands)
            if not target or not all((owner, name, descriptor)):
                raise ValueError("Unsupported dexdump invocation")
            target_owner, target_name, target_type = target.groups()
            calls.append({
                "caller_descriptor": owner + "->" + name + descriptor,
                "target_descriptor": target_owner + "->" + target_name + target_type,
                "opcode": opcode,
                "offset_code_units": int(pc, 16),
                "offset_bytes": int(pc, 16) * 2,
                "instruction_ordinal": ordinal,
                "dex_file_offset_bytes": int(file_offset, 16),
                "instruction_hex": bytes.fromhex(raw).hex(),
            })
        ordinal += 1
    return calls


def build_reference(suite, artifacts, dexdump):
    lock = json.loads((suite / "artifacts.lock.json").read_bytes())
    inputs = json.loads((suite / "inputs.lock.json").read_bytes())
    if lock["source_hashes"] != inputs["sources"]:
        raise ValueError("Source lock mismatch")
    for name, expected in inputs["sources"].items():
        if sha256((suite / name).read_bytes()) != expected:
            raise ValueError("Source differs from frozen input")
    scenarios = {}
    for scenario, expected in lock["apks"].items():
        apk = artifacts / (scenario + ".apk")
        if sha256(apk.read_bytes()) != expected:
            raise ValueError("APK differs from frozen artifact")
        with zipfile.ZipFile(apk) as archive:
            if [name for name in archive.namelist() if name.endswith(".dex")] != ["classes.dex"]:
                raise ValueError("Reference v1 covers single DEX fixtures only")
            dex = archive.read("classes.dex")
        dump = subprocess.check_output([str(dexdump), "-d", str(apk)], text=True)
        calls = parse_dump(dump)
        # Context comes from the frozen authored source, not the scanner's inferred value.
        source = (suite / "android" / scenario / "MainActivity.java").read_text()
        for call in calls:
            call["dex"] = "classes.dex"
            call["context"] = {}
            if "->readLocation(" in call["caller_descriptor"]:
                provider = re.search(r'return manager.getLastKnownLocation\("(gps|network)"\)', source)
                if provider:
                    call["context"] = {"provider": provider[1]}
                elif "return manager.getLastKnownLocation(provider);" not in source:
                    raise ValueError("Context requires a separate source review")
            # Check dexdump's instruction bytes against the DEX bytes independently.
            raw = bytes.fromhex(call["instruction_hex"])
            start = call["dex_file_offset_bytes"]
            if dex[start:start + len(raw)] != raw:
                raise ValueError("Disassembly bytes disagree with DEX")
        scenarios[scenario] = {"apk_sha256": expected,
                               "dex_sha256": {"classes.dex": sha256(dex)}, "invokes": calls}
    return {
        "schema_version": 1,
        "reference_version": "controlled-dexdump-v1",
        "method": "Android dexdump disassembly plus frozen authored source context",
        "dexdump_sha256": sha256(dexdump.read_bytes()),
        "toolchain": json.loads((suite / "toolchain.lock.json").read_bytes()),
        "source_hashes": inputs["sources"],
        "limitations": ["Only the hash-locked authored single-DEX APKs are covered.",
                        "Context is source-reviewed; no runtime or general dataflow claim.",
                        "No prediction or scanner output is used as a location reference."],
        "scenarios": scenarios,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--dexdump", type=Path, default=Path("/opt/sdk/android-15/dexdump"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify-reference", type=Path)
    args = parser.parse_args()
    actual = build_reference(args.suite, args.artifacts, args.dexdump)
    if args.verify_reference:
        frozen_raw = args.verify_reference.read_bytes()
        if sha256(frozen_raw) != args.verify_reference.with_suffix(".sha256").read_text().strip():
            raise ValueError("Reference checksum mismatch")
        frozen = json.loads(frozen_raw)
        for key in ("schema_version", "reference_version", "method", "dexdump_sha256", "toolchain"):
            if actual[key] != frozen[key]:
                raise ValueError("Reference toolchain mismatch")
        for key in ("source_hashes", "scenarios"):
            if any(frozen[key].get(name) != value for name, value in actual[key].items()):
                raise ValueError("Independent reference differs from actual build")
        print(json.dumps({"verified": True, "reference_sha256": sha256(frozen_raw),
                          "reference_version": frozen["reference_version"],
                          "dexdump_sha256": actual["dexdump_sha256"],
                          "scenario_count": len(actual["scenarios"]),
                          "artifacts": {name: {key: item[key] for key in ("apk_sha256", "dex_sha256")}
                                        for name, item in actual["scenarios"].items()}}))
        return
    raw = (json.dumps(actual,
                      ensure_ascii=False, indent=2) + "\n").encode()
    # Never overwrite an existing frozen reference.
    with args.output.open("xb") as stream:
        stream.write(raw)
    with args.output.with_suffix(".sha256").open("x") as stream:
        stream.write(sha256(raw) + "\n")


if __name__ == "__main__":
    main()
