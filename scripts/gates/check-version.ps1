param([switch]$Release)

$ErrorActionPreference = 'Stop'

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -eq 'main') {
  Write-Error 'Version gate: do not develop directly on main. Create a short-lived branch from origin/main.'
  exit 1
}

$dirty = @(git status --porcelain)
if ($Release -and $dirty.Count -gt 0) {
  Write-Error "Version gate: release requires a clean worktree. $($dirty.Count) changed path(s)."
  exit 1
}

$remote = @(git remote)
if ($remote -contains 'origin') {
  git fetch origin main --quiet
  $behind = [int](git rev-list --count 'HEAD..origin/main')
  if ($behind -gt 0) {
    Write-Warning "Version gate: branch is $behind commit(s) behind origin/main. Rebase before release."
    if ($Release) { exit 1 }
  }
}

Write-Host "Version gate: branch=$branch dirty=$($dirty.Count) release=$Release"
