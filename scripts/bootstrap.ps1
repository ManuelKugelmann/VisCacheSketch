# bootstrap.ps1 — Idempotent VisCacheSketch quickstart for PowerShell.
#
# One-liner (paste into PowerShell):
#   irm https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/bootstrap.ps1 | iex
#
# What it does:
#   1. Clones the repo (or pulls if it already exists)
#   2. Runs scripts\quickstart.bat
#
# Safe to re-run: skips clone if the directory exists, pulls latest instead.

param(
    [string]$Dir = "VisCacheSketch",
    [string]$Branch = "main",
    [string]$Scene = "",
    [switch]$SkipScenes
)

$ErrorActionPreference = "Stop"

$repo = "https://github.com/ManuelKugelmann/VisCacheSketch.git"

# ---- git version check ----
$gitVer = $null
try { $gitVer = (git --version) -replace '[^0-9.]','' } catch {}
if (-not $gitVer) {
    Write-Host "ERROR: git not found. Install git 2.43+ from https://git-scm.com" -ForegroundColor Red
    exit 1
}
$major,$minor,$patch = $gitVer.Split('.') | ForEach-Object { [int]$_ }
if ($major -lt 2 -or ($major -eq 2 -and $minor -lt 43)) {
    Write-Host "WARNING: git $gitVer detected. git 2.43+ recommended (sparse-checkout, filter)." -ForegroundColor Yellow
}

# ---- clone or pull ----
if (Test-Path (Join-Path $Dir ".git")) {
    Write-Host "[bootstrap] $Dir already exists — pulling latest..." -ForegroundColor Cyan
    Push-Location $Dir
    try {
        git fetch origin $Branch
        git checkout $Branch 2>$null
        git pull origin $Branch
    } finally {
        Pop-Location
    }
} elseif (Test-Path $Dir) {
    Write-Host "ERROR: $Dir exists but is not a git repo. Remove it or choose a different --Dir." -ForegroundColor Red
    exit 1
} else {
    Write-Host "[bootstrap] Cloning $repo..." -ForegroundColor Cyan
    git clone --branch $Branch $repo $Dir
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# ---- run quickstart ----
Push-Location $Dir
try {
    $qsArgs = @()
    if ($Scene)      { $qsArgs += "--scene"; $qsArgs += $Scene }
    if ($SkipScenes) { $qsArgs += "--skip-scenes" }

    Write-Host "[bootstrap] Running scripts\quickstart.bat $($qsArgs -join ' ')..." -ForegroundColor Cyan
    & cmd /c "scripts\quickstart.bat $($qsArgs -join ' ')"
} finally {
    Pop-Location
}
