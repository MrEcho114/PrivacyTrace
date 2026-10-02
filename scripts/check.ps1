. "$PSScriptRoot\common.ps1"
$uvTool = Get-PrivacyTraceTool 'uv'
$npmTool = Get-PrivacyTraceTool 'npm.cmd'
Push-Location $script:PrivacyTraceRoot
try {
    Invoke-PrivacyTraceTool $uvTool @('run', '--project', 'apps/api', '--locked', 'pytest')
    Invoke-PrivacyTraceTool $uvTool @('run', '--project', 'apps/api', '--locked', 'ruff', 'check', 'apps/api/src', 'apps/api/tests')
    Invoke-PrivacyTraceTool $npmTool @('run', 'build')
} finally { Pop-Location }
