# EchoMind Safe Report Export & Git Push Helper (no --force, no private files)
param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host ">>> [1/4] Generating read-only static report from SQLite..." -ForegroundColor Cyan
python export_static_demo.py

Write-Host ">>> [2/4] Checking remote sync status (git fetch origin)..." -ForegroundColor Cyan
git fetch origin
$counts = (git rev-list --left-right --count HEAD...origin/main).Trim() -split "\s+"
$ahead = [int]$counts[0]
$behind = [int]$counts[1]
if ($behind -gt 0) {
    Write-Host "[STOP] Local branch is behind origin/main by $behind commit(s)." -ForegroundColor Red
    Write-Host "Please reconcile with origin/main first (e.g., git pull --rebase or merge). Force push is disabled." -ForegroundColor Yellow
    exit 1
}

Write-Host ">>> [3/4] Checking working tree (will NOT auto-stage private/copyright files)..." -ForegroundColor Cyan
git status -s

if (-not $Message) {
    Write-Host "`n[INFO] Dry-run complete. Re-run with -Message `"your commit message`" after reviewing staged changes." -ForegroundColor Yellow
    exit 0
}

git add export_static_demo.py docs/index.html index.html EchoMind_Visual_Demo.html
git diff --cached --stat
git commit -m $Message

Write-Host ">>> [4/4] Pushing to origin main (fast-forward only)..." -ForegroundColor Cyan
git push origin main
Write-Host "`n>>> [DONE] Push completed safely." -ForegroundColor Green
