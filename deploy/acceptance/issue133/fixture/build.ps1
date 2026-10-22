param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if (-not $env:ANDROID_HOME -or -not $env:JAVA_HOME) { throw 'ANDROID_HOME and JAVA_HOME are required' }
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Use a new output directory; preserve previous fixture evidence' }
$tools = Join-Path $env:ANDROID_HOME 'build-tools/34.0.0'
$androidJar = Join-Path $env:ANDROID_HOME 'platforms/android-34/android.jar'
New-Item -ItemType Directory -Path "$output/classes","$output/dex" | Out-Null
& "$env:JAVA_HOME/bin/javac.exe" -source 8 -target 8 -cp $androidJar -d "$output/classes" "$PSScriptRoot/IdentifierFixture.java"
if ($LASTEXITCODE -ne 0) { throw 'javac failed' }
& "$tools/d8.bat" --min-api 24 --lib $androidJar --output "$output/dex" "$output/classes/org/privacytrace/issue133/fixture/IdentifierFixture.class"
if ($LASTEXITCODE -ne 0) { throw 'd8 failed' }
& "$tools/aapt.exe" package -f -M "$PSScriptRoot/AndroidManifest.xml" -I $androidJar -F "$output/fixture-unsigned.apk"
if ($LASTEXITCODE -ne 0) { throw 'aapt package failed' }
Push-Location "$output/dex"
try { & "$tools/aapt.exe" add "$output/fixture-unsigned.apk" classes.dex } finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw 'aapt add failed' }
& "$env:JAVA_HOME/bin/keytool.exe" -genkeypair -keystore "$output/fixture.keystore" -storepass android -keypass android -alias fixture -dname 'CN=PrivacyTrace lane E synthetic fixture' -keyalg RSA -validity 7
if ($LASTEXITCODE -ne 0) { throw 'fixture signing key generation failed' }
& "$tools/zipalign.exe" -f 4 "$output/fixture-unsigned.apk" "$output/fixture-aligned.apk"
if ($LASTEXITCODE -ne 0) { throw 'zipalign failed' }
& "$tools/apksigner.bat" sign --ks "$output/fixture.keystore" --ks-key-alias fixture --ks-pass pass:android --out "$output/fixture.apk" "$output/fixture-aligned.apk"
if ($LASTEXITCODE -ne 0) { throw 'apksigner failed' }
& "$tools/apksigner.bat" verify --print-certs "$output/fixture.apk" > "$output/signature.txt"
if ($LASTEXITCODE -ne 0) { throw 'signature verification failed' }
Get-FileHash "$output/fixture.apk" -Algorithm SHA256
