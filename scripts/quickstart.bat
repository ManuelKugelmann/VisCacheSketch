@echo off
REM quickstart.bat — Run the full VisCacheSketch quickstart sequence (steps 0-6).
REM
REM Usage:  scripts\quickstart.bat [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
REM                                [--renderer restirpt|rtxdi|pathtracer|minimal]
REM                                [--variant vanilla|viscache]
REM                                [--skip-scenes] [--skip-pull] [--skip-launch] [--interactive]
REM
REM Steps:
REM   0. git pull                   (unless --skip-pull)
REM   1. download_release.bat       — download latest GitHub release (Mogwai)
REM   2. download_scenes.bat        (unless --skip-scenes) — bundled scenes pre-populated from release
REM   3. copy shaders/data          — copy newest .slang + data into release
REM   4. run-tests.bat              — CPU algorithm tests
REM   5. headless smoke test        — Mogwai --headless
REM   6. launch                     — Mogwai with scene
REM
REM Each script is independently callable. This script just strings them together.
REM Idempotent: safe to re-run. Each step skips work already done.

setlocal enabledelayedexpansion

REM Resolve script directory to absolute path (robust in nested call chains)
for %%F in ("%~f0") do set "SCRIPT_DIR=%%~dpF"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"
set "SCENE=VeachAjar"
set "RENDERER=restirpt"
set "VARIANT="
set "RELEASE_DIR=%ROOT%\release"
set "MEDIA_DIR=%ROOT%\release\media"
set "INTERACTIVE=0"

call "%SCRIPT_DIR%version.bat" quickstart 2>nul
set "SKIP_SCENES=0"
set "SKIP_PULL=0"
set "SKIP_LAUNCH=0"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--renderer" (set "RENDERER=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--variant" (set "VARIANT=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-scenes" (set "SKIP_SCENES=1" & shift & goto :parse_args)
if /i "%~1"=="--skip-pull" (set "SKIP_PULL=1" & shift & goto :parse_args)
if /i "%~1"=="--skip-launch" (set "SKIP_LAUNCH=1" & shift & goto :parse_args)
if /i "%~1"=="--interactive" (set "INTERACTIVE=1" & shift & goto :parse_args)
if /i "%~1"=="-i" (set "INTERACTIVE=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene ...] [--renderer ...] [--variant vanilla^|viscache] [--skip-scenes] [--skip-pull] [--skip-launch] [--interactive]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Step 0: Pull latest
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 0: Pull latest changes
echo ========================================
if "%SKIP_PULL%"=="1" (
    echo [quickstart] step 0 pull -- skipped ^(--skip-pull^)
) else (
    for /f "delims=" %%B in ('git -C "%ROOT%." rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
    if defined BRANCH (
        echo [quickstart] step 0 pull ^(branch: !BRANCH!^)
        REM Stash local changes that setup-build-system may have made (e.g. CMakeLists.txt)
        REM so pull does not fail with "local changes would be overwritten".
        git -C "%ROOT%." stash --quiet 2>nul
        git -C "%ROOT%." pull origin !BRANCH!
        if errorlevel 1 echo [quickstart] WARNING: pull failed, continuing with current checkout
        REM Re-apply stashed changes (if any); ignore conflicts since step 3 re-deploys anyway
        git -C "%ROOT%." stash pop --quiet 2>nul
    ) else (
        echo [quickstart] step 0 pull -- skipped ^(not a git repo^)
    )
)

REM ---------------------------------------------------------------------------
REM Step 1: Download release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 1: Download latest release
echo ========================================
echo [quickstart] step 1 download release
call "%SCRIPT_DIR%download_release.bat"

REM ---------------------------------------------------------------------------
REM Step 2: Download scenes (bundled scenes pre-populated from release)
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 2: Download test scenes
echo ========================================
if "%SKIP_SCENES%"=="1" (
    echo [quickstart] step 2 download scenes -- skipped ^(--skip-scenes^)
) else (
    echo [quickstart] step 2 download scenes
    call "%SCRIPT_DIR%download_scenes.bat" --dir "%MEDIA_DIR%" --yes
    if errorlevel 1 echo [quickstart] WARNING: Some scenes failed to download
)

REM ---------------------------------------------------------------------------
REM Step 3: Copy newer shaders, data, etc. to release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 3: Copy newer shaders, data, etc. to release
echo ========================================
if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [quickstart] step 3 sync shaders, scripts, data from source tree to release
    bash "%ROOT%\.scripts\sync_to_release.sh"
) else (
    echo [quickstart] step 3 deploy shaders, scripts, data -- skipped ^(no release found^)
)

REM ---------------------------------------------------------------------------
REM Step 4: Run Python tests
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 4: Run Python tests
echo ========================================
echo [quickstart] step 4 run py tests
call "%SCRIPT_DIR%run-tests.bat"
if errorlevel 1 echo [quickstart] WARNING: Some tests failed

REM ---------------------------------------------------------------------------
REM Step 5: Run headless smoke test (requires GPU — skip on CI)
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 5: Headless smoke test
echo ========================================
if "%SKIP_LAUNCH%"=="1" (
    echo [quickstart] step 5 headless smoke test -- skipped ^(--skip-launch^)
) else if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [quickstart] step 5 run headless smoke test
    "%RELEASE_DIR%\Mogwai.exe" --headless --script "%RELEASE_DIR%\scripts\VisCache\smoke_test.py"
    if errorlevel 1 (
        echo [quickstart] WARNING: Smoke test failed
    ) else (
        echo [quickstart] smoke test OK
    )
) else (
    echo [quickstart] step 5 run headless smoke test -- skipped ^(Mogwai.exe not found^)
)

REM ---------------------------------------------------------------------------
REM Step 6: Launch (requires GPU — skip on CI)
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 6: Launch
echo ========================================
if "%SKIP_LAUNCH%"=="1" (
    echo [quickstart] step 6 launch -- skipped ^(--skip-launch^)
    goto :done
)
if not exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [quickstart] step 6 launch -- skipped ^(Mogwai.exe not found^)
    echo [quickstart] Run scripts\download_release.bat first, or build from source.
    goto :done
)

