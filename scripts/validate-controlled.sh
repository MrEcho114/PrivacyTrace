#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
: "${ANDROID_HOME:?Provide an installed Android SDK}"
: "${JAVA_HOME:?Provide the locked JDK}"
run=(uv run --project apps/api --locked --extra worker python -m)
out=tmp/pt910-acceptance
"${run[@]}" privacytrace.controlled_compare freeze \
  --suite-dir benchmarks/controlled --output "$out/frozen.json"
git rev-parse HEAD > "$out/commit.txt"
failed=0
for case_id in C02 C06; do
  "${run[@]}" privacytrace.controlled_build --case-dir "benchmarks/controlled/$case_id" \
    --sdk "$ANDROID_HOME" --jdk "$JAVA_HOME" --output-dir "tmp/pt910-ci-build/$case_id"
  "${run[@]}" privacytrace.controlled run --case-dir "benchmarks/controlled/$case_id" \
    --build-receipt "tmp/pt910-ci-build/$case_id/build.json" \
    --output-dir "$out/$case_id" --store-dir data/pt910-ci-jobs \
    --job-id "pt910-$case_id" || failed=1
done
"${run[@]}" privacytrace.controlled_compare compare --freeze "$out/frozen.json" \
  --labels benchmarks/controlled/ground-truth.json \
  --predictions "$out/C02/predictions.json" "$out/C06/predictions.json" \
  --output-dir "$out/comparison"
exit "$failed"
