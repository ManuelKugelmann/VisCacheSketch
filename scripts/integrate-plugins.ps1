# integrate-plugins.ps1 — Copy VisCache/ReSTIRPTPass into Falcor tree and patch CMake.
#
# Usage (from repo root):
#     pwsh scripts/integrate-plugins.ps1 [-FalcorDir Falcor]
#
# Called by build.yml (Windows VS2022 + Ninja jobs) and usable locally.

param(
    [string]$FalcorDir = "Falcor"
)

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------------
# 1. Copy plugin sources into Falcor render-passes directory
# ------------------------------------------------------------------
foreach ($pass in @("VisCache", "ReSTIRPTPass")) {
    $dest = "$FalcorDir/Source/RenderPasses/$pass"
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    Copy-Item "Source/RenderPasses/$pass/*" "$dest/" -Recurse -Force
    Write-Host "[integrate] Copied $pass -> $dest"
}

# Copy scripts
New-Item -ItemType Directory -Path "$FalcorDir/scripts/VisCache" -Force | Out-Null
Copy-Item "scripts/*" "$FalcorDir/scripts/VisCache/" -Recurse -Force
Write-Host "[integrate] Copied scripts -> $FalcorDir/scripts/VisCache/"

# ------------------------------------------------------------------
# 2. Patch RenderPasses/CMakeLists.txt to add our subdirectories
# ------------------------------------------------------------------
$rpCmake = "$FalcorDir/Source/RenderPasses/CMakeLists.txt"
$content = Get-Content $rpCmake -Raw
foreach ($sub in @("VisCache", "ReSTIRPTPass")) {
    if ($content -notmatch "add_subdirectory\($sub\)") {
        Add-Content $rpCmake "`nadd_subdirectory($sub)"
        Write-Host "[integrate] Patched ${rpCmake}: added $sub"
    }
}

# ------------------------------------------------------------------
# 3. Patch external/CMakeLists.txt to silence upstream build warnings
# ------------------------------------------------------------------
$extCmake = "$FalcorDir/external/CMakeLists.txt"
$extContent = Get-Content $extCmake -Raw

# C4996: fmt uses deprecated stdext::checked_array_iterator (MSVC 14.44+)
if ($extContent -notmatch "_SILENCE_STDEXT_ARR_ITERS_DEPRECATION_WARNING") {
    Add-Content $extCmake "`ntarget_compile_definitions(fmt PRIVATE _SILENCE_STDEXT_ARR_ITERS_DEPRECATION_WARNING)"
    Write-Host "[integrate] Patched fmt deprecation warning"
}

# TBB deprecation: OpenVDB pulls in tbb/task.h which TBB marks deprecated.
if ($extContent -notmatch "TBB_SUPPRESS_DEPRECATED_MESSAGES") {
    Add-Content $extCmake "`ntarget_compile_definitions(tbb INTERFACE TBB_SUPPRESS_DEPRECATED_MESSAGES=1)"
    Write-Host "[integrate] Patched TBB deprecation warning"
}

# ------------------------------------------------------------------
# 4. Patch Falcor linker flags for Debug builds
# ------------------------------------------------------------------
$falcorCmake = "$FalcorDir/Source/Falcor/CMakeLists.txt"
$falcorContent = Get-Content $falcorCmake -Raw

# LNK4098: release CRT vs debug CRT mismatch
if ($falcorContent -notmatch "NODEFAULTLIB:MSVCRT") {
    $falcorContent = $falcorContent -replace `
      '(target_link_options\(Falcor\s+PUBLIC\s+# MSVC flags\.)', `
      "`$1`n        `$<`$<AND:`$<CXX_COMPILER_ID:MSVC>,`$<CONFIG:Debug>>:/NODEFAULTLIB:MSVCRT>"
    Set-Content $falcorCmake $falcorContent -NoNewline
    Write-Host "[integrate] Patched Falcor linker flags (NODEFAULTLIB:MSVCRT)"
}

# ------------------------------------------------------------------
# 5. Strip CI path prefix from diagnostics and PDB source paths
# ------------------------------------------------------------------
$rootCmake = "$FalcorDir/CMakeLists.txt"
$rootContent = Get-Content $rootCmake -Raw
$trimPath = (Resolve-Path $FalcorDir).Path -replace '\\','/'
if ($rootContent -notmatch "d1trimfile") {
    $rootContent = $rootContent -replace `
      '(project\(Falcor[^)]*\))', `
      "`$1`nadd_compile_options(/d1trimfile:$trimPath/)"
    Set-Content $rootCmake $rootContent -NoNewline
    Write-Host "[integrate] Patched d1trimfile path stripping"
}

Write-Host "[integrate] Done."
Get-Content $rpCmake