REM ---- Show checkout vs release commit SHA + timestamp for diagnostics ----
set "CHECKOUT_SHA=unknown"
set "CHECKOUT_DATE=unknown"
where git >nul 2>&1 && (
    for /f "tokens=*" %%H in ('git -C "%ROOT%." rev-parse --short HEAD 2^>nul') do set "CHECKOUT_SHA=%%H"
    for /f "tokens=*" %%D in ('git -C "%ROOT%." log -1 --format^=%%ci 2^>nul') do set "CHECKOUT_DATE=%%D"
)
set "RELEASE_SHA=unknown"
set "RELEASE_VER=unknown"
if exist "%RELEASE_DIR%\.release-sha" (
    set /p RELEASE_SHA=<"%RELEASE_DIR%\.release-sha"
    set "RELEASE_SHA=!RELEASE_SHA:~0,7!"
)
if exist "%RELEASE_DIR%\.release-version" (
    set /p RELEASE_VER=<"%RELEASE_DIR%\.release-version"
)
echo [quickstart] checkout: !CHECKOUT_SHA! ^(!CHECKOUT_DATE!^)
echo [quickstart] release:  !RELEASE_SHA! ^(!RELEASE_VER!^)
if not "!CHECKOUT_SHA!"=="unknown" if not "!RELEASE_SHA!"=="unknown" (
    if not "!CHECKOUT_SHA!"=="!RELEASE_SHA!" (
        echo [quickstart] WARNING: checkout and release are from different commits -- shader/binary mismatch possible
    )
)

REM Delegate to run_release.bat (interactive menus live there, not here)
set "_LAUNCH_ARGS=--scene %SCENE% --renderer %RENDERER%"
if defined VARIANT set "_LAUNCH_ARGS=!_LAUNCH_ARGS! --variant !VARIANT!"
if "%INTERACTIVE%"=="1" set "_LAUNCH_ARGS=--interactive"
echo [quickstart] step 6 launch
call "%SCRIPT_DIR%run_release.bat" !_LAUNCH_ARGS!

:done
endlocal
