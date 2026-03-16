@echo off
REM VisCacheSketch — run all CPU algorithm tests (no GPU needed).
REM Usage: double-click or paste into PowerShell/cmd.
REM
REM   scripts\run-tests.bat            Run all 3 test suites
REM   scripts\run-tests.bat quick      Run convergence tests only

setlocal enabledelayedexpansion

REM Ensure Python outputs UTF-8 on Windows (avoids cp1252 UnicodeEncodeError)
set "PYTHONUTF8=1"

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found in PATH
    exit /b 1
)

set "PASS=0"
set "FAIL=0"
for %%I in ("%~dp0..") do set "ROOT=%%~fI"

if /i "%~1"=="quick" (
    echo === Quick: convergence tests only ===
    python "%ROOT%\tests\test_viscache_convergence.py"
    if !errorlevel! equ 0 (set /a PASS+=1) else (set /a FAIL+=1)
    goto :summary
)

echo === VisCache convergence (14 tests) ===
python "%ROOT%\tests\test_viscache_convergence.py"
if !errorlevel! equ 0 (set /a PASS+=1) else (set /a FAIL+=1)

echo.
echo === ReSTIR variants (8 tests) ===
python "%ROOT%\tests\test_restir_variants.py"
if !errorlevel! equ 0 (set /a PASS+=1) else (set /a FAIL+=1)

echo.
echo === Paper ablations (17 tests) ===
python "%ROOT%\tests\test_paper_ablations.py"
if !errorlevel! equ 0 (set /a PASS+=1) else (set /a FAIL+=1)

:summary
echo.
echo ========================================
echo   %PASS% suite(s) passed, %FAIL% suite(s) failed
echo ========================================
if %FAIL% gtr 0 exit /b 1
exit /b 0
