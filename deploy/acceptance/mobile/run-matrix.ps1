#requires -Version 5.1
<#
.SYNOPSIS
    Issue 73 本机 Android 验收矩阵串行执行器。

.DESCRIPTION
    逐个用例调用 client-case.cjs，把退出码、job_state、deletion 和错误首行写入
    <OutDir>\matrix-results.csv。任一用例失败且未指定 -ContinueOnError 时立即停止。
    执行前检查 adb 设备、客户端安装、adb reverse 提示以及 HTTPS 健康检查。

.PARAMETER Cases
    用例数组或通配符。可写 H01、H02,H05、H0*、case-*.json、完整路径。
    显式列出的顺序会被保留；通配符匹配结果按 H/N/F/R 编号排序。默认 '*'（全部 case-*.json）。

.PARAMETER OutDir
    证据目录。会设置为 PT_EVIDENCE_DIR 传给 client-case.cjs；相对路径按当前目录解析。

.PARAMETER ContinueOnError
    某个用例失败后继续执行后续用例。

.PARAMETER DryRun
    只解析并打印计划，不连接 adb、不检查健康、不执行 node。用于核对 -Cases。

.PARAMETER CaCert
    HTTPS 健康检查使用的 CA 文件，默认 <env>\tls\ca.crt。

.PARAMETER Adb
    adb 可执行文件，默认取 PT_ADB，其次 PATH 中的 adb。

.PARAMETER AdbSerial
    adb 序列号，默认取 PT_ADB_SERIAL；两者都没有时直接报错，避免连到错误的设备。

.EXAMPLE
    powershell -NoProfile -File .\run-matrix.ps1 -Cases H02,H05,H01 -OutDir .\evidence\matrix-I -ContinueOnError

.EXAMPLE
    powershell -NoProfile -File .\run-matrix.ps1 -Cases 'H0*' -OutDir .\evidence\matrix-I

.EXAMPLE
    powershell -NoProfile -File .\run-matrix.ps1 -Cases H02 -OutDir .\evidence\dryrun -DryRun
#>
[CmdletBinding()]
param(
    [string[]]$Cases = @('*'),

    [Parameter(Mandatory = $true)]
    [string]$OutDir,

    [switch]$ContinueOnError,
    [switch]$DryRun,

    [string]$CaCert,
    [string]$Adb,
    [string]$AdbSerial
)

$ErrorActionPreference = 'Stop'

$script:Utf8NoBom = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false

try {
    [Console]::OutputEncoding = $script:Utf8NoBom
    $OutputEncoding = $script:Utf8NoBom
} catch {
    # 无控制台（例如某些宿主）时不影响文件输出。
}

$envDir = $PSScriptRoot
$caseDir = Join-Path $envDir 'cases'
$clientCase = Join-Path $envDir 'client-case.cjs'
$invokeDir = (Get-Location).Path

function Write-Section {
    param([string]$Text)
    Write-Host ''
    Write-Host "== $Text =="
}

function Get-CaseSortKey {
    param([string]$Name)
    if ($Name -match '^case-([A-Za-z]+)(\d+)') {
        $group = 9
        switch ($matches[1].ToUpperInvariant()) {
            'H' { $group = 0 }
            'N' { $group = 1 }
            'F' { $group = 2 }
            'R' { $group = 3 }
            default { $group = 9 }
        }
        return ('{0}{1:D3}{2}' -f $group, [int]$matches[2], $Name)
    }
    return ('9' + $Name)
}

