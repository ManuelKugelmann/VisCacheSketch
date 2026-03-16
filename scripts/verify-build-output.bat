@echo off
REM verify-build-output.bat — Check that build output directory has required files.
REM
REM Usage:
REM     scripts\verify-build-output.bat OUTDIR
REM
REM Checks: 16RooksPattern256.txt data file, Mogwai.exe binary.
REM Called by build.yml (Windows jobs) and usable locally.

setlocal enabledelayedexpansion

if "%~1"=="" (
    echo Usage: verify-build-output.bat OUTDIR
    exit /b 1
)

set "OUTDIR=%~1"
echo [verify] Checking build output in %OUTDIR%...

set FAIL=0
if not exist "%OUTDIR%\data\ReSTIRPTPass\16RooksPattern256.txt" (
    echo [verify] FAIL: data\ReSTIRPTPass\16RooksPattern256.txt missing from build output
    set FAIL=1
) else (
    echo [verify] OK: 16RooksPattern256.txt deployed
)

if not exist "%OUTDIR%\Mogwai.exe" (
    echo [verify] FAIL: Mogwai.exe missing from build output
    set FAIL=1
) else (
    echo [verify] OK: Mogwai.exe present
)

REM ---- NRD denoiser DLLs (warn loudly, do not fail) ----
set NRD_WARN=0
if not exist "%OUTDIR%\NRDPass.dll" (
    set NRD_WARN=1
    echo.
    echo ========================================================
    echo  WARNING: NRDPass.dll MISSING from build output
    echo ========================================================
    echo.
)
if not exist "%OUTDIR%\NRD.dll" (
    set NRD_WARN=1
    echo.
    echo ========================================================
    echo  WARNING: NRD.dll MISSING from build output
    echo ========================================================
    echo.
)
if !NRD_WARN!==1 (
    echo [verify] WARNING: NRD denoiser not in build output -- output will be raw noisy radiance.
    echo [verify] Rebuild with D3D12 + packman NRD package, or ensure NRDPass is enabled in CMake.
    echo.
) else (
    echo [verify] OK: NRDPass.dll and NRD.dll present
)

if %FAIL%==1 (
    echo [verify] Data file deployment check failed!
    dir /s /b "%OUTDIR%\data" 2>nul || echo [verify] No data directory found
    exit /b 1
)

echo [verify] All checks passed.
exit /b 0
