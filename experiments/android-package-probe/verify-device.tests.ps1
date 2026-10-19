# Deterministic receipt lifecycle regression. Uses fake APK bytes and mocked ADB,
# never connects to or installs anything on an Android device.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required for receipt provenance checks.' }

$testRoot = Join-Path $PSScriptRoot '.gradle'
[System.IO.Directory]::CreateDirectory($testRoot) | Out-Null
$sandbox = Join-Path $testRoot ('verify-device-test-' + [Guid]::NewGuid().ToString('N'))
[System.IO.Directory]::CreateDirectory($sandbox) | Out-Null
$runner = Join-Path $sandbox 'verify-device.ps1'
$mock = Join-Path $sandbox 'mock-adb.ps1'
$receipt = Join-Path $sandbox 'receipt.json'
$paths = @(
    'app/build/outputs/apk/debug/app-debug.apk',
    'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk',
    'fixture/build/outputs/apk/debug/fixture-debug.apk',
    'fixture-feature/build/outputs/apk/debug/fixture_feature-debug.apk'
)

$mockSource = @'
$arguments = @($args)
if ($arguments.Count -lt 3 -or $arguments[0] -ne '-s') { exit 9 }
switch ($arguments[2]) {
    'get-state' {
        if ($env:PT_PROBE_MOCK_MODE -eq 'no_device') { 'offline' } else { 'device' }
        exit 0
    }
    'install' {
        if ($env:PT_PROBE_MOCK_MODE -eq 'install_failure') { exit 7 }
        'Success'
        exit 0
    }
    'install-multiple' { 'Success'; exit 0 }
    'shell' {
        if ($arguments[3] -eq 'am') {
            if ($env:PT_PROBE_MOCK_MODE -eq 'instrument_failure') {
                'INSTRUMENTATION_CODE: 0'
                exit 0
            }
            $index = [Array]::IndexOf($arguments, 'expectedParts')
            if ($index -lt 0 -or $index + 1 -ge $arguments.Count) { exit 8 }
            $parts = $arguments[$index + 1]
            "INSTRUMENTATION_STATUS: stream=PASS: selected visible package, $parts parts, stable digests"
            'INSTRUMENTATION_CODE: -1'
            exit 0
        }
        if ($arguments[3] -eq 'getprop') {
            switch ($arguments[4]) {
                'ro.kernel.qemu' { '1'; exit 0 }
                'ro.build.version.sdk' { '34'; exit 0 }
                'ro.build.version.release' {
                    if ($env:PT_PROBE_MOCK_MODE -eq 'destination_collision') {
                        New-Item -ItemType Directory -Path $env:PT_PROBE_MOCK_RECEIPT -Force | Out-Null
                    }
                    if ($env:PT_PROBE_MOCK_RELEASE) { $env:PT_PROBE_MOCK_RELEASE } else { '14' }
                    exit 0
                }
            }
        }
    }
}
exit 9
'@

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}
function Invoke-ReceiptRun([string]$Mode, [bool]$ShouldPass) {
    $env:PT_PROBE_MOCK_MODE = $Mode
    $failed = $false
    try {
        $null = & $runner -Serial 'controlled-test-device' -Adb $mock -Receipt $receipt
    } catch {
        $failed = $true
    }
    if ($ShouldPass) {
        Assert-True (-not $failed) "Expected success for $Mode"
        Assert-True (Test-Path -LiteralPath $receipt -PathType Leaf) "Missing receipt for $Mode"
        $result = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
        Assert-True ($result.result -eq 'PASS') "Non-PASS receipt for $Mode"
        Assert-True ($result.cases.Count -eq 2) 'Both device case names must be preserved'
        Assert-True ($result.apk_sha256.Count -eq 4) 'All four APK hashes must be preserved'
        return $result
    }
    Assert-True $failed "Expected failure for $Mode"
    Assert-True (-not (Test-Path -LiteralPath $receipt)) "Stale receipt survived $Mode"
}

