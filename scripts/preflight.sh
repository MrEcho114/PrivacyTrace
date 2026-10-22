#!/usr/bin/env bash
# Fast pre-publish gate for the mistakes that otherwise surface only in CI.
#
# The authoritative, slow check is `bash scripts/check.sh` (uv sync + pytest +
# npm ci + build). This script runs the subset that catches lint and syntax
# errors in the files a branch actually changes, so a broken branch is not
# published and does not burn a full CI cycle.
#
# Usage: bash scripts/preflight.sh [base-ref]
#   base-ref defaults to the merge base with origin/main, then HEAD~1.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1

base="${1:-}"
if [[ -z "$base" ]]; then
  if git rev-parse --verify --quiet origin/main >/dev/null; then
    base="$(git merge-base HEAD origin/main 2>/dev/null || echo "")"
  fi
  [[ -n "$base" ]] || base="$(git rev-parse HEAD~1 2>/dev/null || git rev-parse HEAD)"
fi

# Committed-on-branch changes plus anything still uncommitted or untracked.
files="$(mktemp)"
trap 'rm -f "$files"' EXIT
{
  git diff --name-only --diff-filter=ACMR "$base"...HEAD 2>/dev/null || true
  git status --porcelain 2>/dev/null |
    awk '{ if ($1 ~ /^R/) { print $3 } else { $1 = ""; sub(/^ +/, ""); print } }'
} | sed '/^$/d' | sort -u > "$files"

fail=0
report() { printf '== %s\n' "$*"; }
run() { "$@" || fail=1; }

report "base=$base changed=$(wc -l < "$files") files"

# 1. Ruff over the deployment tree with the repo's own config: the same command
#    CI runs in .github/workflows/deployment.yml.
if command -v ruff >/dev/null 2>&1; then
  run ruff check --config apps/api/pyproject.toml deploy tests/e2e
elif command -v uv >/dev/null 2>&1; then
  run uv run --project apps/api --locked --extra worker \
    ruff check --config apps/api/pyproject.toml deploy tests/e2e
else
  printf 'preflight: ruff not found; install ruff or run bash scripts/check.sh\n'
  fail=1
fi

# 2. Syntax-only checks for changed files (compile in memory; no bytecode or
#    other side effects in the working tree).
while IFS= read -r file; do
  [[ -f "$file" ]] || continue
  case "$file" in
    *.py)
      report "py-syntax $file"
      python3 -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "$file" || fail=1
      ;;
    *.cjs | *.js | *.mjs)
      report "node --check $file"
      node --check "$file" || fail=1
      ;;
    *.sh)
      report "bash -n $file"
      bash -n "$file" || fail=1
      ;;
  esac
done < "$files"

if [[ "$fail" -ne 0 ]]; then
  printf '\npreflight: FAILED. Fix the above before publishing; the full gate is bash scripts/check.sh.\n'
  exit 1
fi
printf '\npreflight: passed. Full gate before merge: bash scripts/check.sh\n'
