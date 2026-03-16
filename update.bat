@echo off
REM update.bat — In-repo equivalent of the one-liner install command.
REM
REM Usage:  update.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]
REM
REM What it does:
REM   1. git pull origin <current branch>
REM   2. Copy latest shaders (.slang) from source tree into release\
REM   3. scripts\quickstart.bat (download scenes, download release, run tests, launch)

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
REM Step 2: Copy shaders to release (if release exists)
REM ---------------------------------------------------------------------------
set "RELEASE_DIR=%ROOT%release"
if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo.
    echo ========================================
    echo  Step 2: Copy shaders to release
    echo ========================================

    for %%P in (VisCache ReSTIRPTPass) do (
        set "SRC=%ROOT%Source\RenderPasses\%%P"
        set "DST=%RELEASE_DIR%\RenderPasses\%%P"
        if exist "!SRC!" (
            if not exist "!DST!" mkdir "!DST!"
            xcopy "!SRC!\*.slang" "!DST!\" /y /q >nul 2>&1
            echo [update]   %%P shaders copied
        )
    )
) else (
    echo [update] No release found, skipping shader copy.
)

REM ---------------------------------------------------------------------------
REM Step 3: Quickstart (scenes, release, tests, launch)
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 3: Quickstart
echo ========================================
call "%ROOT%scripts\quickstart.bat" %QS_ARGS%

endlocal
