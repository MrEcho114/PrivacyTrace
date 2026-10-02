. "$PSScriptRoot\common.ps1"
$uvTool = Get-PrivacyTraceTool 'uv'
Push-Location $script:PrivacyTraceRoot
try {
    Invoke-PrivacyTraceTool $uvTool @('run', '--project', 'apps/api', '--locked', 'uvicorn', 'privacytrace.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload')
} finally { Pop-Location }
