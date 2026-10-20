#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# Bootstrap into ignored, project-local caches only; no global configuration changes.
if ! command -v uv >/dev/null 2>&1; then
  python3 -m venv .themasterplan/cache/check-tools
  .themasterplan/cache/check-tools/bin/python -m pip install --disable-pip-version-check uv==0.11.23
  export PATH="$PWD/.themasterplan/cache/check-tools/bin:$PATH"
fi
if ! command -v node >/dev/null 2>&1 || (( $(node -p 'process.versions.node.split(".")[0]') < 24 )); then
  npm install --prefix .themasterplan/cache/node --no-save --package-lock=false node@24.17.0
  export PATH="$PWD/.themasterplan/cache/node/node_modules/.bin:$PATH"
fi
uv sync --project apps/api --locked --extra worker
uv run --project apps/api --locked --extra worker python .themasterplan/bin/themasterplan.py verify --root .
# CI must exercise Docker; local users may opt in with this same variable.
if [[ "${CI:-}" == "true" ]]; then export PRIVACYTRACE_DOCKER_TESTS=1; fi
if [[ "${PRIVACYTRACE_DOCKER_TESTS:-0}" == "1" ]]; then
  uv run --project apps/api --locked --extra worker python - <<'PY'
from pathlib import Path
import subprocess
from privacytrace.isolated_scan import docker_prefix
prefix = docker_prefix()
root = str(Path.cwd())
if prefix[0].lower().endswith("wsl.exe"):
    root = subprocess.check_output(["wsl.exe", "-d", "Ubuntu-24.04", "--exec", "wslpath", "-a", root], text=True).strip()
subprocess.run(prefix + ["build", "--file", root + "/apps/api/worker.Dockerfile", "--tag", "privacytrace-worker:s1", root], check=True)
PY
fi
uv run --project apps/api --locked --extra worker pytest apps/api/tests -q -p no:cacheprovider
uv run --project apps/api --locked --extra worker pytest tests/e2e -q -p no:cacheprovider
uv run --project apps/api --locked --extra worker ruff check apps/api/src apps/api/tests scripts/export-schema.py scripts/verify_workflow.py scripts/build-dataset.py scripts/metrics-user-study.py scripts/validate-trace.py scripts/verify-run-ledger.py scripts/generate-synthetic-pt907.py scripts/verify-user-study-pack.py scripts/controlled/location_reference.py scripts/verify-controlled-locations.py
# deploy/ and tests/e2e/ have no pyproject.toml above them, so name the repo
# config explicitly; otherwise Ruff applies whatever config it falls back to.
uv run --project apps/api --locked --extra worker ruff check --config apps/api/pyproject.toml deploy tests/e2e
uv run --project apps/api --locked --extra worker python scripts/verify-user-study-pack.py
uv run --project apps/api --locked --extra worker python scripts/export-schema.py
git diff --exit-code -- packages/contracts apps/web/src/contracts.generated.ts
npm ci
npm run test --workspace @privacytrace/web
npm run build
printf '\nPrivacyTrace checks passed.\n'
