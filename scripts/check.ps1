. "$PSScriptRoot\common.ps1"
$uvTool = Get-PrivacyTraceTool 'uv'
$npmTool = Get-PrivacyTraceTool 'npm.cmd'
Push-Location $script:PrivacyTraceRoot
try {
    Invoke-PrivacyTraceTool $uvTool @('run', '--project', 'apps/api', '--locked', '--extra', 'worker', 'pytest', 'apps/api/tests')
    Invoke-PrivacyTraceTool $uvTool @('run', '--project', 'apps/api', '--locked', '--extra', 'worker', 'ruff', 'check', 'apps/api/src', 'apps/api/tests', 'scripts/export-schema.py')
    Invoke-PrivacyTraceTool $npmTool @('run', 'build')
} finally { Pop-Location }
