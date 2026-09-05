param(
    [ValidatePattern('^[0-9a-f]{40}$')][string]$Commit,
    [int]$PullRequest,
    [ValidatePattern('^[0-9a-f]{40}$')][string]$Head,
    [switch]$Merge
)
$ErrorActionPreference = 'Stop'
if (($Commit -and $PullRequest) -or (-not $Commit -and -not $PullRequest)) {
    throw 'Specify either -Commit or -PullRequest with -Head.'
}
if ($PullRequest -and ($PullRequest -lt 1 -or -not $Head)) { throw 'A positive PR and exact Head are required.' }
if ($Merge -and -not $PullRequest) { throw '-Merge requires -PullRequest.' }
$repository = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$common = git -C $repository rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0) { throw 'Cannot locate shared Git directory.' }
$key = if ($PullRequest) { "pr-$PullRequest-$Head" } else { $Commit }
$folder = Join-Path $common "hxy-release-reports/$key"
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$arguments = @('"' + (Join-Path $PSScriptRoot 'watch_release.py') + '"')
if ($PullRequest) { $arguments += @('--pr', "$PullRequest", '--head', $Head) }
else { $arguments += @('--commit', $Commit) }
if ($Merge) { $arguments += '--merge' }
$process = Start-Process -FilePath (Get-Command python).Source -ArgumentList $arguments -WindowStyle Hidden -PassThru
Write-Output "PID: $($process.Id)"
Write-Output "Report: $(Join-Path $folder 'report.json')"
Write-Output 'Background script started; no model polling needed. Read terminal=true report on handoff.'
