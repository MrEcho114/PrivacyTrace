$ErrorActionPreference = 'Stop'
if (-not $env:PRIVACYTRACE_TEST_DATABASE_URL -or
    -not $env:PRIVACYTRACE_TEST_MIGRATION_DATABASE_URL) {
    throw 'Set both disposable PostgreSQL test URLs; this check must not silently skip.'
}
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    & uv run --project apps/api --locked --extra worker pytest `
        apps/api/tests/test_postgres_storage.py apps/api/tests/test_postgres_outbox.py `
        apps/api/tests/test_postgres_execution.py `
        -q -p no:cacheprovider --tb=short -ra
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL verification failed: $LASTEXITCODE" }
} finally { Pop-Location }
