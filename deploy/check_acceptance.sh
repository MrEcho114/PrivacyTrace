#!/usr/bin/env bash
# Real, disposable same-host acceptance. The recorded dedicated-host waiver is
# explicit; no public DNS, ACME account, registry push or production switch.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
# `all` is the single-round gate and stays the default. The two split phases let a
# workflow run the collectors as parallel jobs: R1-R4 (deployment, business loop,
# isolation, fault recovery) need both owned instances and no previous-commit
# image; R5-R6 (backup recovery, capacity and secret audit) run on one instance but
# need the previous api image for the rollback drill. Receipts, the FAILED_LAB
# cleanup path and the exit semantics are identical in every phase.
phase=${1:-all}
case "$phase" in
  all) collectors=r1,r2,r3,r4,r5,r6; laboratories=2; previous_api=1 ;;
  r1-r4) collectors=r1,r2,r3,r4; laboratories=2; previous_api=0 ;;
  r5-r6) collectors=r5,r6; laboratories=1; previous_api=1 ;;
  *)
    echo "usage: $0 [all|r1-r4|r5-r6]" >&2
    exit 2
    ;;
esac
echo "phase: $phase (collectors $collectors)"
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$PWD"
test "$(id -u)" = 0 || { echo 'Run on disposable Linux with root for file ownership'; exit 2; }
test -z "$(git status --porcelain --untracked-files=normal)" || { echo 'Clean committed source required'; exit 2; }
sha=$(git rev-parse HEAD)
baseline=201d34da78028978c98f3077d0a940f4882c7ca9
temporary=$(mktemp -d /var/tmp/pt81-build-XXXXXXXX)
receipt_dir="$PWD/tmp/deployment-acceptance"
mkdir -p "$receipt_dir"
states=()
cleanup() {
  result=$?
  # Failed provisioning prints an owned state path before returning nonzero.
  # Include that state even though the successful-up path was never reached.
  for log in "$temporary"/up-*.log; do
    test -f "$log" || continue
    while IFS= read -r failed; do
      test -n "$failed" && states+=("$failed")
    done < <(sed -n 's/^FAILED_LAB=//p' "$log")
  done
  for state in "${states[@]}"; do
    if ! python3 -m deploy.acceptance.provision down --state "$state" --purge; then
      echo "Cleanup failed; retained owned laboratory: $state" >&2
      result=1
    fi
  done
  if test -d "$temporary/baseline"; then
    git worktree remove "$temporary/baseline" || result=1
  fi
  if test -d "$temporary/baseline"; then
    echo "Cleanup failed; retained baseline worktree: $temporary/baseline" >&2
  fi
  # Keep a failed worktree removal recoverable. Otherwise remove only our
  # mktemp-generated, non-symlink build directory (CLI copy and local logs).
  if ! test -d "$temporary/baseline" && [[ "$temporary" =~ ^/var/tmp/pt81-build-[A-Za-z0-9]{8}$ ]] \
      && test -d "$temporary" && ! test -L "$temporary"; then
    rm -r -- "$temporary" || result=1
  fi
  exit "$result"
}
trap cleanup EXIT
mkdir "$temporary/docker-client"
cp "$(command -v docker)" "$temporary/docker-client/docker"
cli_sha=$(sha256sum "$temporary/docker-client/docker" | cut -d ' ' -f1)
build_args=(--build-arg "VCS_REF=$sha")
# Local preloaded transport aliases are optional. CI uses the Dockerfile's
# locked registry digests; callers must audit any explicitly supplied override.
for variable in PYTHON NODE CADDY; do
  key="PT_BUILD_${variable}_IMAGE"
  if test -n "${!key:-}"; then build_args+=(--build-arg "${variable}_IMAGE=${!key}"); fi
done
echo 'build: current api, web, runner, scanner'
docker build -f deploy/Dockerfile --target api "${build_args[@]}" -t privacytrace-api:issue81-test .
docker build -f deploy/Dockerfile --target web "${build_args[@]}" -t privacytrace-web:issue81-test .
docker build -f deploy/Runner.Dockerfile --build-arg API_IMAGE=privacytrace-api:issue81-test \
  --build-arg "DOCKER_CLI_SHA256=$cli_sha" --build-context "docker-client=$temporary/docker-client" \
  -t privacytrace-runner:issue81-test .
docker build -f deploy/Scan.Dockerfile --build-arg API_IMAGE=privacytrace-api:issue81-test \
  -t privacytrace-scanner:issue81-test .
if test "$previous_api" = 1; then
  echo "build: previous api from the $baseline worktree"
  git worktree add --detach "$temporary/baseline" "$baseline"
  baseline_args=(--build-arg "VCS_REF=$baseline")
  if test -n "${PT_BUILD_PYTHON_IMAGE:-}"; then baseline_args+=(--build-arg "PYTHON_IMAGE=$PT_BUILD_PYTHON_IMAGE"); fi
  docker build -f "$temporary/baseline/deploy/Dockerfile" --target api "${baseline_args[@]}" \
    -t privacytrace-api:issue81-previous "$temporary/baseline"
fi
echo "provision: $laboratories owned instance(s)"
for index in $(seq 1 "$laboratories"); do
  # Provisioning output is redirected, so announce the phase explicitly: the CI log
  # otherwise goes silent for the whole simulation.
  echo "provision $index/$laboratories"
  python3 -m deploy.acceptance.provision up --scanner-image privacytrace-scanner:issue81-test \
    > "$temporary/up-$index.log"
  state=$(sed -n 's/^LAB_STATE=//p' "$temporary/up-$index.log")
  test -n "$state"
  states+=("$state")
done
echo "laboratory: $collectors"
lab_args=(--state "${states[0]}" --only "$collectors" --receipt-dir "$receipt_dir")
test "${#states[@]}" -lt 2 || lab_args+=(--other-state "${states[1]}")
test "$previous_api" = 0 || lab_args+=(--previous-api-image privacytrace-api:issue81-previous)
python3 -m deploy.acceptance.laboratory "${lab_args[@]}"
