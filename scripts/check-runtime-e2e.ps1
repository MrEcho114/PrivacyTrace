$ErrorActionPreference = 'Stop'
foreach ($name in @('PRIVACYTRACE_TEST_DATABASE_URL', 'PRIVACYTRACE_TEST_MIGRATION_DATABASE_URL',
                    'PRIVACYTRACE_E2E_WSL_DISTRO', 'PRIVACYTRACE_E2E_WSL_MARKER',
                    'PRIVACYTRACE_E2E_LINUX_REPO')) {
    if (-not [Environment]::GetEnvironmentVariable($name)) {
        throw "Explicit authorized disposable E2E configuration required: $name"
    }
}
$root = Split-Path -Parent $PSScriptRoot
$previous = $env:PRIVACYTRACE_E2E_WSL_TESTS
Push-Location $root
try {
    $env:PRIVACYTRACE_E2E_WSL_TESTS = '1'
    & uv run --project apps/api --locked --extra worker --extra runtime python -B -m pytest `
        apps/api/tests/test_runtime_e2e.py -q -p no:cacheprovider --tb=short -ra
    if ($LASTEXITCODE -ne 0) { throw "Actual runtime E2E failed: $LASTEXITCODE" }
} finally {
    $env:PRIVACYTRACE_E2E_WSL_TESTS = $previous
    Pop-Location
}
