$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & npm run tauri -- android init --ci --skip-targets-install
    if ($LASTEXITCODE -ne 0) { throw 'Tauri Android initialization failed.' }
    $androidRoot = Join-Path $PSScriptRoot 'src-tauri/gen/android'
    $appGradle = Join-Path $androidRoot 'app/build.gradle.kts'
    $text = [IO.File]::ReadAllText($appGradle)
    # CLI 2.12.3 generates API 37; this mobile shell uses the inherited API 36 pin.
    foreach ($setting in @('compileSdk', 'targetSdk')) {
        $pattern = "($setting\s*=\s*)(37|36)\b"
        if ([regex]::Matches($text, $pattern).Count -ne 1) {
            throw "Unexpected generated Android template for $setting. Review it before building."
        }
        $text = [regex]::Replace($text, $pattern, '${1}36')
    }
    $text = $text.Replace('manifestPlaceholders["usesCleartextTraffic"] = "true"',
        'manifestPlaceholders["usesCleartextTraffic"] = "false"')
    [IO.File]::WriteAllText($appGradle, $text)

    $manifestPath = Join-Path $androidRoot 'app/src/main/AndroidManifest.xml'
    [xml]$manifest = [IO.File]::ReadAllText($manifestPath)
    $androidNamespace = 'http://schemas.android.com/apk/res/android'
    # Native transport needs INTERNET; the reused plugin declares it.
    # Cleartext remains disabled and no WebView network capability is added.
    [void]$manifest.manifest.application.SetAttribute('allowBackup', $androidNamespace, 'false')
    $manifest.Save($manifestPath)

    $wrapperPath = Join-Path $androidRoot 'gradle/wrapper/gradle-wrapper.properties'
    $wrapper = [IO.File]::ReadAllText($wrapperPath)
    if ($wrapper -notmatch 'gradle-9\.6\.1-bin\.zip') {
        throw 'Unexpected Gradle distribution. Review the pinned CLI template before building.'
    }
    $checksum = '9c0f7faeeb306cb14e4279a3e084ca6b596894089a0638e68a07c945a32c9e14'
    $wrapper = [regex]::Replace($wrapper, '(?m)^distributionSha256Sum=.*\r?\n?', '')
    [IO.File]::WriteAllText($wrapperPath, $wrapper.TrimEnd() + "`ndistributionSha256Sum=$checksum`n")
    Write-Output 'Prepared PrivacyTrace mobile workflow (API 36).'
} finally { Pop-Location }