function Resolve-CaseFiles {
    param(
        [string[]]$Tokens,
        [string]$CaseDir,
        [string]$InvokeDir
    )

    if (-not (Test-Path -LiteralPath $CaseDir -PathType Container)) {
        throw "用例目录不存在: $CaseDir"
    }
    $allCases = @(Get-ChildItem -LiteralPath $CaseDir -File -Filter 'case-*.json' -ErrorAction SilentlyContinue)
    if ($allCases.Count -eq 0) {
        throw "用例目录里没有 case-*.json: $CaseDir"
    }

    $resolved = New-Object System.Collections.Generic.List[string]
    $seen = @{}

    foreach ($rawToken in $Tokens) {
        if ([string]::IsNullOrWhiteSpace($rawToken)) { continue }
        $token = $rawToken.Trim()
        $found = New-Object System.Collections.Generic.List[string]
        $looksLikePath = ([System.IO.Path]::IsPathRooted($token)) -or ($token -match '[\\/]')

        if ($looksLikePath) {
            $candidate = $token
            if (-not [System.IO.Path]::IsPathRooted($candidate)) {
                $candidate = Join-Path $InvokeDir $candidate
            }
            if ($token -match '[*?\[]') {
                foreach ($item in @(Get-ChildItem -Path $candidate -File -ErrorAction SilentlyContinue)) {
                    $found.Add($item.FullName)
                }
            } elseif (Test-Path -LiteralPath $candidate -PathType Leaf) {
                $found.Add((Resolve-Path -LiteralPath $candidate).Path)
            }
        } else {
            $patterns = @(
                $token,
                ($token + '.json'),
                ('case-' + $token),
                ('case-' + $token + '.json'),
                ('case-' + $token + '*'),
                ('case-' + $token + '.json*')
            ) | Select-Object -Unique
            $matched = New-Object System.Collections.Generic.List[object]
            foreach ($caseFile in $allCases) {
                foreach ($pattern in $patterns) {
                    if (($caseFile.Name -like $pattern) -or ($caseFile.BaseName -like $pattern)) {
                        $matched.Add($caseFile)
                        break
                    }
                }
            }
            if ($matched.Count -gt 1) {
                $matched = @($matched | Sort-Object { Get-CaseSortKey $_.Name })
            }
            foreach ($item in $matched) { $found.Add($item.FullName) }
        }

        if ($found.Count -eq 0) {
            throw "未找到用例: $token（用例目录 $CaseDir）。人工用例没有 JSON，见 cases/README.md。"
        }

        foreach ($path in $found) {
            $full = [System.IO.Path]::GetFullPath($path)
            $key = $full.ToLowerInvariant()
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                $resolved.Add($full)
            }
        }
    }

    if ($resolved.Count -eq 0) { throw '没有解析到任何用例。' }
    return $resolved.ToArray()
}

function Read-CaseFile {
    param([string]$Path)
    try {
        $case = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "无法解析用例 JSON: $Path ($($_.Exception.Message))"
    }
    if (-not $case.caseId) { throw "用例缺少 caseId: $Path" }
    if (-not $case.origin) { throw "用例缺少 origin: $Path" }
    if (-not $case.policyMode) { throw "用例缺少 policyMode: $Path" }

    $prefix = [string]$case.evidencePrefix
    if ([string]::IsNullOrWhiteSpace($prefix)) { $prefix = [string]$case.caseId }

    return [pscustomobject]@{
        Path = $Path
        CaseId = [string]$case.caseId
        Origin = [string]$case.origin
        PolicyMode = [string]$case.policyMode
        EvidencePrefix = $prefix
        UploadAttempts = $case.uploadAttempts
        Cleanup = $case.cleanup
        AppLabel = $case.appLabel
        Raw = $case
    }
}

function Resolve-AdbPath {
    param([string]$Explicit)
    if ($Explicit) {
        if (Test-Path -LiteralPath $Explicit -PathType Leaf) {
            return (Resolve-Path -LiteralPath $Explicit).Path
        }
        throw "指定的 adb 不存在: $Explicit"
    }
    if ($env:PT_ADB -and (Test-Path -LiteralPath $env:PT_ADB -PathType Leaf)) {
        return (Resolve-Path -LiteralPath $env:PT_ADB).Path
    }
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw '找不到 adb。请用 -Adb 指定，或设置 PT_ADB。'
}

function Resolve-AdbSerial {
    param([string]$Explicit)
    if ($Explicit) { return $Explicit }
    if ($env:PT_ADB_SERIAL) { return $env:PT_ADB_SERIAL }
    throw '缺少 adb 序列号。请用 -AdbSerial 指定，或设置 PT_ADB_SERIAL（例如模拟器的 127.0.0.1:<port>）。'
}

