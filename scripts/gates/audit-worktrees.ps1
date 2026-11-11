param(
  [string]$Repo = (Get-Location).Path,
  [string]$Out = "docs/design/WORKTREE-AUDIT.md"
)

$ErrorActionPreference = 'Stop'

function Get-WorktreeRows {
  $raw = git -C $Repo worktree list --porcelain
  $items = @()
  $current = $null
  foreach ($line in $raw) {
    if ($line -like 'worktree *') {
      if ($current) { $items += [pscustomobject]$current }
      $current = [ordered]@{ path = $line.Substring(9); head = ''; branch = '' }
    } elseif ($line -like 'HEAD *' -and $current) {
      $current.head = $line.Substring(5)
    } elseif ($line -like 'branch *' -and $current) {
      $current.branch = $line.Substring(7)
    }
  }
  if ($current) { $items += [pscustomobject]$current }
  return $items
}

$rows = foreach ($item in Get-WorktreeRows) {
  if (-not (Test-Path $item.path)) { continue }
  $dirty = @(git -C $item.path status --porcelain 2>$null)
  $last = (git -C $item.path log -1 --format=%cs 2>$null)
  [pscustomobject]@{
    Path = $item.path
    Branch = $item.branch
    LastCommit = $last
    DirtyFiles = $dirty.Count
    Status = if ($dirty.Count -eq 0) { 'clean' } else { 'dirty' }
  }
}

$summary = @"
# Worktree 审计

生成时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm')
仓库：$Repo

- 总数：$($rows.Count)
- clean：$(($rows | Where-Object Status -eq 'clean').Count)
- dirty：$(($rows | Where-Object Status -eq 'dirty').Count)

> 本文件只审计，不删除。删除前需确认分支已合并或改动已保存。

| 状态 | 最后提交 | 脏文件 | 分支 | 路径 |
|---|---:|---:|---|---|
"@

$body = $rows | Sort-Object Status, LastCommit | ForEach-Object {
  "| $($_.Status) | $($_.LastCommit) | $($_.DirtyFiles) | $($_.Branch) | $($_.Path) |"
}

$dir = Split-Path (Join-Path $Repo $Out) -Parent
New-Item -ItemType Directory $dir -Force | Out-Null
($summary + $body -join "`n") + "`n" | Set-Content (Join-Path $Repo $Out) -Encoding utf8
Write-Host "Wrote ${Out}: $($rows.Count) worktrees"
