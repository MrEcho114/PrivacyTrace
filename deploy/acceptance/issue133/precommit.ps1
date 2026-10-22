param(
    [Parameter(Mandatory=$true)][ValidateSet('cancel','delete')][string]$Action,
    [Parameter(Mandatory=$true)][ValidateSet('begin','retry')][string]$StartAction,
    [Parameter(Mandatory=$true)][string]$ConfigFile,
    [Parameter(Mandatory=$true)][ValidatePattern('^D[0-9]+$')][string]$Scope,
    [Parameter(Mandatory=$true)][string]$OutputDirectory
)
$ErrorActionPreference='Stop'
$output=[IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Use a new evidence directory' }
New-Item -ItemType Directory -Path $output | Out-Null
$client=Join-Path $PSScriptRoot 'client.cjs'
function Invoke-LaneClient([string]$name) {
    & node $client $name $ConfigFile *> (Join-Path $output "client-$name.log")
    if ($LASTEXITCODE -ne 0) { throw "Client action failed: $name" }
}
function Invoke-LaneControl([string]$name,[string]$label) {
    & docker exec pt133e-controller python3 -m deploy.acceptance.issue133.control $name --scope $Scope *> (Join-Path $output "$label.json")
    if ($LASTEXITCODE -ne 0) { throw "Owned controller action failed: $name" }
}
Invoke-LaneClient $StartAction
Invoke-LaneControl 'wait-scan' 'active'
Invoke-LaneControl 'scope' 'before'
$paused=$false
try {
    Invoke-LaneControl 'pause-worker' 'pause'
    $paused=$true
    Invoke-LaneControl 'wait-result' 'completed-result-before-commit'
    Invoke-LaneClient $Action
    Invoke-LaneControl 'observe' 'revoked'
} finally {
    if ($paused) { Invoke-LaneControl 'unpause-worker' 'unpause' }
}
Start-Sleep -Seconds 2
Invoke-LaneControl 'scope' 'after'
if ($Action -eq 'delete') { Invoke-LaneControl 'replay-deleted' 'old-access' }
Invoke-LaneControl 'observe' 'persistent-after-late-consumer'
