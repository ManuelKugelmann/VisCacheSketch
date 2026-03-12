# VisCacheSketch Windows bootstrap — clone, setup, quickstart.
# Usage (paste into PowerShell or cmd):
#   powershell -NoProfile -c "irm https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/install.ps1 | iex"
#
# Or from cmd:
#   powershell -NoProfile -c "irm https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/install.ps1 | iex"
#
# What this does:
#   1. Checks prerequisites (git, python)
#   2. Clones the repo (if not already in one)
#   3. Runs scripts\quickstart.bat (downloads release, scenes, tests, launches Mogwai)

$ErrorActionPreference = 'Stop'

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  VisCacheSketch Windows Bootstrap"      -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Check prerequisites ---
$missing = @()
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { $missing += 'git' }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { $missing += 'python' }

if ($missing.Count -gt 0) {
    Write-Host "ERROR: Missing prerequisites: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Install them and re-run this script." -ForegroundColor Red
    exit 1
}

# --- Determine target directory ---
$repo = "ManuelKugelmann/VisCacheSketch"
$dir  = "VisCacheSketch"

# If we're already inside the repo, use it
if (Test-Path (Join-Path $PWD ".git")) {
    $remote = git remote get-url origin 2>$null
    if ($remote -and $remote -match 'VisCacheSketch') {
        Write-Host "[bootstrap] Already inside VisCacheSketch repo at $PWD"
        $dir = $PWD
    }
}

if ($dir -eq "VisCacheSketch") {
    if (Test-Path $dir) {
        Write-Host "[bootstrap] Directory '$dir' already exists, using it."
    } else {
        Write-Host "[bootstrap] Cloning $repo..."
        git clone "https://github.com/$repo.git" $dir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: git clone failed." -ForegroundColor Red
            exit 1
        }
    }
    Set-Location $dir
}

Write-Host "[bootstrap] Working directory: $PWD"
Write-Host ""

# --- Run quickstart ---
if (Test-Path "scripts\quickstart.bat") {
    Write-Host "[bootstrap] Running scripts\quickstart.bat ..."
    Write-Host ""
    & cmd.exe /c "scripts\quickstart.bat"
} else {
    Write-Host "ERROR: scripts\quickstart.bat not found. Is this the right repo?" -ForegroundColor Red
    exit 1
}
