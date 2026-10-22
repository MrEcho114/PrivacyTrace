#!/usr/bin/env bash
# Print the environment facts agents otherwise guess wrong about.
#
# Sessions inherit stale lore ("git is blocked here", "containers have no
# egress") that outlives the condition. This probe reports what is true right
# now, from the shell it is run in, before freezing a head or rebuilding a
# package. Missing capabilities are reported as MISSING, never guessed.
#
# Usage: bash scripts/agent-env-probe.sh [--docker]
#   --docker also runs a one-shot container egress check (slow, needs a daemon).
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
want_docker=0
[[ "${1:-}" == "--docker" ]] && want_docker=1

section() { printf '\n== %s\n' "$*"; }

section "repo"
printf 'branch   %s\n' "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
printf 'head     %s\n' "$(git rev-parse HEAD 2>/dev/null || echo unknown)"
printf 'dirty    %s\n' "$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

section "remote"
if timeout 20 git ls-remote --heads origin main >/dev/null 2>&1; then
  printf 'git-fetch  reachable; origin/main=%s\n' \
    "$(git ls-remote --heads origin main 2>/dev/null | awk '{print substr($1,1,12)}')"
else
  printf 'git-fetch  UNREACHABLE (fall back to gh api for reads; retry before publishing)\n'
fi
gh auth status 2>&1 | sed -n '1,3p' | sed 's/^/gh        /'

section "tools"
for tool in uv ruff node npm python3 docker adb gh git; do
  path="$(command -v "$tool" 2>/dev/null || true)"
  printf '%-9s %s\n' "$tool" "${path:-MISSING}"
done
printf 'node-ver  %s\n' "$(node --version 2>/dev/null || echo unknown)"
printf 'ruff-ver  %s\n' "$(ruff --version 2>/dev/null || echo unknown)"

section "docker"
if docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
  printf 'daemon    %s\n' "$(docker info --format '{{.ServerVersion}}' 2>/dev/null)"
  printf 'proxies   %s\n' "$(docker info --format '{{json .HttpProxy}}' 2>/dev/null | head -c 200)"
  printf 'running   %s containers\n' "$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$want_docker" == "1" ]]; then
    if timeout 60 docker run --rm busybox sh -c 'wget -q -O- -T 10 http://example.com >/dev/null' 2>/dev/null; then
      printf 'egress    reachable\n'
    else
      printf 'egress    BLOCKED (check iptables FORWARD and daemon proxy injection)\n'
    fi
  fi
else
  printf 'daemon    UNREACHABLE from this shell (try: wsl -d Ubuntu-24.04 -u root -- docker info)\n'
fi

section "iptables FORWARD"
iptables -S FORWARD 2>/dev/null | sed -n '1,3p' || printf 'needs privilege (run inside the lab shell)\n'

section "android"
if command -v adb >/dev/null 2>&1; then
  adb devices 2>/dev/null | tail -n +2 | sed '/^$/d' | sed 's/^/device    /' || true
else
  printf 'adb       MISSING (MuMu ships its own adb; see docs/agents/local-environment.md)\n'
fi

section "existing artifacts (do not rebuild a head that is already packaged)"
ls -1 .scratch/package-final 2>/dev/null | sed -n '1,10p' | sed 's/^/package   /' || printf 'package   none\n'
ls -1 .scratch/lead/coldstart-*-receipts 2>/dev/null | sed -n '1,5p' | sed 's/^/receipts  /' || true

printf '\nProbe only reports facts; re-run it after any network, daemon, or device change.\n'
