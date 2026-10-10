$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPlan = Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'changes.json') | ConvertFrom-Json
$taskBefore = @(Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'prepublish.snapshot.json') | ConvertFrom-Json)
$taskAfter = @(Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'postpublish.snapshot.json') | ConvertFrom-Json)
$taskDependencies = @(Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'postpublish-dependencies.json') | ConvertFrom-Json)
$taskParent = Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'postpublish-parent.json') | ConvertFrom-Json

function Assert-TaskMetadata($Original, $Actual) {
    if ((@($Original.assignees.login | Sort-Object) -join ',') -ne
        (@($Actual.assignees.login | Sort-Object) -join ',') -or
        $Original.milestone.number -ne $Actual.milestone.number) {
        throw "Assignee/milestone changed #$($Original.number)"
    }
    foreach ($taskComment in $Original.comments) {
        $taskCurrent = $Actual.comments | Where-Object id -eq $taskComment.id
        if ($taskCurrent.body -ne $taskComment.body) {
            throw "Original comment changed #$($Original.number)"
        }
    }
}

$taskVerified = @()
foreach ($taskEdit in $taskPlan.update) {
    $taskActual = $taskAfter | Where-Object number -eq $taskEdit.number
    $taskOriginal = $taskBefore | Where-Object number -eq $taskEdit.number
    $taskExpected = Get-Content -Raw -LiteralPath (Join-Path $taskRoot ('published/'+[IO.Path]::GetFileName($taskEdit.body_file)))
    if ($taskActual.title -ne $taskEdit.title -or $taskActual.body -ne $taskExpected -or $taskActual.state -ne $taskEdit.state_after) {
        throw "Title/body/state mismatch #$($taskEdit.number)"
    }
    $taskLabels = @($taskOriginal.labels.name) + @($taskEdit.add_labels) | Where-Object { $_ } | Sort-Object -Unique
    if (($taskLabels -join ',') -ne (@($taskActual.labels.name | Sort-Object -Unique) -join ',')) {
        throw "Label mismatch #$($taskEdit.number)"
    }
    Assert-TaskMetadata $taskOriginal $taskActual
    $taskVerified += [PSCustomObject]@{
        number = $taskEdit.number
        title = $taskActual.title
        state = $taskActual.state
        labels = @($taskActual.labels.name)
        url = $taskActual.url
        body_sha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($taskActual.body))).ToLowerInvariant()
    }
}
foreach ($taskNumber in $taskPlan.preserve_issues) {
    $taskOriginal = $taskBefore | Where-Object number -eq $taskNumber
    $taskActual = $taskAfter | Where-Object number -eq $taskNumber
    if ($taskActual.body -ne $taskOriginal.body -or $taskActual.title -ne $taskOriginal.title -or $taskActual.state -ne $taskOriginal.state -or
        (@($taskActual.labels.name | Sort-Object) -join ',') -ne (@($taskOriginal.labels.name | Sort-Object) -join ',')) {
        throw "Preserved issue changed #$taskNumber"
    }
    Assert-TaskMetadata $taskOriginal $taskActual
}
$taskNew = $taskAfter | Where-Object number -eq 31
$taskNewExpected = Get-Content -Raw -LiteralPath (Join-Path $taskRoot 'published/new-PT-910.md')
if ($taskNew.title -ne $taskPlan.create[0].title -or $taskNew.body -ne $taskNewExpected -or
    $taskNew.state -ne 'OPEN' -or 'ready-for-agent' -notin $taskNew.labels.name) {
    throw 'Created issue mismatch'
}
foreach ($taskEdge in $taskPlan.dependencies) {
    $taskBlocker = if ([string]$taskEdge.blocker -eq 'PT-910') {31} else {[int]$taskEdge.blocker}
    $taskActualEdge = $taskDependencies | Where-Object number -eq $taskEdge.blocked
    if ($taskBlocker -notin $taskActualEdge.blocked_by) { throw 'Dependency missing' }
}
if ((@($taskDependencies.blocked_by).Count) -ne 6) { throw 'Unexpected dependency count' }
foreach ($taskNumber in @(17,31)) {
    if (@(($taskDependencies | Where-Object number -eq $taskNumber).blocked_by).Count -ne 0) { throw 'Frontier blocked' }
}
if ($taskParent.parent -ne 30 -or 31 -notin $taskParent.sub_issues) { throw 'Parent link missing' }
$taskOverviewBefore = $taskBefore | Where-Object number -eq 1
$taskHistorical = $taskOverviewBefore.body.Substring($taskOverviewBefore.body.IndexOf('### 2026-10-05 历史推进记录'))
if (-not ($taskAfter | Where-Object number -eq 1).body.Contains($taskHistorical)) { throw 'Overview history missing' }
$taskClosedBefore = @($taskBefore | Where-Object state -eq 'CLOSED' | Select-Object -ExpandProperty number)
$taskNewlyClosed = @($taskAfter | Where-Object { $_.state -eq 'CLOSED' -and $_.number -notin $taskClosedBefore })
if ($taskNewlyClosed.Count -ne 1 -or $taskNewlyClosed[0].number -ne 2) { throw 'Unexpected close' }
if (@($taskAfter | Where-Object { $_.body -like '*privacytrace-plan:2026-10-10:PT-910*' }).Count -ne 1) { throw 'Duplicate ticket' }
$taskReceipt = [PSCustomObject]@{
    repository = $taskPlan.repository
    status = 'remote_verified'
    verified_at = [DateTimeOffset]::UtcNow.ToString('o')
    created_issue = 31
    created_url = $taskNew.url
    canonical_spec = 30
    updated_issues = $taskVerified
    closed_issues = @(2)
    native_dependencies = $taskDependencies
    original_comments_preserved = $true
    unchanged_issues_verified = $taskPlan.preserve_issues
    assignees_milestones_preserved = $true
    overview_history_preserved = $true
    parent_link_verified = $true
    ready_frontier = @(31,17)
    new_count = 1
    updated_count = 11
    dependency_count = 6
    code_commit_push_performed = $false
    feature_tests_executed = $false
}
$taskReceipt | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $taskRoot 'publication-receipt.json') -Encoding utf8
$taskPlan.status = 'remote_verified'
$taskPlan | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $taskRoot 'changes.json') -Encoding utf8
'Verified: 1 created, 11 updated, only #2 closed, 6 native edges, historical comments/spec/metadata preserved; frontier #31/#17.'

