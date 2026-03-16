@echo off
REM update.bat — In-repo equivalent of the one-liner install command.
REM
REM Usage:  update.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]
REM
REM What it does:
REM   1. git pull origin <current branch>
REM   2. If ONLY shader (.slang) files changed: copy them to release\ (fast path)
REM   3. Otherwise: full quickstart (download scenes, download release, run tests, launch)

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
REM Step 1: Record HEAD before pull
REM ---------------------------------------------------------------------------
for /f "delims=" %%H in ('git -C "%ROOT%." rev-parse HEAD') do set "OLD_HEAD=%%H"

REM ---------------------------------------------------------------------------
REM Step 2: Pull latest
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

for /f "delims=" %%H in ('git -C "%ROOT%." rev-parse HEAD') do set "NEW_HEAD=%%H"

REM ---------------------------------------------------------------------------
REM Step 2: Check what changed
REM ---------------------------------------------------------------------------
if "%OLD_HEAD%"=="%NEW_HEAD%" (
    echo [update] Already up to date.
    echo [update] Running full quickstart anyway...
    goto :full_quickstart
)

echo [update] Checking changes %OLD_HEAD:~0,8%..%NEW_HEAD:~0,8%...

REM Count files that changed and are NOT .slang
set "NON_SHADER=0"
for /f %%F in ('git -C "%ROOT%." diff --name-only "%OLD_HEAD%" "%NEW_HEAD%" ^| findstr /v /i "\.slang$"') do (
    set /a NON_SHADER+=1
)

REM Count shader files that changed
set "SHADER_COUNT=0"
for /f %%F in ('git -C "%ROOT%." diff --name-only "%OLD_HEAD%" "%NEW_HEAD%" ^| findstr /i "\.slang$"') do (
    set /a SHADER_COUNT+=1
)

if %SHADER_COUNT%==0 (
    echo [update] No shader changes detected.
    goto :full_quickstart
)

if %NON_SHADER% GTR 0 (
    echo [update] %SHADER_COUNT% shader(s) + %NON_SHADER% other file(s) changed.
    echo [update] Non-shader changes detected, running full quickstart...
    goto :full_quickstart
)

REM ---------------------------------------------------------------------------
REM Fast path: shader-only changes — copy .slang files to release directory
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Shader-only update (%SHADER_COUNT% file(s))
echo ========================================

set "RELEASE_DIR=%ROOT%release"
if not exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [update] No release found at %RELEASE_DIR% — need full quickstart.
    goto :full_quickstart
)

set "COPIED=0"
for /f "delims=" %%F in ('git -C "%ROOT%." diff --name-only "%OLD_HEAD%" "%NEW_HEAD%" ^| findstr /i "\.slang$"') do (
    set "SRC=%ROOT%%%F"
    set "REL_PATH=%%F"

    REM Map Source/RenderPasses/X/*.slang -> release/RenderPasses/X/*.slang
    echo !REL_PATH! | findstr /i "^Source\\RenderPasses\\" >nul 2>&1
    if not errorlevel 1 (
        REM Strip leading "Source\" to get RenderPasses\...\file.slang
        set "DST_REL=!REL_PATH:Source\=!"
        set "DST=%RELEASE_DIR%\!DST_REL!"

        REM Ensure destination directory exists
        for %%D in ("!DST!") do (
            if not exist "%%~dpD" mkdir "%%~dpD"
        )

        copy /y "!SRC!" "!DST!" >nul
        echo [update]   !REL_PATH! -^> release\!DST_REL!
        set /a COPIED+=1
    ) else (
        echo [update]   Skipped: %%F (not under Source\RenderPasses\)
    )
)

if %COPIED%==0 (
    echo [update] No shaders copied — falling back to full quickstart.
    goto :full_quickstart
)

echo.
echo [update] Fast shader update complete: %COPIED% file(s) copied to release\.
echo [update] Restart Mogwai to pick up the changes.
goto :done

REM ---------------------------------------------------------------------------
REM Full quickstart path
REM ---------------------------------------------------------------------------
:full_quickstart
echo.
echo ========================================
echo  Full quickstart
echo ========================================
call "%ROOT%scripts\quickstart.bat" %QS_ARGS%

:done
endlocal