function Assert-AdbDevice {
    param([string]$AdbExe, [string]$Serial)

    $stateRaw = & $AdbExe -s $Serial get-state 2>&1
    $stateCode = $LASTEXITCODE
    $stateText = ($stateRaw | Out-String).Trim()
    if ($stateCode -ne 0 -or $stateText -notmatch 'device') {
        throw "ADB 设备不在线: $Serial（exit=$stateCode, output=$stateText）"
    }

    $pkgRaw = & $AdbExe -s $Serial shell pm list packages org.privacytrace.mobile 2>&1
    $pkgCode = $LASTEXITCODE
    $pkgText = ($pkgRaw | Out-String)
    if ($pkgCode -ne 0 -or $pkgText -notmatch 'org\.privacytrace\.mobile') {
        throw "模拟器未安装客户端 org.privacytrace.mobile（exit=$pkgCode）"
    }

    $fixtureRaw = & $AdbExe -s $Serial shell pm list packages org.privacytrace.probe.fixture 2>&1
    $fixtureText = ($fixtureRaw | Out-String)
    if ($fixtureText -notmatch 'org\.privacytrace\.probe\.fixture') {
        Write-Warning '未检测到受控样本 org.privacytrace.probe.fixture；H 用例需要先安装 fixture base/base+splits。'
    }

    $reverseRaw = & $AdbExe -s $Serial reverse --list 2>&1
    $reverseText = ($reverseRaw | Out-String)
    if ($reverseText -notmatch 'tcp:28443') {
        Write-Warning "adb reverse 列表里没有 tcp:28443；客户端可能无法访问 https://localhost:28443。请先建立 28443 的反向映射（I/J 切换时尤其注意）。"
    }

    return $stateText
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 5000
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        if (-not $task.Wait($TimeoutMs)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Assert-Health {
    param([string]$Origin, [string]$CaPath)

    $uri = $null
    try { $uri = [System.Uri]$Origin } catch { $uri = $null }
    if ($null -eq $uri -or -not $uri.IsAbsoluteUri) {
        throw "origin 不是绝对 URL: $Origin"
    }

    $healthUrl = $Origin.TrimEnd('/') + '/api/v1/health'
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    $hasCa = ($CaPath -and (Test-Path -LiteralPath $CaPath -PathType Leaf))

    if ($curl -and $hasCa) {
        $curlArgs = @(
            '--noproxy', '*',
            '--silent', '--show-error',
            '--max-time', '8',
            '--output', 'NUL',
            '--write-out', '%{http_code}',
            '--cacert', $CaPath,
            $healthUrl
        )
        $curlRaw = & $curl.Source @curlArgs 2>&1
        $curlCode = $LASTEXITCODE
        $curlText = ($curlRaw | Out-String).Trim()
        $httpCode = @($curlText -split "`r?`n" | Where-Object { $_.Trim() -ne '' }) | Select-Object -Last 1
        if ($null -eq $httpCode) { $httpCode = '' }
        $httpCode = ([string]$httpCode).Trim()
        if ($curlCode -ne 0) {
            throw "HTTPS 健康检查失败（curl exit=$curlCode）: $curlText"
        }
        if ($httpCode -ne '200') {
            throw "HTTPS 健康检查返回 $httpCode，期望 200: $healthUrl"
        }
        return 'https-200'
    }

    if (-not (Test-TcpPort -HostName $uri.Host -Port $uri.Port)) {
        throw "无法建立 TCP 连接: $($uri.Host):$($uri.Port)（实例未启动或转发未建立）"
    }
    if (-not $curl) {
        Write-Warning '未找到 curl.exe，只完成 TCP 探测，未验证 HTTPS/TLS 与 /api/v1/health。'
    } else {
        Write-Warning "未找到 CA 文件 '$CaPath'，只完成 TCP 探测，未验证 HTTPS/TLS。可用 -CaCert 指定。"
    }
    return 'tcp-only'
}

function Save-MatrixCsv {
    param([string]$Path, $Rows)
    try {
        $Rows | Export-Csv -LiteralPath $Path -NoTypeInformation -Encoding UTF8
    } catch {
        throw "无法写入 CSV: $Path ($($_.Exception.Message))"
    }
}

function Get-ErrorFirstLine {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return '' }
    $lines = @($Text -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
    $caseLine = $lines | Where-Object { $_ -match 'CASE_FAILED' } | Select-Object -First 1
    if ($caseLine) { return $caseLine.Trim() }
    if ($lines.Count -gt 0) { return $lines[0].Trim() }
    return ''
}

# ---------- 用例解析 ----------

if ($null -eq $Cases -or $Cases.Count -eq 0) { $Cases = @('*') }
$expandedCases = New-Object System.Collections.Generic.List[string]
foreach ($item in $Cases) {
    foreach ($part in ($item -split ',')) {
        if (-not [string]::IsNullOrWhiteSpace($part)) { $expandedCases.Add($part.Trim()) }
    }
}
if ($expandedCases.Count -eq 0) { $expandedCases.Add('*') }

try {
    $caseFiles = @(Resolve-CaseFiles -Tokens $expandedCases.ToArray() -CaseDir $caseDir -InvokeDir $invokeDir)
    $plan = New-Object System.Collections.Generic.List[object]
    $ids = @{}
    foreach ($file in $caseFiles) {
        $case = Read-CaseFile -Path $file
        if ($ids.ContainsKey($case.CaseId)) { throw "caseId 重复: $($case.CaseId)" }
        $ids[$case.CaseId] = $true
        $plan.Add($case)
    }
} catch {
    Write-Host "用例解析失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}

if ($DryRun) {
    Write-Section '计划（DryRun：不连接 adb、不检查健康、不执行 node）'
    Write-Host "用例目录: $caseDir"
    Write-Host "证据目录: $OutDir"
    $n = 0
    foreach ($case in $plan) {
        $n++
        Write-Host ("  [{0}/{1}] {2}  mode={3}  appLabel={4}  file={5}" -f $n, $plan.Count, $case.CaseId, $case.PolicyMode, $case.AppLabel, (Split-Path -Leaf $case.Path))
    }
    exit 0
}

# ---------- 输出目录 ----------

try {
    if ([string]::IsNullOrWhiteSpace($OutDir)) { throw '必须提供 -OutDir。' }
    if (-not [System.IO.Path]::IsPathRooted($OutDir)) { $OutDir = Join-Path $invokeDir $OutDir }
    $OutDir = [System.IO.Path]::GetFullPath($OutDir)
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    $logDir = Join-Path $OutDir 'logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $csvPath = Join-Path $OutDir 'matrix-results.csv'
} catch {
    Write-Host "无法准备输出目录: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}

# ---------- 预检 ----------

try {
    if (-not (Test-Path -LiteralPath $clientCase -PathType Leaf)) {
        throw "执行器不存在: $clientCase"
    }
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) { throw '找不到 node。' }

    $adbExe = Resolve-AdbPath -Explicit $Adb
    $serial = Resolve-AdbSerial -Explicit $AdbSerial
    $env:PT_ADB = $adbExe
    $env:PT_ADB_SERIAL = $serial

    $deviceState = Assert-AdbDevice -AdbExe $adbExe -Serial $serial

    $caPath = $CaCert
    if ([string]::IsNullOrWhiteSpace($caPath)) { $caPath = Join-Path $envDir 'tls\ca.crt' }
    $origins = @($plan | ForEach-Object { $_.Origin } | Select-Object -Unique)
    $healthResults = @()
    foreach ($origin in $origins) {
        $healthResults += (Assert-Health -Origin $origin -CaPath $caPath)
    }

    $singleCount = @($plan | Where-Object { $_.CaseId -match 'single' }).Count
    $splitsCount = @($plan | Where-Object { $_.CaseId -match 'splits' }).Count
    if ($singleCount -gt 0 -and $splitsCount -gt 0) {
        Write-Warning '本次计划同时包含单 APK 与 splits 用例；执行前需按用例切换安装集合，否则单/拆包语义会错。'
    }
    if ($singleCount -gt 0 -or $splitsCount -gt 0) {
        $pathRaw = & $adbExe -s $serial shell pm path org.privacytrace.probe.fixture 2>&1
        $pathText = ($pathRaw | Out-String)
        $packageCount = @($pathText -split "`r?`n" | Where-Object { $_ -match '^package:' }).Count
        if ($singleCount -gt 0 -and $packageCount -gt 1) {
            Write-Warning "计划包含单 APK 用例，但当前 fixture 读到 $packageCount 个包；请先卸载 split。"
        }
        if ($splitsCount -gt 0 -and $packageCount -lt 2) {
            Write-Warning '计划包含 splits 用例，但当前 fixture 似乎只有 base；请安装 base+fixture_feature。'
        }
    }

    Write-Section '预检通过'
    Write-Host "ADB: $adbExe ($serial)  state=$deviceState"
    Write-Host "HTTPS: $($origins -join ', ')  health=$($healthResults -join ', ')"
    Write-Host "Node: $($node.Source)"
    Write-Host "执行器: $clientCase"
    Write-Host "证据: $OutDir"
} catch {
    Write-Host "预检失败: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
}

# ---------- 逐例执行 ----------

$rows = New-Object System.Collections.Generic.List[object]
$failed = New-Object System.Collections.Generic.List[string]
$total = $plan.Count
$index = 0
$stopped = $false

foreach ($case in $plan) {
    $index++
    Write-Section ("[{0}/{1}] {2}" -f $index, $total, $case.CaseId)
    Write-Host ("  mode={0}  appLabel={1}  evidencePrefix={2}" -f $case.PolicyMode, $case.AppLabel, $case.EvidencePrefix)

    $startedAt = Get-Date
    $resultPath = Join-Path $OutDir ($case.EvidencePrefix + '-result.json')
    $logPath = Join-Path $logDir ($case.CaseId + '.log')
    $env:PT_EVIDENCE_DIR = $OutDir

    $outputObjects = @()
    $exitCode = 1
    Push-Location $envDir
    try {
        $outputObjects = & $node.Source $clientCase $case.Path 2>&1
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) { $exitCode = 1 }
    } catch {
        $exitCode = 1
        $outputObjects = @("启动 node 失败: $($_.Exception.Message)")
    } finally {
        Pop-Location
    }
    $outputText = ($outputObjects | Out-String)

    try {
        [System.IO.File]::WriteAllText($logPath, [string]$outputText, $script:Utf8NoBom)
    } catch {
        Write-Warning "无法写入日志 ${logPath}: $($_.Exception.Message)"
    }

    $jobState = ''
    $deletion = ''
    $parseError = ''
    $resultExists = Test-Path -LiteralPath $resultPath -PathType Leaf
    if ($resultExists) {
        try {
            $result = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $jobState = [string]$result.job_state
            $deletion = [string]$result.deletion
        } catch {
            $parseError = $_.Exception.Message
        }
    }

    $failureReason = ''
    if ($exitCode -ne 0) {
        $failureReason = 'exit=' + $exitCode
    } elseif (-not $resultExists) {
        $failureReason = '结果 JSON 缺失'
    } elseif ($parseError) {
        $failureReason = '结果 JSON 解析失败'
    } elseif ($jobState -ne 'SUCCEEDED') {
        $failureReason = 'job_state=' + $jobState
    }

    $errorFirst = ''
    if ($exitCode -ne 0) {
        $errorFirst = Get-ErrorFirstLine -Text $outputText
    } elseif ($failureReason) {
        $errorFirst = $failureReason
        if ($parseError) { $errorFirst = $errorFirst + ': ' + $parseError }
    }

    $resultPathValue = ''
    if ($resultExists) { $resultPathValue = $resultPath }

    $rows.Add([pscustomobject][ordered]@{
        '时间' = $startedAt.ToString('yyyy-MM-dd HH:mm:ss')
        '用例' = $case.CaseId
        '退出码' = $exitCode
        '结果 JSON 路径' = $resultPathValue
        'job_state' = $jobState
        'deletion' = $deletion
        '错误首行' = $errorFirst
    })
    Save-MatrixCsv -Path $csvPath -Rows $rows

    if ($resultExists -and $case.Cleanup -eq $true -and $deletion -ne 'DELETED') {
        Write-Warning ("cleanup=true 但 deletion={0}；当前执行器未驱动原生删除确认，远端草稿可能仍占用每 IP 3 份配额。" -f $deletion)
    }

    if ($failureReason) {
        Write-Host ("  -> 失败: {0}（job_state={1}, deletion={2}）" -f $failureReason, $jobState, $deletion) -ForegroundColor Red
        $failed.Add(("{0} [{1}]" -f $case.CaseId, $failureReason))
        if (-not $ContinueOnError) {
            $stopped = $true
            break
        }
    } else {
        Write-Host ("  -> 通过: job_state={0}, deletion={1}" -f $jobState, $deletion) -ForegroundColor Green
    }
}

# ---------- 汇总 ----------

$executed = $rows.Count
$passed = $executed - $failed.Count
$notRun = $total - $executed

Write-Section '矩阵汇总'
Write-Host ("用例总数: {0}；已执行: {1}；通过: {2}；失败: {3}；未执行: {4}" -f $total, $executed, $passed, $failed.Count, $notRun)
if ($stopped) {
    Write-Host '已在首个失败处停止（未使用 -ContinueOnError）。' -ForegroundColor Yellow
}
if ($failed.Count -gt 0) {
    Write-Host '失败用例:' -ForegroundColor Red
    foreach ($item in $failed) {
        Write-Host ("  - " + $item)
    }
}
Write-Host ("CSV: " + $csvPath)

if ($failed.Count -gt 0) { exit 1 }
exit 0
