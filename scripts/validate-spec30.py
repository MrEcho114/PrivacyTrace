"""Run the integrated source/CLI/HTTP/browser/offline acceptance; retain failed runs."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from controlled_paths import daemon_path
from privacytrace.controlled import SUITE, SUITES, scenario_ids
from privacytrace.isolated_scan import docker_prefix

ROOT = Path(__file__).resolve().parents[1]


SCENARIOS = tuple(f"C0{i}" for i in range(1, 7))
RECEIPT_INVALID = "BUILD_ARTIFACT_RECEIPT_INVALID"
HASH_MISMATCH = "BUILD_ARTIFACT_HASH_MISMATCH"


def _frozen_build_contract(suite=SUITE):
    return (
        json.loads((suite / "artifacts.lock.json").read_bytes()),
        json.loads((suite / "inputs.lock.json").read_bytes()),
        json.loads((suite / "toolchain.lock.json").read_bytes()),
    )


def verify_build_artifacts(build_a, build_b, *, contract=None, scenarios=SCENARIOS):
    """Hash both complete builds; never authorize scanning by receipts alone."""
    try:
        frozen, inputs, toolchain = _frozen_build_contract() if contract is None else contract
        if (
            not isinstance(frozen, dict) or not isinstance(inputs, dict)
            or not isinstance(toolchain, dict)
            or frozen.get("schema_version") != 1
            or inputs.get("schema_version") != 1
        ):
            return RECEIPT_INVALID
        expected_apks = frozen.get("apks")
        expected_sources = frozen.get("source_hashes")
        sources = inputs.get("sources")
        if (
            not isinstance(expected_apks, dict)
            or set(expected_apks) != set(scenarios)
            or not isinstance(expected_sources, dict)
            or not isinstance(sources, dict)
            or set(expected_sources) != set(sources)
        ):
            return RECEIPT_INVALID
        if expected_sources != sources:
            return HASH_MISMATCH

        for directory in (build_a, build_b):
            receipt = json.loads((directory / "build-receipt.json").read_bytes())
            if (
                not isinstance(receipt, dict)
                or receipt.get("schema_version") != 1
                or receipt.get("artifact_use") != "UNSIGNED_STATIC_ANALYSIS_ONLY"
                or receipt.get("toolchain") != toolchain
                or not isinstance(receipt.get("apks"), dict)
                or not isinstance(receipt.get("source_hashes"), dict)
                or set(receipt["apks"]) != set(scenarios)
                or set(receipt["source_hashes"]) != set(expected_sources)
                or {file.name for file in directory.glob("*.apk")}
                != {scenario + ".apk" for scenario in scenarios}
            ):
                return RECEIPT_INVALID
            for mapping in (receipt["apks"], receipt["source_hashes"], expected_apks, expected_sources):
                if any(
                    not isinstance(value, str) or len(value) != 64
                    or any(char not in "0123456789abcdef" for char in value)
                    for value in mapping.values()
                ):
                    return RECEIPT_INVALID
            if receipt["apks"] != expected_apks or receipt["source_hashes"] != expected_sources:
                return HASH_MISMATCH
            for scenario in scenarios:
                apk = directory / (scenario + ".apk")
                if apk.is_symlink() or not apk.is_file():
                    return RECEIPT_INVALID
                digest = hashlib.sha256()
                with apk.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != receipt["apks"][scenario]:
                    return HASH_MISMATCH
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return RECEIPT_INVALID
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/toolchain")
    parser.add_argument("--cached", action="store_true")
    parser.add_argument("--suite", choices=SUITES, default="spec30")
    parser.add_argument("--playwright-modules", type=Path,
                        default=ROOT / "tmp/spec30-browser/node_modules")
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:12]
    output = (args.output or ROOT / "tmp/spec30-integration" / run_id).absolute()
    output.mkdir(parents=True, exist_ok=False)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    stages = []
    servers = []
    logs = []

    def stage(name, command, env=None, timeout=900):
        started = time.monotonic()
        print("Running " + name, flush=True)
        failure = {}
        with (output / (name + ".log")).open("wb") as log:
            try:
                # Prepare host-dependent arguments inside the same failure boundary.
                argv = command() if callable(command) else command
                result = subprocess.run(argv, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        env=env, timeout=timeout, check=False)
                code = result.returncode
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                code = -1
                failure["error_type"] = type(error).__name__
        stages.append({"stage": name, "exit_code": code,
                       "elapsed_seconds": time.monotonic() - started, **failure})
        print(f"{name}: exit {code}", flush=True)
        if code:
            print((output / (name + ".log")).read_text(encoding="utf-8", errors="replace")[-4000:],
                  flush=True)
        return code == 0

    def python(script, *values):
        return [sys.executable, str(ROOT / "scripts" / script), *map(str, values)]

    def serve(name, command, url):
        # Refuse unknown listeners; only this run's own children are terminated.
        try:
            urllib.request.urlopen(url, timeout=1).close()
        except OSError:
            pass
        else:
            raise ValueError("Acceptance port already in use")
        log = (output / (name + ".log")).open("wb")
        logs.append(log)
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        servers.append(process)
        for _ in range(100):
            if process.poll() is not None:
                raise ValueError("Acceptance server failed to start")
            try:
                urllib.request.urlopen(url, timeout=1).close()
                return
            except OSError:
                time.sleep(0.1)
        raise ValueError("Acceptance server did not become ready")

    passed = False
    try:
        build_a, build_b = output / "build-a", output / "build-b"
        common = ["--suite", args.suite, "--cache", args.cache,
                  *(["--cached"] if args.cached else [])]
        built = stage("build-a", python("build-controlled-apks.py", *common, "--output", build_a))
        rebuilt = built and stage("build-b", python("build-controlled-apks.py", "--suite", args.suite, "--cache",
                                                   args.cache, "--cached", "--output", build_b))
        rebuild_error = "BUILD_A_FAILED" if not built else ("BUILD_B_FAILED" if not rebuilt else None)
        if rebuild_error:
            stages[-1]["error_code"] = rebuild_error
        if rebuilt:
            rebuild_error = (
                verify_build_artifacts(build_a, build_b) if args.suite == "spec30"
                else verify_build_artifacts(build_a, build_b,
                                            contract=_frozen_build_contract(SUITES[args.suite]),
                                            scenarios=scenario_ids(SUITES[args.suite]))
            )
            stages.append({
                "stage": "rebuild-hashes",
                "exit_code": 1 if rebuild_error else 0,
                **({"error_code": rebuild_error} if rebuild_error else {}),
            })
        # An untrusted build must never enter the actual worker/prediction path.
        if rebuild_error is None and not stage(
            "worker-build",
            lambda: [*docker_prefix(), "build", "-f",
                     daemon_path(ROOT / "apps/api/worker.Dockerfile"),
                     "-t", "privacytrace-worker:s1", daemon_path(ROOT)],
        ):
            rebuild_error = "WORKER_BUILD_FAILED"
            stages[-1]["error_code"] = rebuild_error
        # Retain every scheme/scenario row on failure; mismatched builds are never scanned.
        comparison_command = [
            sys.executable, "-m", "privacytrace.benchmark", "run",
            "--artifacts", str(build_a), "--output", str(output / "evaluation"),
            "--suite", args.suite,
        ]
        if rebuild_error is not None:
            comparison_command.extend(["--blocked-error", rebuild_error])
        compared = stage("six-scenarios" if args.suite == "spec30" else "twelve-scenarios",
                         comparison_command)
        if not (built and rebuilt and compared) or any(item["exit_code"] for item in stages):
            return 1
        env = {**os.environ, "PRIVACYTRACE_CONTROLLED_ARTIFACTS": str(build_a),
               "PRIVACYTRACE_CONTROLLED_SUITE": args.suite}
        if not stage("source-cli-regressions", [sys.executable, "-m", "pytest",
                     "apps/api/tests/test_controlled_source_cli.py", "-q", "-p", "no:cacheprovider",
                     "--basetemp", str(output / "source-cli-temp")],
                     env=env):
            return 1
        npm = "npm.cmd" if os.name == "nt" else "npm"
        if not stage("web-build", [npm, "run", "build"]):
            return 1
        if args.suite == "pt907":
            serve("api", python("serve-reports.py", "--store-dir", output / "evaluation/jobs"),
                  "http://127.0.0.1:8000/api/v1/health")
            serve("web", ["node", str(ROOT / "node_modules/vite/bin/vite.js"), "preview", "--host",
                           "127.0.0.1", "--port", "5173", "--strictPort", "--config",
                           str(ROOT / "apps/web/vite.config.ts"), str(ROOT / "apps/web")],
                  "http://127.0.0.1:5173")
            env = {**os.environ, "PLAYWRIGHT_MODULE_PATH":
                   str(args.playwright_modules.absolute() / "playwright")}
            passed = stage("controlled-browser", ["node", str(ROOT / "scripts/verify-controlled-browser.cjs"),
                           str(output / "evaluation/comparison.json"), str(output / "browser-proof")], env=env)
            return 0 if passed else 1
        if not stage("export-offline", python("export-offline.py", "--run", output / "evaluation",
                                              "--output", output / "offline")):
            return 1
        if not stage("browser-fixtures", python("prepare-browser-check.py", "--store-dir",
                     output / "evaluation/jobs", "--output", output / "browser-jobs")):
            return 1
        modules = args.playwright_modules.absolute()
        if json.loads((modules / "playwright/package.json").read_bytes())["version"] != "1.62.1":
            raise ValueError("Acceptance requires the existing Playwright 1.62.1 environment")
        executable = subprocess.check_output(
            ["node", "-e", "process.stdout.write(require(process.argv[1]).chromium.executablePath())",
             str(modules / "playwright")], text=True,
        ).strip()
        serve("api", python("serve-reports.py", "--store-dir", output / "browser-jobs"),
              "http://127.0.0.1:8000/api/v1/health")
        serve("web", ["node", str(ROOT / "node_modules/vite/bin/vite.js"), "preview", "--host",
                       "127.0.0.1", "--port", "5173", "--strictPort", "--config",
                       str(ROOT / "apps/web/vite.config.ts"), str(ROOT / "apps/web")],
              "http://127.0.0.1:5173")
        serve("viewer", [sys.executable, str(output / "offline/viewer.py"), "--port", "8765"],
              "http://127.0.0.1:8765/api/v1/jobs")
        env = {**os.environ, "PLAYWRIGHT_MODULE_PATH": str(modules / "playwright"),
               "PRIVACYTRACE_CHROMIUM": executable}
        if not stage("controlled-browser", ["node", str(ROOT / "scripts/verify-browser.cjs"),
                                             str(output / "browser-proof")], env=env):
            return 1
        if not stage("independent-offline", python("verify-offline.py", "--package",
                     output / "offline", "--browser-runtime", Path(executable).parents[1],
                     "--playwright-modules", modules, "--output", output / "offline-proof")):
            return 1
        passed = True
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        stages.append({"stage": "acceptance-error", "exit_code": 1,
                       "error_type": type(error).__name__})
        print("Acceptance failed: " + type(error).__name__, flush=True)
        return 1
    finally:
        for server in servers:
            server.terminate()
        for server in servers:
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
        for log in logs:
            log.close()
        # Allowlist evidence only: no APK, job store, policy capture or raw logs.
        evidence = {}
        for relative in ["build-a/build-receipt.json", "build-b/build-receipt.json",
                         "evaluation/comparison.json", "browser-proof/browser-proof.json",
                         "offline-proof/offline-proof.json"]:
            path = output / relative
            if path.exists():
                evidence[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        receipt = {"schema_version": 1, "run_id": run_id, "commit_sha": commit,
                   "suite": args.suite, "scenario_count": len(scenario_ids(SUITES[args.suite])),
                   "dirty_checkout": dirty, "passed": passed, "stages": stages,
                   "evidence_sha256": evidence,
                   "generated_at": datetime.now(timezone.utc).isoformat()}
        (output / "integration-receipt.json").write_text(json.dumps(receipt, indent=2),
                                                        encoding="utf-8")
        print(json.dumps({"passed": passed, "output": str(output), "commit_sha": commit}))


if __name__ == "__main__":
    raise SystemExit(main())
