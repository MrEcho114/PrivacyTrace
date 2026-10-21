param(
    [Parameter(Mandatory = $true)][string]$CaseFile,
    [Parameter(Mandatory = $true)][string]$EvidenceDir,
    [string]$Serial = '<SERIAL>',
    [string]$Adb = '${ADB}',
    [int]$DevicePort = 29443,
    [int]$HostPort = 28443,
    [string]$PreflightScript = '${WORKSPACE}/tmp/issue129-acceptance-20261021/lab/preflight.sh',
    [switch]$SkipPreflight
)
$ErrorActionPreference = 'Stop'
$repo = '${WORKSPACE}'
$driver = Join-Path $repo 'tmp\issue129-acceptance-20261021\driver'

if (-not $SkipPreflight) {
    Write-Host '[0/3] lab preflight (repair policy egress, verify mock/model)'
    & wsl -d PrivacyTrace73-Control -u root --exec bash $PreflightScript 2>&1 | Out-Host
}

Write-Host "[1/3] reset client and wire adb ($Serial)"
& $Adb -s $Serial shell am force-stop org.privacytrace.mobile | Out-Null
& $Adb -s $Serial shell pm clear org.privacytrace.mobile | Out-Null
& $Adb -s $Serial reverse "tcp:$DevicePort" "tcp:$HostPort" | Out-Null
& $Adb -s $Serial shell am start -n org.privacytrace.mobile/.MainActivity | Out-Null
Start-Sleep -Seconds 9

Write-Host '[2/3] locate WebView devtools socket'
$socket = (& $Adb -s $Serial shell "cat /proc/net/unix | grep -o 'webview_devtools_remote_[0-9]*'") -join ''
if (-not $socket) { throw 'NO_WEBVIEW_SOCKET' }
$pidValue = ($socket -replace 'webview_devtools_remote_', '').Trim()
& $Adb -s $Serial forward --remove-all | Out-Null
& $Adb -s $Serial forward tcp:9222 "localabstract:webview_devtools_remote_$pidValue" | Out-Null
Write-Host "webview pid=$pidValue"

Write-Host '[3/3] run client case'
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
$env:PT_ADB = $Adb
$env:PT_ADB_SERIAL = $Serial
$env:PT_EVIDENCE_DIR = $EvidenceDir
Set-Location $driver
& node client-case.cjs $CaseFile
exit $LASTEXITCODE
