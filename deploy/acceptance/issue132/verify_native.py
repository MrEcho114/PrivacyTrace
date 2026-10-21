"""Run existing native scope/TLS regressions on JVM, without Android SDK or global trust edits."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
JARS = (
    "kotlin-compiler-embeddable-1.9.24.jar", "kotlin-stdlib-1.9.24.jar",
    "kotlin-script-runtime-1.9.24.jar", "kotlin-reflect-1.6.10.jar",
    "trove4j-1.0.20200330.jar", "annotations-13.0.jar", "okhttp-4.12.0.jar",
    "mockwebserver-4.12.0.jar", "okhttp-tls-4.12.0.jar", "okio-jvm-3.6.0.jar",
    "junit-4.13.2.jar", "hamcrest-core-1.3.jar",
)
TESTS = ("ProbeOperationTest", "HttpsHealthCallTest", "AnalysisTransportTest")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", default="java")
    parser.add_argument("--dependency-cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    jars = [args.dependency_cache.resolve() / name for name in JARS]
    if any(not path.is_file() for path in jars):
        parser.error("missing pinned JVM dependencies; see README; no downloads performed")
    base = ROOT / "experiments/android-package-probe"
    core = base / "core/src/main/java/org/privacytrace/probe"
    sources = sorted(path for path in core.glob("*.kt")
                     if not path.name.startswith("Android") and path.name != "ProtectedKeyInput.kt")
    sources += [base / "app/src/testSupport/java/org/privacytrace/probe" / (name + ".kt")
                for name in ("HealthTlsChecks", "AnalysisTransportTest")]
    sources += [base / "app/src/test/java/org/privacytrace/probe" / (name + ".kt")
                for name in TESTS[:2]]
    args.output_dir.mkdir(parents=True, exist_ok=False)
    classes = args.output_dir.resolve() / "classes"
    classes.mkdir()
    classpath = os.pathsep.join(str(path) for path in jars)
    receipt = {
        "record_kind": "JVM_COMPONENT_REGRESSION", "android_acceptance": False,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip(),
        "source_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True,
        ).strip()),
        "source_sha256": {path.relative_to(ROOT).as_posix(): sha(path) for path in sources},
        "dependency_sha256": {path.name: sha(path) for path in jars},
        "tests": list(TESTS), "status": "FAILED",
    }
    compile_command = [
        args.java, "-Dfile.encoding=UTF-8", "-cp", classpath,
        "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler", "-no-stdlib", "-no-reflect",
        "-jvm-target", "17", "-classpath", classpath, "-d", str(classes),
        *[str(path) for path in sources],
    ]
    commands = [compile_command, [
        args.java, "-Dfile.encoding=UTF-8", "-cp", str(classes) + os.pathsep + classpath,
        "org.junit.runner.JUnitCore", *["org.privacytrace.probe." + name for name in TESTS],
    ]]
    for name, command in zip(("compile", "junit"), commands, strict=True):
        try:
            result = subprocess.run(command, capture_output=True, timeout=180)
            log = args.output_dir / (name + ".log")
            log.write_bytes(result.stdout + result.stderr)
            receipt[name] = {"exit_code": result.returncode, "log_sha256": sha(log)}
            if result.returncode:
                break
        except (OSError, subprocess.TimeoutExpired) as error:
            receipt[name] = {"error": type(error).__name__}
            break
    else:
        receipt["status"] = "PASSED"
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    path = args.output_dir / "receipt.json"
    encoded = json.dumps(receipt, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8")
    if path.read_text(encoding="utf-8") != encoded:
        raise OSError("native receipt readback failed")
    print(json.dumps({"status": receipt["status"], "receipt_sha256": sha(path)}))
    return 0 if receipt["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