try {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'verify-device.ps1') -Destination $runner
    [System.IO.File]::WriteAllText($mock, $mockSource, [System.Text.UTF8Encoding]::new($false))
    foreach ($relativePath in $paths) {
        $path = Join-Path $sandbox $relativePath
        [System.IO.Directory]::CreateDirectory((Split-Path -Parent $path)) | Out-Null
        [System.IO.File]::WriteAllText($path, 'controlled fake APK bytes: ' + $relativePath)
    }

    $null = Invoke-ReceiptRun 'success' $true
    Invoke-ReceiptRun 'no_device' $false
    Write-Host 'PASS stale receipt removed on device failure'

    $null = Invoke-ReceiptRun 'success' $true
    $missing = Join-Path $sandbox $paths[0]
    Remove-Item -LiteralPath $missing -Force
    try {
        Invoke-ReceiptRun 'success' $false
    } finally {
        [System.IO.File]::WriteAllText($missing, 'controlled fake APK bytes: ' + $paths[0])
    }
    Write-Host 'PASS stale receipt removed when APK is missing'

    $null = Invoke-ReceiptRun 'success' $true
    Invoke-ReceiptRun 'install_failure' $false
    Write-Host 'PASS stale receipt removed on ADB install failure'

    $null = Invoke-ReceiptRun 'success' $true
    Invoke-ReceiptRun 'instrument_failure' $false
    Write-Host 'PASS stale receipt removed on instrumentation failure despite ADB exit zero'

    $first = Invoke-ReceiptRun 'success' $true
    $env:PT_PROBE_MOCK_RELEASE = '15'
    $second = Invoke-ReceiptRun 'success' $true
    Assert-True ($first.android_release -eq '14' -and $second.android_release -eq '15') 'A successful rerun must replace the old receipt'
    Assert-True ($second.schema -eq 'privacytrace-android-probe-device-v1') 'Receipt schema changed'
    $env:PT_PROBE_MOCK_RELEASE = '14'
    Write-Host 'PASS successful rerun publishes a new complete receipt'

    $null = Invoke-ReceiptRun 'success' $true
    $env:PT_PROBE_MOCK_MODE = 'destination_collision'
    $env:PT_PROBE_MOCK_RECEIPT = $receipt
    $failed = $false
    try {
        $null = & $runner -Serial 'controlled-test-device' -Adb $mock -Receipt $receipt
    } catch {
        $failed = $true
    }
    Assert-True $failed 'Atomic commit must fail if the destination becomes occupied'
    Assert-True (-not (Test-Path -LiteralPath $receipt -PathType Leaf)) 'Failed commit published a receipt'
    Assert-True (Test-Path -LiteralPath $receipt -PathType Container) 'Mock did not create a destination collision'
    $temps = @(Get-ChildItem -LiteralPath $sandbox -Filter '.receipt.json.*.tmp' -File -Force)
    Assert-True ($temps.Count -eq 0) 'Temporary receipt remained after failed commit'
    Remove-Item -LiteralPath $receipt -Recurse -Force
    Write-Host 'PASS atomic write failure leaves no partial receipt or temporary file'

    $env:PT_PROBE_MOCK_MODE = 'success'
    $output = (& $runner -Serial 'controlled-test-device' -Adb $mock) -join "`n"
    $stdoutReceipt = $output | ConvertFrom-Json
    Assert-True ($stdoutReceipt.result -eq 'PASS') 'Without -Receipt, stdout JSON must still work'
    Assert-True (-not (Test-Path -LiteralPath $receipt)) 'Without -Receipt, no file should be written'
    Write-Host 'PASS stdout-only mode preserved'
    Write-Host 'PASS all 7 receipt regression scenarios'
} finally {
    foreach ($name in @('PT_PROBE_MOCK_MODE', 'PT_PROBE_MOCK_RELEASE', 'PT_PROBE_MOCK_RECEIPT')) {
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}
