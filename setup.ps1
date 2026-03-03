# setup.ps1  —  MLVHF Falcor 8.0 integration setup script
# Run from the MLVHF package root: .\setup.ps1
#
# What this script does:
#   1. Initialises the Falcor submodule (external/Falcor fork with DQLin port)
#   2. Copies MLVHF source files into the Falcor tree
#   3. Patches CMakeLists.txt to register the plugins
#   4. Runs the Python unit tests
#   5. Optionally invokes CMake to configure the build
#
# Requirements:
#   - Git, CMake 3.21+, Python 3.9+, Visual Studio 2022
#   - CUDA 12.x (for NRD denoiser)
#   - Windows 10 SDK 10.0.19041+ (for SM 6.5 / DXR 1.1)

param(
    [string]$FalcorRoot,          # Override: use external Falcor instead of submodule

    [switch]$SkipCMake,           # Skip CMake configure step
    [switch]$Verbose
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Log($msg, $colour="Cyan") {
    Write-Host "[MLVHF] $msg" -ForegroundColor $colour
}
function Fail($msg) {
    Write-Host "[MLVHF] ERROR: $msg" -ForegroundColor Red
    exit 1
}
function Require($cmd) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Fail "$cmd not found in PATH. Please install it and re-run."
    }
}

# ---------------------------------------------------------------------------
# Step 0: Prerequisites
# ---------------------------------------------------------------------------
Log "Step 0: Checking prerequisites..."
Require "git"
Require "cmake"
Require "python"

# ---------------------------------------------------------------------------
# Step 1: Resolve Falcor root (submodule or external override)
# ---------------------------------------------------------------------------
if (-not $FalcorRoot) {
    $FalcorRoot = "$ScriptDir\external\Falcor"
    Log "Step 1: Using Falcor submodule at: $FalcorRoot"

    # Initialise submodule if not already done
    if (-not (Test-Path "$FalcorRoot\CMakeLists.txt")) {
        Log "  Initialising git submodule..."
        Push-Location $ScriptDir
        git submodule update --init --depth 1 external/Falcor
        if ($LASTEXITCODE -ne 0) { Fail "Failed to init Falcor submodule." }
        Pop-Location
    }
} else {
    Log "Step 1: Using external Falcor at: $FalcorRoot"
}

if (-not (Test-Path "$FalcorRoot\CMakeLists.txt")) {
    Fail "CMakeLists.txt not found in $FalcorRoot. Is this a valid Falcor root?"
}

# Verify Falcor version
$cmake_content = Get-Content "$FalcorRoot\CMakeLists.txt" -Raw
if ($cmake_content -notmatch "falcor_8|Falcor 8|version.*8\.") {
    Write-Host "[MLVHF] WARNING: Could not confirm Falcor 8.x from CMakeLists.txt." -ForegroundColor Yellow
    Write-Host "         Proceeding — verify manually if the build fails." -ForegroundColor Yellow
}

Push-Location $FalcorRoot
$gitCommit = git rev-parse --short HEAD 2>$null
Log "  Falcor commit: $gitCommit" "Green"
Pop-Location

# ---------------------------------------------------------------------------
# Step 2: Copy MLVHF source into Falcor tree
# ---------------------------------------------------------------------------
Log "Step 2: Copying MLVHF RenderPass sources..."

# VisHashFilter plugin
$vhfDst = "$FalcorRoot\Source\RenderPasses\VisHashFilter"
if (-not (Test-Path $vhfDst)) {
    New-Item -ItemType Directory -Path $vhfDst | Out-Null
}
$vhfSrc = "$ScriptDir\Source\RenderPasses\VisHashFilter"
Copy-Item "$vhfSrc\*" $vhfDst -Recurse -Force
Log "  Copied: VisHashFilter -> $vhfDst" "Green"

# ReSTIRGIPass (MLVHF integration files)
$giDst = "$FalcorRoot\Source\RenderPasses\ReSTIRGIPass"
if (-not (Test-Path $giDst)) {
    New-Item -ItemType Directory -Path $giDst | Out-Null
}
$giSrc = "$ScriptDir\Source\RenderPasses\ReSTIRGIPass"
Copy-Item "$giSrc\*" $giDst -Recurse -Force
Log "  Copied: ReSTIRGIPass -> $giDst" "Green"

