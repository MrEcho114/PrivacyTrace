. "$PSScriptRoot\common.ps1"
$npmTool = Get-PrivacyTraceTool 'npm.cmd'
Push-Location $script:PrivacyTraceRoot
try { Invoke-PrivacyTraceTool $npmTool @('run', 'dev') } finally { Pop-Location }
