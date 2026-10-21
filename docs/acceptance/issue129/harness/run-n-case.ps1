param(
    [Parameter(Mandatory = $true)][string]$Mode,
    [Parameter(Mandatory = $true)][string]$EvidenceDir,
    [string]$Serial = '<SERIAL>',
    [string]$Adb = '${ADB}',
    [int]$DevicePort = 29443,
    [int]$HostPort = 28443
)
$ErrorActionPreference = 'Stop'
$driver = '${WORKSPACE}\tmp\issue129-acceptance-20261021\driver'
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null

function Count-Drafts {
    $out = & wsl -d PrivacyTrace73-Control -u root --exec bash ${WORKSPACE}/tmp/issue129-acceptance-20261021/lab/count-drafts.sh 2>$null
    return ("$out").Trim()
}

$before = Count-Drafts
Write-Host "drafts-before=$before"
$env:PT_ADB = $Adb
$env:PT_ADB_SERIAL = $Serial
$env:PT_EVIDENCE_DIR = $EvidenceDir
$env:PT_N_ORIGIN = "https://localhost:$DevicePort"
$env:PT_N_DEVICE_PORT = "$DevicePort"
$env:PT_N_HOST_PORT = "$HostPort"
$env:PT_N_BASE_V2 = "${WORKSPACE}\tmp\issue129-acceptance-20261021\variants\base-v2.apk"
Set-Location $driver
& node n-cases.cjs $Mode
$code = $LASTEXITCODE
$after = Count-Drafts
Write-Host "drafts-after=$after"
@{
    mode = $Mode
    drafts_before = $before
    drafts_after = $after
    node_exit = $code
    serial = $Serial
    origin = "https://localhost:$DevicePort"
} | ConvertTo-Json | Set-Content -Path (Join-Path $EvidenceDir "n-summary.json") -Encoding UTF8
exit $code
