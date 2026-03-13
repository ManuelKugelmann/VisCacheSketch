@echo off
REM quickstart.bat — Run the full VisCacheSketch quickstart sequence.
REM
REM Usage:  scripts\quickstart.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]
REM
REM Calls each step in order:
REM   1. download_scenes.bat   — fetch test scenes (unless --skip-scenes)
REM   2. download_release.bat  — download latest GitHub release (Mogwai)
REM   3. run-tests.bat         — CPU algorithm tests
REM   4. run_release.bat       — smoke test + launch Mogwai
REM
REM Each script is independently callable. This script just strings them together.
REM Idempotent: safe to re-run. Each step skips work already done.

setlocal enabledelayedexpansion

REM Resolve script directory to absolute path (robust in nested call chains)
for %%F in ("%~f0") do set "SCRIPT_DIR=%%~dpF"
set "ROOT=%SCRIPT_DIR%.."
set "SCENE=Bistro"

call "%SCRIPT_DIR%version.bat" quickstart 2>nul
set "SKIP_SCENES=0"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-scenes" (set "SKIP_SCENES=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene Bistro^|Sponza^|Arcade] [--skip-scenes]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM 1. Download scenes
REM ---------------------------------------------------------------------------
if %SKIP_SCENES%==1 (
    echo [quickstart] Skipping scene download ^(--skip-scenes^)
) else (
    echo.
    echo ========================================
    echo  Step 1: Download test scenes
    echo ========================================
    call "%SCRIPT_DIR%download_scenes.bat" --dir "%ROOT%\media" --yes
    if errorlevel 1 echo [quickstart] WARNING: Some scenes failed to download
)

REM ---------------------------------------------------------------------------
REM 2. Download release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 2: Download latest release
echo ========================================
call "%SCRIPT_DIR%download_release.bat"

REM ---------------------------------------------------------------------------
REM 3. Run tests
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 3: Run tests
echo ========================================
call "%SCRIPT_DIR%run-tests.bat"
if errorlevel 1 echo [quickstart] WARNING: Some tests failed

REM ---------------------------------------------------------------------------
REM 4. Launch
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 4: Launch
echo ========================================
call "%SCRIPT_DIR%run_release.bat" --scene %SCENE%

endlocal
