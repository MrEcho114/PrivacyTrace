param(
    [Parameter(Mandatory = $true)][string]$Serial,
    [string]$Adb = 'adb',
    [string]$Receipt
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$receiptPath = $null
$temporaryReceipt = $null
try {
    # Invalidate a previous success before doing anything that can fail this run.
    # Resolve relative receipts against this script's directory, as before.
    if ($Receipt) {
        $parent = Split-Path -Path $Receipt -Parent
        if (-not $parent) { $parent = '.' }
        $receiptDir = (Resolve-Path -LiteralPath $parent -ErrorAction Stop).ProviderPath
        $receiptName = Split-Path -Path $Receipt -Leaf
        if (-not $receiptName -or $receiptName -eq '.' -or $receiptName -eq '..') {
            throw 'Receipt must name a file.'
        }
        $receiptPath = Join-Path $receiptDir $receiptName
        if (Test-Path -LiteralPath $receiptPath -PathType Container) {
            throw 'Receipt path must not be a directory.'
        }
        if (Test-Path -LiteralPath $receiptPath) {
            Remove-Item -LiteralPath $receiptPath -Force -ErrorAction Stop
        }
    }

    function Invoke-ProbeAdb([string[]]$ProbeArguments) {
        $output = & $Adb -s $Serial @ProbeArguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw 'ADB operation failed; no passing device receipt produced.' }
        return ($output -join "`n")
    }
    $paths = @(
        'app/build/outputs/apk/debug/app-debug.apk',
        'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk',
        'fixture/build/outputs/apk/debug/fixture-debug.apk',
        'fixture-feature/build/outputs/apk/debug/fixture_feature-debug.apk'
    )
    foreach ($path in $paths) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'Build all probe APKs first.' }
    }
    if ((Invoke-ProbeAdb -ProbeArguments @('get-state')).Trim() -ne 'device') { throw 'Selected device is not ready.' }
    Invoke-ProbeAdb -ProbeArguments @('install', '-r', $paths[0]) | Out-Null
    Invoke-ProbeAdb -ProbeArguments @('install', '-r', '-t', $paths[1]) | Out-Null
    Invoke-ProbeAdb -ProbeArguments @('install-multiple', '-r', $paths[2], $paths[3]) | Out-Null
    foreach ($target in @(
        @{ Package = 'org.privacytrace.probe'; Parts = 1 },
        @{ Package = 'org.privacytrace.probe.fixture'; Parts = 2 }
    )) {
        $output = Invoke-ProbeAdb -ProbeArguments @(
            'shell', 'am', 'instrument', '-w',
            '-e', 'probePackage', $target.Package,
            '-e', 'expectedParts', [string]$target.Parts,
            'org.privacytrace.probe.test/org.privacytrace.probe.ProbeInstrumentation'
        )
        if ($output -notmatch '(?m)^INSTRUMENTATION_CODE: -1\s*$' -or
            $output -notmatch "PASS: selected visible package, $($target.Parts) parts, stable digests") {
            throw 'Device expectations failed; no passing device receipt produced.'
        }
    }
    $sourceCommit = & git rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot bind device receipt to a source commit.' }
    $sourceChanges = @(& git status --porcelain=v1)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect source state.' }
    $result = [ordered]@{
        schema = 'privacytrace-android-probe-device-v1'
        source_commit = $sourceCommit.Trim()
        source_dirty = $sourceChanges.Count -gt 0
        emulator = (Invoke-ProbeAdb -ProbeArguments @('shell', 'getprop', 'ro.kernel.qemu')).Trim() -eq '1'
        android_api = (Invoke-ProbeAdb -ProbeArguments @('shell', 'getprop', 'ro.build.version.sdk')).Trim()
        android_release = (Invoke-ProbeAdb -ProbeArguments @('shell', 'getprop', 'ro.build.version.release')).Trim()
        cases = @('single_self_app_uid', 'external_base_plus_installed_feature_app_uid')
        result = 'PASS'
        apk_sha256 = @($paths | ForEach-Object { (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant() })
        unverified = @('installation_update_race', 'unreadable_packages', 'oem_matrix', 'tauri_bridge', 'remote_upload')
    }
    $json = $result | ConvertTo-Json -Depth 4
    if ($receiptPath) {
        # Write in the same directory, then publish via a single rename.
        # A failed write leaves no partial PASS at the requested receipt path.
        $temporaryReceipt = Join-Path $receiptDir ('.{0}.{1}.tmp' -f $receiptName, [Guid]::NewGuid().ToString('N'))
        [System.IO.File]::WriteAllText($temporaryReceipt, $json, [System.Text.UTF8Encoding]::new($false))
        [System.IO.File]::Move($temporaryReceipt, $receiptPath)
        $temporaryReceipt = $null
    }
    $json
} finally {
    if ($temporaryReceipt -and (Test-Path -LiteralPath $temporaryReceipt -PathType Leaf)) {
        Remove-Item -LiteralPath $temporaryReceipt -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
