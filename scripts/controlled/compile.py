#!/usr/bin/env python3
"""Run inside the pinned network-disabled builder, never on untrusted APKs."""

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path("/source")
SUITES = {"spec30": ROOT / "benchmarks/controlled", "pt907": ROOT / "benchmarks/controlled-v2"}
TOOLS = Path("/opt/sdk/android-15")
PLATFORM = Path("/opt/sdk/android-35/android.jar")


def main():
    SUITE = SUITES[sys.argv[1] if len(sys.argv) > 1 else "spec30"]
    lock = json.loads((SUITE / "inputs.lock.json").read_text())
    tools_lock = json.loads((SUITE / "toolchain.lock.json").read_text())
    sources = {
        name: hashlib.sha256((SUITE / name).read_bytes()).hexdigest()
        for name in lock["sources"]
    }
    if sources != lock["sources"]:
        raise ValueError("Source hash differs from frozen inputs")
    hashes = {}
    for scenario in lock["features"]:
        source = SUITE / "android" / scenario
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            classes, dex = work / "classes", work / "dex"
            classes.mkdir()
            dex.mkdir()
            subprocess.run(
                [
                    "javac",
                    "-g",
                    "-source",
                    "8",
                    "-target",
                    "8",
                    "-classpath",
                    str(PLATFORM),
                    "-d",
                    str(classes),
                    str(source / "MainActivity.java"),
                ],
                check=True,
            )
            subprocess.run(
                [
                    str(TOOLS / "d8"),
                    "--lib",
                    str(PLATFORM),
                    "--min-api",
                    "23",
                    "--output",
                    str(dex),
                    *[str(path) for path in sorted(classes.rglob("*.class"))],
                ],
                check=True,
            )
            resources = work / "resources.apk"
            subprocess.run(
                [
                    str(TOOLS / "aapt2"),
                    "link",
                    "-I",
                    str(PLATFORM),
                    "--manifest",
                    str(source / "AndroidManifest.xml"),
                    "-o",
                    str(resources),
                ],
                check=True,
            )
            # Normalize ZIP metadata for byte-identical rebuilds; APKs are unsigned analysis fixtures.
            with zipfile.ZipFile(resources) as archive:
                entries = {name: archive.read(name) for name in archive.namelist()}
            entries["classes.dex"] = (dex / "classes.dex").read_bytes()
            output = Path("/output") / (scenario + ".apk")
            with zipfile.ZipFile(output, "w") as archive:
                for name, value in sorted(entries.items()):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, value)
            hashes[scenario] = hashlib.sha256(output.read_bytes()).hexdigest()
    receipt = {
        "schema_version": 1,
        "source_hashes": sources,
        "apks": hashes,
        "toolchain": tools_lock,
        "artifact_use": "UNSIGNED_STATIC_ANALYSIS_ONLY",
        "javac": subprocess.check_output(["javac", "-version"], text=True).strip(),
        "d8": subprocess.check_output(
            [str(TOOLS / "d8"), "--version"], text=True
        ).strip(),
        "aapt2": subprocess.run(
            [str(TOOLS / "aapt2"), "version"],
            capture_output=True,
            text=True,
            check=True,
        ).stderr.strip(),
    }
    Path("/output/build-receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
