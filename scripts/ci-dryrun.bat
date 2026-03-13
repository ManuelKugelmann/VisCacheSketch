@echo off
REM ci-dryrun.bat — Local dry-run of CI checks (no GPU needed).
REM
REM Catches script syntax errors, missing enum symbols, Python import
REM failures, and algorithm-test regressions *before* pushing.
REM
REM Usage:
REM     scripts\ci-dryrun.bat           Run all checks
REM     scripts\ci-dryrun.bat quick     Skip algorithm tests

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
set PASS=0
set FAIL=0
set TOTAL=0

echo ========================================
echo  VisCacheSketch CI dry-run
echo ========================================
echo.

REM -------------------------------------------------------------------
REM 1. Python syntax check on all render-graph / smoke-test scripts
REM -------------------------------------------------------------------
echo [1/4] Checking Python syntax (render graph scripts)...
set /a TOTAL+=1
set "SYNTAX_FAIL=0"
for %%f in ("%ROOT_DIR%\scripts\*.py") do (
    python -m py_compile "%%f" 2>nul
    if errorlevel 1 (
        echo   FAIL: %%~nxf
        set SYNTAX_FAIL=1
    ) else (
        echo   OK:   %%~nxf
    )
)
if "%SYNTAX_FAIL%"=="0" (
    echo   All scripts parse OK.
    set /a PASS+=1
) else (
    echo   FAIL: syntax errors found.
    set /a FAIL+=1
)
echo.

REM -------------------------------------------------------------------
REM 2. Check for stale Falcor 4.x enum usage in graph scripts
REM    (SamplePattern.xxx, CullMode.CullXxx, RTXDIOptions(...), etc.)
REM -------------------------------------------------------------------
echo [2/4] Checking for stale Falcor 4.x enum references...
set /a TOTAL+=1
set "ENUM_FAIL=0"
for %%f in ("%ROOT_DIR%\scripts\VisCache_*.py" "%ROOT_DIR%\scripts\smoke_test.py") do (
    REM Use findstr for basic pattern matching (no full regex, but catches the obvious ones)
    findstr /n /r "SamplePattern\. CullMode\. RTXDIMode\. RTXDIOptions( ColorFormat\. NRDMethod\. ToneMapOp\." "%%f" >nul 2>nul
    if not errorlevel 1 (
        echo   FAIL: %%~nxf contains old-style enum references:
        findstr /n /r "SamplePattern\. CullMode\. RTXDIMode\. RTXDIOptions( ColorFormat\. NRDMethod\. ToneMapOp\." "%%f"
        set ENUM_FAIL=1
    )
)
if "%ENUM_FAIL%"=="0" (
    echo   No stale enums found.
    set /a PASS+=1
) else (
    echo   FAIL: use string literals instead of enum objects in Falcor 8.
    set /a FAIL+=1
)
echo.

REM -------------------------------------------------------------------
REM 3. Check data file deployment (16RooksPattern256.txt)
REM -------------------------------------------------------------------
echo [3/4] Checking data file presence...
set /a TOTAL+=1
set "DATA_SRC=%ROOT_DIR%\Source\RenderPasses\ReSTIRPTPass\Data\16RooksPattern256.txt"
if exist "%DATA_SRC%" (
    echo   OK: source data file exists
    set /a PASS+=1
) else (
    echo   FAIL: %DATA_SRC% not found
    set /a FAIL+=1
)
echo.

REM -------------------------------------------------------------------
REM 4. Algorithm validation tests (CPU-only, skip with "quick")
REM -------------------------------------------------------------------
if /i "%~1"=="quick" (
    echo [4/4] Algorithm tests skipped (quick mode).
    echo.
) else (
    echo [4/4] Running algorithm validation tests...
    set /a TOTAL+=1
    call "%ROOT_DIR%\scripts\run-tests.bat"
    if errorlevel 1 (
        set /a FAIL+=1
    ) else (
        set /a PASS+=1
    )
    echo.
)

REM -------------------------------------------------------------------
REM Summary
REM -------------------------------------------------------------------
echo ========================================
echo  CI dry-run: %PASS%/%TOTAL% passed, %FAIL% failed
echo ========================================

if %FAIL% gtr 0 (
    echo  Some checks failed. Fix before pushing.
    exit /b 1
)
echo  All checks passed.
exit /b 0
