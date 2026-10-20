param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9_.:-]+$')][string]$Serial,
    [Parameter(Mandatory = $true)][string]$UpdatedBaseApk,
    [Parameter(Mandatory = $true)][string]$UpdatedSplitApk,
    [string]$Adb = 'adb',
    [long]$BeforeVersion = 1,
    [long]$AfterVersion = 2
)
$ErrorActionPreference = 'Stop'
if ($BeforeVersion -eq $AfterVersion) { throw 'Two different fixture versions are required.' }
foreach ($path in @($UpdatedBaseApk, $UpdatedSplitApk)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Build both updated fixture APKs first.' }
}
$logRoot = Join-Path $PSScriptRoot '.gradle'
[System.IO.Directory]::CreateDirectory($logRoot) | Out-Null
$logPrefix = Join-Path $logRoot ('update-race-' + [Guid]::NewGuid().ToString('N'))
$process = $null
function Invoke-UpdateAdb([string[]]$ProbeArguments) {
    $output = & $Adb -s $Serial @ProbeArguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Controlled update ADB operation failed.' }
    return ($output -join "`n")
}
try {
    $startOptions = @{
        FilePath = (Get-Command $Adb -ErrorAction Stop).Source
        ArgumentList = @('-s', $Serial, 'shell', 'am', 'instrument', '-r', '-w',
            '-e', 'mode', 'update_race', '-e', 'beforeVersion', [string]$BeforeVersion,
            '-e', 'afterVersion', [string]$AfterVersion,
            'org.privacytrace.probe.test/org.privacytrace.probe.ProbeInstrumentation')
        RedirectStandardOutput = $logPrefix + '.stdout'
        RedirectStandardError = $logPrefix + '.stderr'
        PassThru = $true
    }
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) { $startOptions.WindowStyle = 'Hidden' }
    $process = Start-Process @startOptions
    $ready = $false
    $deadline = (Get-Date).AddSeconds(25)
    do {
        if ((Get-Content -LiteralPath ($logPrefix + '.stdout') -Raw) -match 'probe_checkpoint=SNAPSHOT_READY') {
            $ready = $true
            break
        }
        if ($process.HasExited) { break }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
    if (-not $ready) { throw 'Instrumentation did not reach the installation snapshot checkpoint.' }
    Invoke-UpdateAdb -ProbeArguments @('install-multiple', '-r', $UpdatedBaseApk, $UpdatedSplitApk) | Out-Null
    Invoke-UpdateAdb -ProbeArguments @('shell', 'run-as', 'org.privacytrace.probe', 'touch', 'cache/probe-update-continue') | Out-Null
    if (-not $process.WaitForExit(10000)) { throw 'Update instrumentation timed out.' }
    $output = Get-Content -LiteralPath ($logPrefix + '.stdout') -Raw
    if ($process.ExitCode -ne 0 -or $output -notmatch '(?m)^INSTRUMENTATION_CODE: -1\s*$' -or
        $output -notmatch 'PASS: installation update rejected code=(INSTALLATION_CHANGED|UNREADABLE)') {
        throw 'Installation update did not produce the expected complete-result rejection.'
    }
    $sourceCommit = & git -C $PSScriptRoot rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Cannot bind update receipt to a source commit.' }
    $sourceChanges = @(& git -C $PSScriptRoot status --porcelain=v1)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect source state.' }
    [ordered]@{
        schema = 'privacytrace-android-probe-update-v1'
        source_commit = $sourceCommit.Trim()
        source_dirty = $sourceChanges.Count -gt 0
        emulator = (Invoke-UpdateAdb -ProbeArguments @('shell', 'getprop', 'ro.kernel.qemu')).Trim() -eq '1'
        android_api = (Invoke-UpdateAdb -ProbeArguments @('shell', 'getprop', 'ro.build.version.sdk')).Trim()
        before_version = $BeforeVersion
        after_version = $AfterVersion
        result = 'PASS'
        rejection = [regex]::Match($output, 'rejected code=(\w+)').Groups[1].Value
        scheduling = 'test-only pause after actual installation snapshot; actual package replacement'
        unverified = @('unscheduled_race_timing', 'physical_devices', 'tauri_bridge', 'remote_upload')
    } | ConvertTo-Json -Depth 3
} finally {
    if ($process -and -not $process.HasExited) {
        try { Invoke-UpdateAdb -ProbeArguments @('shell', 'am', 'force-stop', 'org.privacytrace.probe') | Out-Null } catch { }
        if (-not $process.WaitForExit(5000)) { Stop-Process -Id $process.Id }
    }
}
