#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
: "${PRIVACYTRACE_TEST_DATABASE_URL:?Explicit disposable PostgreSQL runtime URL required}"
: "${PRIVACYTRACE_TEST_MIGRATION_DATABASE_URL:?Separate migration URL required}"
command -v redis-server >/dev/null || { printf 'Real redis-server is required\n' >&2; exit 1; }
export PRIVACYTRACE_REDIS_TESTS=1
uv run --project apps/api --locked --extra worker --extra runtime python -B -m pytest \
  apps/api/tests/test_postgres_storage.py apps/api/tests/test_postgres_outbox.py \
  apps/api/tests/test_queue_runtime.py -q -p no:cacheprovider --tb=short -ra
