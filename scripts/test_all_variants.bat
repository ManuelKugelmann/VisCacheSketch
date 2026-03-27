@echo off
setlocal enabledelayedexpansion
REM test_all_variants.bat — Run all 8 renderer+variant combos headless.
REM Usage: scripts\test_all_variants.bat [NUM_FRAMES]

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "RELEASE=%ROOT%\release"
set "MOGWAI=%RELEASE%\Mogwai.exe"
set "RUNNER=scripts/VisCache/RunGraphHeadless.py"
set "SCENE=data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene"
set "FRAMES=%~1"
if "%FRAMES%"=="" set "FRAMES=2"

if not exist "%MOGWAI%" (
    echo [test] ERROR: Mogwai.exe not found at %MOGWAI%
    exit /b 1
)

set "PASS=0"
set "FAIL=0"
set "TOTAL=0"

for %%R in (MinimalPathTracer PathTracer RTXDI ReSTIRPT) do (
    for %%V in (Graph VisCache_Graph) do (
        set /a TOTAL+=1
        set "SCRIPT=scripts/VisCache/%%R_%%V.py"
        echo [test] %%R_%%V ...

        set "GRAPH_SCRIPT=!SCRIPT!"
        set "NUM_FRAMES=%FRAMES%"
        set "SCENE_FILE=%SCENE%"
        call "%ROOT%\scripts\mogwai_run.bat" --headless -s "%RUNNER%" >nul 2>&1
        set "EC=!errorlevel!"

        if !EC! equ 0 (
            echo [test]   PASS
            set /a PASS+=1
        ) else (
            echo [test]   FAIL (exit !EC!)
            set /a FAIL+=1
        )
    )
)

echo.
echo ========================================
echo  Results: !PASS!/!TOTAL! passed, !FAIL! failed
echo ========================================
if !FAIL! gtr 0 exit /b 1
exit /b 0
