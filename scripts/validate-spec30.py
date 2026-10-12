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
from privacytrace.isolated_scan import docker_prefix

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cache", type=Path, default=ROOT / "tmp/toolchain")
    parser.add_argument("--cached", action="store_true")
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
        with (output / (name + ".log")).open("wb") as log:
            try:
                result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                        env=env, timeout=timeout, check=False)
                code = result.returncode
            except (OSError, subprocess.TimeoutExpired):
                code = -1
        stages.append({"stage": name, "exit_code": code,
                       "elapsed_seconds": time.monotonic() - started})
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
        common = ["--cache", args.cache, *(["--cached"] if args.cached else [])]
        built = stage("build-a", python("build-controlled-apks.py", *common, "--output", build_a))
        rebuilt = built and stage("build-b", python("build-controlled-apks.py", "--cache",
                                                   args.cache, "--cached", "--output", build_b))
        rebuild_error = "BUILD_A_FAILED" if not built else ("BUILD_B_FAILED" if not rebuilt else None)
        if rebuild_error:
            stages[-1]["error_code"] = rebuild_error
        if rebuilt:
            try:
                first = json.loads((build_a / "build-receipt.json").read_bytes())
                second = json.loads((build_b / "build-receipt.json").read_bytes())
                frozen = json.loads(
                    (ROOT / "benchmarks/controlled/artifacts.lock.json").read_bytes()
                )
                if not (
                    first["apks"] == second["apks"] == frozen["apks"]
                    and first["source_hashes"] == second["source_hashes"]
                    == frozen["source_hashes"]
                ):
                    rebuild_error = "BUILD_ARTIFACT_HASH_MISMATCH"
            except (OSError, ValueError, KeyError, TypeError):
                rebuild_error = "BUILD_ARTIFACT_RECEIPT_INVALID"
            stages.append({
                "stage": "rebuild-hashes",
                "exit_code": 1 if rebuild_error else 0,
                **({"error_code": rebuild_error} if rebuild_error else {}),
            })
        # An untrusted build must never enter the actual worker/prediction path.
        if rebuild_error is None and not stage("worker-build", [*docker_prefix(), "build", "-f",
                                                             daemon_path(ROOT / "apps/api/worker.Dockerfile"),
                                                             "-t", "privacytrace-worker:s1", daemon_path(ROOT)]):
            rebuild_error = "WORKER_BUILD_FAILED"
            stages[-1]["error_code"] = rebuild_error
        # Retain 18 result rows on failure; a mismatched build is never scanned.
        comparison_command = [
            sys.executable, "-m", "privacytrace.benchmark", "run",
            "--artifacts", str(build_a), "--output", str(output / "evaluation"),
        ]
        if rebuild_error is not None:
            comparison_command.extend(["--blocked-error", rebuild_error])
        compared = stage("six-scenarios", comparison_command)
        if not (built and rebuilt and compared) or any(item["exit_code"] for item in stages):
            return 1
        env = {**os.environ, "PRIVACYTRACE_CONTROLLED_ARTIFACTS": str(build_a)}
        if not stage("source-cli-regressions", [sys.executable, "-m", "pytest",
                     "apps/api/tests/test_controlled_source_cli.py", "-q", "-p", "no:cacheprovider"],
                     env=env):
            return 1
        npm = "npm.cmd" if os.name == "nt" else "npm"
        if not stage("web-build", [npm, "run", "build"]):
            return 1
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
                   "dirty_checkout": dirty, "passed": passed, "stages": stages,
                   "evidence_sha256": evidence,
                   "generated_at": datetime.now(timezone.utc).isoformat()}
        (output / "integration-receipt.json").write_text(json.dumps(receipt, indent=2),
                                                        encoding="utf-8")
        print(json.dumps({"passed": passed, "output": str(output), "commit_sha": commit}))


if __name__ == "__main__":
    raise SystemExit(main())
