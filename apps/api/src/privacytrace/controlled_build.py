"""Build source-owned Java scenarios with installed JDK, AAPT2 and D8 (no Gradle)."""

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from .controlled_inputs import load_case, source_hashes
from .policy_intake import digest, read_safe


def build(case_dir, sdk, jdk, output):
    case_dir, sdk, jdk, output = [Path(p).absolute() for p in (case_dir, sdk, jdk, output)]
    case = load_case(case_dir)
    config_bytes = read_safe(case_dir.parent / "toolchain.json")
    config = json.loads(config_bytes)
    suffix = ".exe" if os.name == "nt" else ""
    java, javac = [jdk / "bin" / (name + suffix) for name in ("java", "javac")]
    platform = sdk / "platforms" / config["platform"]
    build_tools = sdk / "build-tools" / config["build_tools"]
    android = platform / "android.jar"
    aapt = build_tools / ("aapt2" + suffix)
    d8 = build_tools / "lib/d8.jar"
    release = read_safe(jdk / "release").decode()
    if f'JAVA_VERSION="{config["java_version"]}"' not in release:
        raise ValueError("JDK differs from locked version")
    if (
        f"Pkg.Revision={config['platform_revision']}"
        not in read_safe(platform / "source.properties").decode().splitlines()
    ):
        raise ValueError("Android platform differs from locked revision")
    tools = {
        "jdk": config["java_version"],
        "platform": config["platform"],
        "build_tools": config["build_tools"],
    }
    for name, path in {
        "android.jar": android,
        "aapt2": aapt,
        "d8.jar": d8,
        "jdk-release": jdk / "release",
        "javac": javac,
        "java": java,
        "ct.sym": jdk / "lib/ct.sym",
    }.items():
        tools[name + "_sha256"] = digest(read_safe(path, max_bytes=256 * 1024 * 1024))
    hashes = source_hashes(case_dir)
    if any(
        p.is_symlink() or getattr(p, "is_junction", lambda: False)()
        for p in (output, *output.parents)
    ):
        raise ValueError("Linked build output is not allowed")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    for name in hashes:
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = read_safe(case_dir / name)
        if digest(data) != hashes[name]:
            raise ValueError("Source changed during build")
        target.write_bytes(data)
    classes, dex = output / "classes", output / "dex"
    classes.mkdir()
    dex.mkdir()
    commands = []

    def execute(args):
        args = list(map(str, args))
        logical = []
        for arg in args:
            for path, label in ((jdk, "<jdk>"), (sdk, "<sdk>"), (output, "<output>")):
                arg = arg.replace(str(path), label)
            logical.append(arg.replace("\\", "/"))
        commands.append(logical)
        result = subprocess.run(args, capture_output=True, timeout=120)
        with (output / "build.log").open("ab") as log:
            log.write(result.stdout + result.stderr)
        if result.returncode:
            raise ValueError("Build tool failed; inspect local build.log")

    execute(
        [
            javac,
            "--release",
            config["java_release"],
            "-g",
            "-encoding",
            "UTF-8",
            "-proc:none",
            "-classpath",
            android,
            "-d",
            classes,
            *sorted((output / "source/src").rglob("*.java")),
        ]
    )
    execute(
        [
            java,
            "-cp",
            d8,
            "com.android.tools.r8.D8",
            "--debug",
            "--min-api",
            str(config["min_api"]),
            "--lib",
            android,
            "--output",
            dex,
            *sorted(classes.rglob("*.class")),
        ]
    )
    execute(
        [
            aapt,
            "link",
            "-I",
            android,
            "--manifest",
            output / "source/AndroidManifest.xml",
            "--min-sdk-version",
            str(config["min_api"]),
            "--target-sdk-version",
            "35",
            "-o",
            output / "resources.apk",
        ]
    )
    # Only our just-built artifacts are opened here, never unknown APK inputs.
    with ZipFile(output / "resources.apk") as resources:
        entries = {name: resources.read(name) for name in resources.namelist()}
    for path in sorted(dex.glob("*.dex")):
        entries[path.name] = path.read_bytes()
    if "classes.dex" not in entries:
        raise ValueError("D8 produced no primary DEX")
    apk = output / "scenario.apk"
    with ZipFile(apk, "x", compression=ZIP_STORED) as archive:
        for name, content in sorted(entries.items()):
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, content)
    receipt = {
        "schema_version": 1,
        "case_id": case.case_id,
        "source_hashes": hashes,
        "toolchain_sha256": digest(config_bytes),
        "apk": "scenario.apk",
        "apk_sha256": digest(apk.read_bytes()),
        "tools": tools,
        "commands": commands,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    (output / "build.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("case-dir", "sdk", "jdk", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = build(args.case_dir, args.sdk, args.jdk, args.output_dir)
        print(
            json.dumps(
                {
                    "status": "BUILT_UNSIGNED",
                    "case_id": receipt["case_id"],
                    "apk_sha256": receipt["apk_sha256"],
                }
            )
        )
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "FAILED", "error": "CONTROLLED_BUILD_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
