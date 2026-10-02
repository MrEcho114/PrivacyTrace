param([string]$RepositoryName = 'privacytrace')
. "$PSScriptRoot\common.ps1"
$ghTool = Get-PrivacyTraceTool 'gh'
$gitTool = Get-PrivacyTraceTool 'git'
Push-Location $script:PrivacyTraceRoot
try {
    Invoke-PrivacyTraceTool $ghTool @('auth', 'status')
    $accountJson = & $ghTool api user
    if ($LASTEXITCODE -ne 0) { throw 'GitHub account verification failed.' }
    $account = $accountJson | ConvertFrom-Json
    $fullName = "$($account.login)/$RepositoryName"
    $existingJson = & $ghTool repo view $fullName --json nameWithOwner,visibility 2>$null
    if ($LASTEXITCODE -eq 0) {
        $existing = $existingJson | ConvertFrom-Json
        if ($existing.visibility -ne 'PRIVATE') { throw 'Existing repository is not private.' }
        throw "Repository $fullName already exists. Review it before adding a remote."
    }
    $existingOrigin = & $gitTool remote get-url origin 2>$null
    if ($LASTEXITCODE -eq 0) { throw "An origin already exists: $existingOrigin" }
    $authorName = & $gitTool config --get user.name
    if (-not $authorName) {
        Invoke-PrivacyTraceTool $gitTool @('config', '--local', 'user.name', $account.login)
    }
    $authorEmail = & $gitTool config --get user.email
    if (-not $authorEmail) {
        $noReply = "$($account.id)+$($account.login)@users.noreply.github.com"
        Invoke-PrivacyTraceTool $gitTool @('config', '--local', 'user.email', $noReply)
    }
    & $gitTool rev-parse --verify HEAD 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Invoke-PrivacyTraceTool $gitTool @('add', '.')
        Invoke-PrivacyTraceTool $gitTool @('commit', '-m', 'chore(PT-001): bootstrap PrivacyTrace MVP repository')
    }
    Invoke-PrivacyTraceTool $ghTool @('repo', 'create', $fullName, '--private', '--source=.', '--remote=origin', '--push', '--description', 'Evidence-based Android privacy reports with traceable policy consistency checks')
    $verifiedJson = & $ghTool repo view $fullName --json url,visibility
    if ($LASTEXITCODE -ne 0) { throw 'Post-creation repository verification failed.' }
    $verified = $verifiedJson | ConvertFrom-Json
    if ($verified.visibility -ne 'PRIVATE') { throw 'Repository privacy verification failed.' }
    Write-Output "Private repository ready: $($verified.url)"
} finally { Pop-Location }
