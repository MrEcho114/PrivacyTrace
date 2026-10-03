. "$PSScriptRoot\common.ps1"
Push-Location $script:PrivacyTraceRoot
try {
    $npmTool = Get-PrivacyTraceTool 'npm.cmd'
    $uvTool = Get-PrivacyTraceTool 'uv'
    Invoke-PrivacyTraceTool $npmTool @('ci')
    Invoke-PrivacyTraceTool $uvTool @('sync', '--project', 'apps/api', '--locked', '--extra', 'worker')
} finally { Pop-Location }
