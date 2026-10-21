param(
    [Parameter(Mandatory)][string]$ConfigurationPath,
    [string]$OutputPath,
    [Alias('RequireReady')][switch]$RequireToolchainReady
)

$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath $ConfigurationPath -Raw | ConvertFrom-Json
$checks = [System.Collections.Generic.List[object]]::new()

function Add-Probe([string]$Name, [scriptblock]$Action) {
    try {
        $observed = & $Action
        $checks.Add([ordered]@{ name = $Name; status = 'PASSED'; observed = $observed })
    } catch {
        # Details remain in the local receipt. Never publish it without review.
        $checks.Add([ordered]@{ name = $Name; status = 'BLOCKED'; reason = $_.Exception.Message })
    }
}

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    $result = & $Executable @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $result" }
    return ($result -join "`n").Trim()
}

$androidPlatform = if ($config.android_platform) { [string]$config.android_platform } else { 'android-36' }
$buildToolsVersion = if ($config.build_tools_version) { [string]$config.build_tools_version } else { '36.0.0' }
$ndkVersion = if ($config.ndk_version) { [string]$config.ndk_version } else { '27.2.12479018' }
$abiTargets = @{
    'x86_64' = 'x86_64-linux-android'
    'arm64-v8a' = 'aarch64-linux-android'
    'armeabi-v7a' = 'armv7-linux-androideabi'
}

Add-Probe 'android-build-tools' {
    foreach ($relative in @("platforms/$androidPlatform/android.jar",
        "build-tools/$buildToolsVersion/aapt2.exe", "build-tools/$buildToolsVersion/apksigner.bat",
        "ndk/$ndkVersion/source.properties")) {
        if (-not (Test-Path -LiteralPath (Join-Path $config.android_sdk $relative))) {
            throw "Missing SDK component: $relative"
        }
    }
    "API $androidPlatform / build-tools $buildToolsVersion / NDK $ndkVersion files present; build compatibility still requires compilation"
}
Add-Probe 'java' { Invoke-Checked (Join-Path $config.java_home 'bin/java.exe') @('-version') }
Add-Probe 'rust-android-target' {
    $rustTarget = if ($config.rust_android_target) { [string]$config.rust_android_target } else { $abiTargets[[string]$config.expected_abi] }
    if (-not $rustTarget) { throw "No Rust target mapping for expected ABI: $($config.expected_abi)" }
    $rust = Join-Path $config.rust_toolchain "lib/rustlib/$rustTarget/lib"
    if (-not (Test-Path -LiteralPath $rust)) { throw "Rust target missing: $rustTarget" }
    if (-not $config.windows_gnu_tools -or -not (Test-Path -LiteralPath (Join-Path $config.windows_gnu_tools 'dlltool.exe'))) {
        throw 'A complete Windows GNU host toolchain is required'
    }
    Invoke-Checked (Join-Path $config.rust_toolchain 'bin/rustc.exe') @('--version')
}
Add-Probe 'dedicated-android' {
    if (-not $config.adb_target -or $config.device_kind -ne 'EMULATOR') {
        throw 'An explicit dedicated emulator target is required'
    }
    $target = [string]$config.adb_target
    # MuMu masks ro.kernel.qemu. Bind host inventory to this exact ADB endpoint.
    $inventory = Invoke-Checked $config.emulator_manager @('info', '--vmindex', [string]$config.emulator_index) | ConvertFrom-Json
    if ($inventory.name -ne $config.emulator_name -or -not $inventory.is_android_started -or
        "$($inventory.adb_host_ip):$($inventory.adb_port)" -ne $target) {
        throw 'Host emulator identity does not match the dedicated ADB target'
    }
    $state = Invoke-Checked $config.adb @('-s', $target, 'get-state')
    $boot = Invoke-Checked $config.adb @('-s', $target, 'shell', 'getprop', 'sys.boot_completed')
    if ($state -ne 'device' -or $boot -ne '1') { throw 'Dedicated emulator is not booted' }
    $api = Invoke-Checked $config.adb @('-s', $target, 'shell', 'getprop', 'ro.build.version.sdk')
    $abi = Invoke-Checked $config.adb @('-s', $target, 'shell', 'getprop', 'ro.product.cpu.abi')
    if ($api -ne [string]$config.expected_api -or $abi -ne $config.expected_abi) {
        throw 'Android runtime API or ABI differs from the explicit configuration'
    }
    [ordered]@{
        kind = 'EMULATOR'
        api = $api
        abi = $abi
        system_build = Invoke-Checked $config.adb @('-s', $target, 'shell', 'getprop', 'ro.build.display.id')
        webview = Invoke-Checked $config.adb @('-s', $target, 'shell', 'dumpsys', 'webviewupdate')
    }
}
if (-not $config.control_distribution -or -not $config.runner_distribution -or
    $config.control_distribution -eq $config.runner_distribution) {
    $checks.Add([ordered]@{
        name = 'dedicated-distributions'
        status = 'BLOCKED'
        reason = 'Control and runner must have distinct dedicated distributions'
    })
}
foreach ($role in @('control', 'runner')) {
    $distribution = [string]$config."${role}_distribution"
    Add-Probe "${role}-tools" {
        if (-not $distribution) { throw 'Missing dedicated distribution name' }
        # Static read-only shell; distribution is a separate argv, never shell code.
        Invoke-Checked 'wsl.exe' @('-d', $distribution, '-u', 'root', '--exec', 'bash', '-lc',
            'set -eu; cat /etc/os-release; python3 --version; docker --version; docker compose version; openssl version')
    }
    Add-Probe "${role}-daemon" {
        Invoke-Checked 'wsl.exe' @('-d', $distribution, '-u', 'root', '--exec', 'bash', '-lc',
            'set -eu; test "$(cat /etc/privacytrace-issue73-environment)" = "$1"; test "$(docker --host=unix:///var/run/docker.sock info --format "{{.DockerRootDir}}")" = /var/lib/privacytrace73/docker; pid=$(systemctl show privacytrace73-docker.service -p MainPID --value); test "$pid" -gt 0; daemon_net=$(readlink /proc/$pid/ns/net); host_net=$(readlink /proc/self/ns/net); test "$daemon_net" != "$host_net"; docker --host=unix:///var/run/docker.sock info --format "{{.ServerVersion}} cgroup={{.CgroupVersion}} driver={{.CgroupDriver}}"; printf "%s\n%s\n" "$host_net" "$daemon_net"',
            'probe', $role)
    }
}

$report = [ordered]@{
    record_kind = 'LOCAL_ENVIRONMENT_PROBE'
    captured_at_utc = [DateTime]::UtcNow.ToString('o')
    issue = 73
    toolchain_ready = @($checks | Where-Object status -ne 'PASSED').Count -eq 0
    checks = $checks
    final_acceptance_ready = $false
    final_acceptance_passed = $false
    unverified = @('Issue81 final handoff', 'Client compilation and installation',
        'Android HTTPS trust and routing', 'Daemon/network isolation',
        'H01-H12 N01-N12 F01-F10 R01-R04')
}
$json = $report | ConvertTo-Json -Depth 12
if ($OutputPath) {
    if (Test-Path -LiteralPath $OutputPath) { throw 'Use a new receipt path; existing evidence is preserved' }
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), $json + "`n")
}
$json
if ($RequireToolchainReady -and -not $report.toolchain_ready) { exit 1 }
exit 0
