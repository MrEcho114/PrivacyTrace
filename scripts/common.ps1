$ErrorActionPreference = 'Stop'
$script:PrivacyTraceRoot = Split-Path -Parent $PSScriptRoot

function Get-PrivacyTraceTool([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $runtimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
    if ($Name -eq 'npm.cmd') {
        $candidate = Join-Path $runtimeRoot 'node\bin\npm.cmd'
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    if ($Name -eq 'uv') {
        $candidate = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
        if (Test-Path -LiteralPath $candidate) {
            $pythonCandidate = Join-Path $runtimeRoot 'python\python.exe'
            if (Test-Path -LiteralPath $pythonCandidate) { $env:UV_PYTHON = $pythonCandidate }
            return $candidate
        }
    }
    throw "Required tool '$Name' is missing. See README for installation."
}

function Invoke-PrivacyTraceTool([string]$Tool, [string[]]$Arguments) {
    & $Tool @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE" }
}