# Scripts
$scriptDst = "$FalcorRoot\scripts\MLVHF"
if (-not (Test-Path $scriptDst)) {
    New-Item -ItemType Directory -Path $scriptDst | Out-Null
}
Copy-Item "$ScriptDir\scripts\*" $scriptDst -Recurse -Force
Log "  Copied: scripts -> $scriptDst" "Green"

# Tests
$testDst = "$FalcorRoot\scripts\MLVHF\tests"
if (-not (Test-Path $testDst)) {
    New-Item -ItemType Directory -Path $testDst | Out-Null
}
Copy-Item "$ScriptDir\tests\*" $testDst -Recurse -Force
Log "  Copied: tests -> $testDst" "Green"

# ---------------------------------------------------------------------------
# Step 3: Patch CMakeLists.txt to register plugins
# ---------------------------------------------------------------------------
Log "Step 3: Patching Source/RenderPasses/CMakeLists.txt..."

$rpCmake = "$FalcorRoot\Source\RenderPasses\CMakeLists.txt"
if (-not (Test-Path $rpCmake)) {
    Fail "Could not find $rpCmake"
}

$rpContent = Get-Content $rpCmake -Raw

# VisHashFilter
$vhfMarker = "add_subdirectory(VisHashFilter)"
if ($rpContent -notmatch [regex]::Escape($vhfMarker)) {
    Add-Content $rpCmake "`n$vhfMarker"
    Log "  Added: $vhfMarker" "Green"
} else {
    Log "  Already present: $vhfMarker (skipped)" "Yellow"
}

# ReSTIRGIPass
$giMarker = "add_subdirectory(ReSTIRGIPass)"
if ($rpContent -notmatch [regex]::Escape($giMarker)) {
    Add-Content $rpCmake "`n$giMarker`n"
    Log "  Added: $giMarker" "Green"
} else {
    Log "  Already present: $giMarker (skipped)" "Yellow"
}

# ---------------------------------------------------------------------------
# Step 4: Python unit tests
# ---------------------------------------------------------------------------
Log "Step 4: Running CPU unit tests..."
python "$testDst\test_vhf_convergence.py"
if ($LASTEXITCODE -ne 0) {
    Fail "Unit tests failed. Fix issues before building."
}
Log "  All unit tests passed." "Green"

# ---------------------------------------------------------------------------
# Step 5: CMake configure (optional)
# ---------------------------------------------------------------------------
if (-not $SkipCMake) {
    Log "Step 5: Configuring CMake build..."

    $buildDir = "$FalcorRoot\build\windows-vs2022-Release"
    if (-not (Test-Path $buildDir)) {
        New-Item -ItemType Directory -Path $buildDir | Out-Null
    }

    Push-Location $buildDir
    cmake $FalcorRoot `
        -G "Visual Studio 17 2022" `
        -A x64 `
        -DCMAKE_BUILD_TYPE=Release `
        -DFALCOR_GFX_D3D12=ON
    if ($LASTEXITCODE -ne 0) { Fail "CMake configure failed." }
    Pop-Location

    Log "  CMake configured. Open $buildDir\Falcor.sln in Visual Studio." "Green"
    Log "  Build target: Mogwai (builds both plugins automatically)" "Green"
} else {
    Log "Step 5: Skipped (--SkipCMake)" "Yellow"
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Log "Setup complete." "Green"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Build Mogwai in Visual Studio (Release, x64)"
Write-Host "  2. Run unit tests: python scripts/MLVHF/tests/test_vhf_convergence.py"
Write-Host "  3. Launch: Mogwai.exe --script scripts/MLVHF/MLVHF_Graph.py --scene Bistro_Interior.pyscene"
Write-Host "  4. Ablation: Mogwai.exe --script scripts/MLVHF/MLVHF_Ablation.py --scene Bistro_Interior.pyscene"
Write-Host ""
