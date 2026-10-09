$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$git = Get-Command git.exe -ErrorAction Stop
$gitRoot = Split-Path -Parent (Split-Path -Parent $git.Source)
$bash = Join-Path $gitRoot 'bin/bash.exe'
if (-not (Test-Path -LiteralPath $bash)) { throw 'Git for Windows Bash is required.' }
Push-Location $root
try {
    & $bash --noprofile --norc scripts/check.sh
    if ($LASTEXITCODE -ne 0) { throw "Validation failed: $LASTEXITCODE" }
} finally { Pop-Location }
