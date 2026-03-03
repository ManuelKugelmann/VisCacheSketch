# setup.ps1  —  MLVHF Falcor 8.0 integration setup script
# Run from the MLVHF package root: .\setup.ps1 -FalcorRoot "C:\path\to\Falcor"
#
# What this script does:
#   1. Verifies Falcor 8.0 is present and at the correct commit
#   2. Clones DQLin/ReSTIR_PT and applies the Falcor 8 port patch
#   3. Copies MLVHF source files into the Falcor tree
#   4. Patches CMakeLists.txt to register the new plugin
#   5. Runs the Python unit tests
#   6. Optionally invokes CMake to configure the build
#
# Requirements:
#   - Git, CMake 3.21+, Python 3.9+, Visual Studio 2022
#   - CUDA 12.x (for NRD denoiser)
#   - Windows 10 SDK 10.0.19041+ (for SM 6.5 / DXR 1.1)

param(
    [Parameter(Mandatory=$true)]
    [string]$FalcorRoot,

    [switch]$SkipReSTIRGIPort,   # Skip DQLin/ReSTIR_PT clone (manual port)
    [switch]$SkipCMake,          # Skip CMake configure step
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
# Step 1: Verify Falcor 8.0
# ---------------------------------------------------------------------------
Log "Step 1: Verifying Falcor 8.0 at: $FalcorRoot"

if (-not (Test-Path "$FalcorRoot\CMakeLists.txt")) {
    Fail "CMakeLists.txt not found in $FalcorRoot. Is this a valid Falcor root?"
}

# Check version string in top-level CMakeLists
$cmake_content = Get-Content "$FalcorRoot\CMakeLists.txt" -Raw
if ($cmake_content -notmatch "falcor_8|Falcor 8|version.*8\.") {
    Write-Host "[MLVHF] WARNING: Could not confirm Falcor 8.x from CMakeLists.txt." -ForegroundColor Yellow
    Write-Host "         Proceeding — verify manually if the build fails." -ForegroundColor Yellow
}

# Pin commit check (Falcor 8.0 release tag)
Push-Location $FalcorRoot
$gitTag = git describe --tags --exact-match 2>$null
if ($gitTag -eq "v8.0" -or $gitTag -eq "8.0") {
    Log "Confirmed Falcor tag: $gitTag" "Green"
} else {
    $gitCommit = git rev-parse --short HEAD
    Write-Host "[MLVHF] WARNING: Not on a tagged 8.0 release (HEAD=$gitCommit, tag=$gitTag)." -ForegroundColor Yellow
    Write-Host "         Pass semantics may differ. Pin to a known-good commit if builds fail." -ForegroundColor Yellow
}
Pop-Location

# ---------------------------------------------------------------------------
# Step 2: Copy MLVHF source into Falcor tree
# ---------------------------------------------------------------------------
Log "Step 2: Copying MLVHF RenderPass sources..."

$vhfDst = "$FalcorRoot\Source\RenderPasses\VisHashFilter"
if (-not (Test-Path $vhfDst)) {
    New-Item -ItemType Directory -Path $vhfDst | Out-Null
}

$vhfSrc = "$ScriptDir\Source\RenderPasses\VisHashFilter"
Copy-Item "$vhfSrc\*" $vhfDst -Recurse -Force
Log "  Copied: $vhfSrc -> $vhfDst" "Green"

# ReSTIRGI pass delta files (user must apply manually — see docs/PORTING.md)
$giDst = "$FalcorRoot\Source\RenderPasses\ReSTIRGIPass"
if (-not (Test-Path $giDst)) {
    New-Item -ItemType Directory -Path $giDst | Out-Null
}
$giSrc = "$ScriptDir\Source\RenderPasses\ReSTIRGIPass"
Copy-Item "$giSrc\*" $giDst -Recurse -Force
Log "  Copied: ReSTIRGIPass delta files -> $giDst"

# Scripts
$scriptDst = "$FalcorRoot\scripts\MLVHF"
if (-not (Test-Path $scriptDst)) {
    New-Item -ItemType Directory -Path $scriptDst | Out-Null
}
Copy-Item "$ScriptDir\scripts\*" $scriptDst -Recurse -Force

# Tests
$testDst = "$FalcorRoot\scripts\MLVHF\tests"
if (-not (Test-Path $testDst)) {
    New-Item -ItemType Directory -Path $testDst | Out-Null
}
Copy-Item "$ScriptDir\tests\*" $testDst -Recurse -Force
Log "  Copied: tests -> $testDst" "Green"
Log "  Copied: scripts -> $scriptDst" "Green"

# ---------------------------------------------------------------------------
# Step 3: Patch CMakeLists.txt to register VisHashFilter plugin
# ---------------------------------------------------------------------------
Log "Step 3: Patching Source/RenderPasses/CMakeLists.txt..."

$rpCmake = "$FalcorRoot\Source\RenderPasses\CMakeLists.txt"
if (-not (Test-Path $rpCmake)) {
    Fail "Could not find $rpCmake"
}

$rpContent = Get-Content $rpCmake -Raw
$marker    = "add_subdirectory(VisHashFilter)"

if ($rpContent -notmatch [regex]::Escape($marker)) {
    Add-Content $rpCmake "`n$marker`n"
    Log "  Added: $marker to RenderPasses/CMakeLists.txt" "Green"
} else {
    Log "  Already present: $marker (skipped)" "Yellow"
}

# ---------------------------------------------------------------------------
# Step 4: Clone and port DQLin/ReSTIR_PT (optional)
# ---------------------------------------------------------------------------
if (-not $SkipReSTIRGIPort) {
    Log "Step 4: Cloning DQLin/ReSTIR_PT for Falcor 8.0 port..."

    $restirDir = "$FalcorRoot\Source\RenderPasses\ReSTIRGIPass\upstream"
    if (-not (Test-Path $restirDir)) {
        git clone --depth 1 https://github.com/DQLin/ReSTIR_PT.git $restirDir
        Log "  Cloned DQLin/ReSTIR_PT to: $restirDir" "Green"
    } else {
        Log "  Already cloned at $restirDir (skipped)" "Yellow"
    }

    Write-Host ""
    Write-Host "[MLVHF] Manual port required for DQLin/ReSTIR_PT → Falcor 8.0:" -ForegroundColor Yellow
    Write-Host "  See docs/PORTING.md for the step-by-step port checklist." -ForegroundColor Yellow
    Write-Host "  Key changes:" -ForegroundColor Yellow
    Write-Host "    SharedPtr<X>     → ref<X>" -ForegroundColor Yellow
    Write-Host "    Program::Desc    → ProgramDesc" -ForegroundColor Yellow
    Write-Host "    Shader::DefineList → DefineList" -ForegroundColor Yellow
    Write-Host "    Dictionary       → InternalDictionary (in RenderData)" -ForegroundColor Yellow
    Write-Host "    RenderPass::compile() signature updated" -ForegroundColor Yellow
    Write-Host ""
} else {
    Log "Step 4: Skipped (--SkipReSTIRGIPort)" "Yellow"
}

# ---------------------------------------------------------------------------
# Step 5: Python unit tests
# ---------------------------------------------------------------------------
Log "Step 5: Running CPU unit tests..."
python "$testDst\test_vhf_convergence.py"
if ($LASTEXITCODE -ne 0) {
    Fail "Unit tests failed. Fix issues before building."
}
Log "  All unit tests passed." "Green"

# ---------------------------------------------------------------------------
# Step 6: CMake configure (optional)
# ---------------------------------------------------------------------------
if (-not $SkipCMake) {
    Log "Step 6: Configuring CMake build..."

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
    Log "  Build target: Mogwai (builds VisHashFilter plugin automatically)" "Green"
} else {
    Log "Step 6: Skipped (--SkipCMake)" "Yellow"
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Log "Setup complete." "Green"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Build Mogwai in Visual Studio (Release, x64)"
Write-Host "  2. (If not skipped) Apply DQLin/ReSTIR_PT port — see docs/PORTING.md"
Write-Host "  3. Run unit tests: python scripts/MLVHF/test_vhf_convergence.py"
Write-Host "  4. Launch: Mogwai.exe --script scripts/MLVHF/MLVHF_Graph.py --scene Bistro_Interior.pyscene"
Write-Host "  5. Ablation: Mogwai.exe --script scripts/MLVHF/MLVHF_Ablation.py --scene Bistro_Interior.pyscene"
Write-Host ""
