@echo off
REM update.bat — In-repo equivalent of the one-liner install command.
REM
REM Usage:  update.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]
REM
REM What it does (same as the curl one-liner, but from inside the repo):
REM   1. git pull origin <current branch>
REM   2. scripts\quickstart.bat (download scenes, download release, run tests, launch)

setlocal enabledelayedexpansion

set "ROOT=%~dp0"

REM ---------------------------------------------------------------------------
REM Collect pass-through arguments for quickstart
REM ---------------------------------------------------------------------------
set "QS_ARGS="
:parse_args
if "%~1"=="" goto :args_done
set "QS_ARGS=%QS_ARGS% %~1"
shift
goto :parse_args
:args_done

REM ---------------------------------------------------------------------------
REM Step 1: Pull latest
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 1: Pull latest changes
echo ========================================

for /f "delims=" %%B in ('git -C "%ROOT%." rev-parse --abbrev-ref HEAD') do set "BRANCH=%%B"
echo [update] Branch: %BRANCH%
git -C "%ROOT%." pull origin %BRANCH%
if errorlevel 1 (
    echo [update] WARNING: pull failed, continuing with current checkout
)

REM ---------------------------------------------------------------------------
REM Step 2: Quickstart (scenes, release, tests, launch)
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 2: Quickstart
echo ========================================
call "%ROOT%scripts\quickstart.bat" %QS_ARGS%

endlocal
