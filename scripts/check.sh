#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# Bootstrap into ignored, project-local caches only; no global configuration changes.
if ! command -v uv >/dev/null 2>&1; then
  venv=.themasterplan/cache/check-tools
  bootstrap_python=$(command -v python3 || command -v python || true)
  if [[ -z "$bootstrap_python" ]]; then
    printf '%s\n' 'scripts/check.sh: no python3/python on PATH; install Python or uv first.' >&2
    exit 1
  fi
  "$bootstrap_python" -m venv "$venv"
  # A Windows venv puts its interpreter in Scripts/, a POSIX venv in bin/.
  if [[ -x "$venv/bin/python" ]]; then
    venv_bin="$venv/bin"
    venv_python="$venv/bin/python"
  elif [[ -x "$venv/Scripts/python.exe" ]]; then
    venv_bin="$venv/Scripts"
    venv_python="$venv/Scripts/python.exe"
  else
    printf '%s\n' "scripts/check.sh: unexpected venv layout under $venv" >&2
    exit 1
  fi
  "$venv_python" -m pip install --disable-pip-version-check uv==0.11.23
  export PATH="$PWD/$venv_bin:$PATH"
fi
if ! command -v node >/dev/null 2>&1 || (( $(node -p 'process.versions.node.split(".")[0]') < 24 )); then
  npm install --prefix .themasterplan/cache/node --no-save --package-lock=false node@24.17.0
  export PATH="$PWD/.themasterplan/cache/node/node_modules/.bin:$PATH"
fi
# #287: celery lives in the api `runtime` extra, so the authoritative check must
# install both extras; otherwise test_runtime_worker.py skips its worker protocol
# assertions at import and the gate stays green without covering them. Every uv
# command carries the same extras so the outcome does not depend on `uv run`
# keeping whatever a previous `uv sync` installed (sync prunes, run does not).
# Cost: celery[redis]==5.6.3 plus its transitive packages in this check-only
# virtualenv; apps/api/worker.Dockerfile still installs the worker extra alone,
# so the release image is unchanged.
api_uv_extras=(--extra worker --extra runtime)
uv sync --project apps/api --locked "${api_uv_extras[@]}"
uv run --project apps/api --locked "${api_uv_extras[@]}" python .themasterplan/bin/themasterplan.py verify --root .
# CI must exercise Docker; local users may opt in with this same variable.
if [[ "${CI:-}" == "true" ]]; then export PRIVACYTRACE_DOCKER_TESTS=1; fi
if [[ "${PRIVACYTRACE_DOCKER_TESTS:-0}" == "1" ]]; then
  uv run --project apps/api --locked "${api_uv_extras[@]}" python - <<'PY'
from pathlib import Path
import subprocess
from privacytrace.isolated_scan import docker_prefix
from privacytrace.wsl import wsl_distro
prefix = docker_prefix()
root = str(Path.cwd())
if prefix[0].lower().endswith("wsl.exe"):
    root = subprocess.check_output(["wsl.exe", "-d", wsl_distro(), "--exec", "wslpath", "-a", root], text=True).strip()
subprocess.run(prefix + ["build", "--file", root + "/apps/api/worker.Dockerfile", "--tag", "privacytrace-worker:s1", root], check=True)
PY
fi
uv run --project apps/api --locked "${api_uv_extras[@]}" pytest apps/api/tests -q -p no:cacheprovider
uv run --project apps/api --locked "${api_uv_extras[@]}" pytest tests/e2e -q -p no:cacheprovider
uv run --project apps/api --locked "${api_uv_extras[@]}" ruff check apps/api/src apps/api/tests scripts/export-schema.py scripts/verify_workflow.py scripts/build-dataset.py scripts/metrics-user-study.py scripts/validate-trace.py scripts/verify-run-ledger.py scripts/generate-synthetic-pt907.py scripts/verify-user-study-pack.py scripts/controlled/location_reference.py scripts/verify-controlled-locations.py
# deploy/ and tests/e2e/ have no pyproject.toml above them, so name the repo
# config explicitly; otherwise Ruff applies whatever config it falls back to.
uv run --project apps/api --locked "${api_uv_extras[@]}" ruff check --config apps/api/pyproject.toml deploy tests/e2e
uv run --project apps/api --locked "${api_uv_extras[@]}" python scripts/verify-user-study-pack.py
uv run --project apps/api --locked "${api_uv_extras[@]}" python scripts/export-schema.py
git diff --exit-code -- packages/contracts apps/web/src/contracts.generated.ts
# #169: brand assets are committed sources; web copies must stay byte-identical
# and the Android icon overlay must be idempotent, including its failure cases.
# Node only: no Android toolchain, no PowerShell, same result on Linux CI.
node scripts/verify-brand-assets.cjs
node --test scripts/run-powershell.test.cjs
npm ci
npm run test --workspace @privacytrace/web
npm run build
printf '\nPrivacyTrace checks passed.\n'
