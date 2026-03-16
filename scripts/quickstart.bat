@echo off
REM quickstart.bat — Run the full VisCacheSketch quickstart sequence (steps 0-6).
REM
REM Usage:  scripts\quickstart.bat [--scene VeachAjar|Bistro|Sponza|Arcade] [--skip-scenes] [--skip-pull] [--skip-launch]
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
set "RELEASE_DIR=%ROOT%\release"
set "MEDIA_DIR=%ROOT%\release\media"

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
if /i "%~1"=="--skip-scenes" (set "SKIP_SCENES=1" & shift & goto :parse_args)
if /i "%~1"=="--skip-pull" (set "SKIP_PULL=1" & shift & goto :parse_args)
if /i "%~1"=="--skip-launch" (set "SKIP_LAUNCH=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene VeachAjar^|Bistro^|Sponza^|Arcade] [--skip-scenes] [--skip-pull] [--skip-launch]
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
        git -C "%ROOT%." pull origin !BRANCH!
        if errorlevel 1 echo [quickstart] WARNING: pull failed, continuing with current checkout
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
    echo [quickstart] step 3 deploy shaders, scripts, data from source tree to release

    REM ---- Deploy ALL .slang shaders (source tree is authoritative) ----
    REM Force-copy (no /D date check) — git pull/checkout timestamps are unreliable.

    REM Falcor built-in shaders: Falcor\Source\Falcor\**\*.slang → release\shaders\
    set "FALCOR_SRC=%ROOT%\Falcor\Source\Falcor"
    set "FALCOR_DST=%RELEASE_DIR%\shaders"
    if exist "!FALCOR_SRC!" (
        xcopy "!FALCOR_SRC!\*.slang" "!FALCOR_DST!\" /s /Y /q >nul 2>&1
        echo [quickstart]   Falcor built-in shaders deployed
    )

    REM Custom render pass shaders
    for %%P in (VisCache ReSTIRPTPass) do (
        set "SRC=%ROOT%\Source\RenderPasses\%%P"
        set "DST=%RELEASE_DIR%\shaders\RenderPasses\%%P"
        if exist "!SRC!" (
            if not exist "!DST!" mkdir "!DST!"
            xcopy "!SRC!\*.slang" "!DST!\" /Y /q >nul 2>&1
            echo [quickstart]   %%P shaders deployed
        )
    )

    REM ---- Deploy scripts ----
    set "SCRIPTS_SRC=%ROOT%\scripts"
    set "SCRIPTS_DST=%RELEASE_DIR%\scripts\VisCache"
    if exist "%SCRIPTS_SRC%\smoke_test.py" (
        if not exist "!SCRIPTS_DST!" mkdir "!SCRIPTS_DST!"
        xcopy "%SCRIPTS_SRC%\*" "!SCRIPTS_DST!\" /s /Y /q >nul 2>&1
        echo [quickstart]   scripts deployed
    )

    REM ---- Deploy ReSTIRPTPass data files ----
    set "DATA_SRC=%ROOT%\Source\RenderPasses\ReSTIRPTPass\Data"
    set "DATA_DST=%RELEASE_DIR%\data\ReSTIRPTPass"
    if exist "!DATA_SRC!\16RooksPattern256.txt" (
        if not exist "!DATA_DST!" mkdir "!DATA_DST!"
        xcopy "!DATA_SRC!\*" "!DATA_DST!\" /s /Y /q >nul 2>&1
        echo [quickstart]   ReSTIRPTPass data deployed
    )

    REM ---- Validate NRD (denoiser) availability in release ----
    set "NRD_OK=1"
    if not exist "%RELEASE_DIR%\NRDPass.dll" (
        echo [quickstart]   NRDPass.dll: MISSING
        set "NRD_OK=0"
    ) else (
        echo [quickstart]   NRDPass.dll: OK
    )
    if not exist "%RELEASE_DIR%\NRD.dll" (
        echo [quickstart]   NRD.dll: MISSING
        set "NRD_OK=0"
    ) else (
        echo [quickstart]   NRD.dll: OK
    )
    if "!NRD_OK!"=="0" (
        echo [quickstart]   WARNING: NRD denoiser not in release — output will be raw noisy radiance.
        echo [quickstart]   Rebuild with D3D12 + packman NRD package, or download a release that includes NRD.
    ) else (
        echo [quickstart]   NRD denoiser: available
    )

    REM ---- Validate shaders (content hash) ----
    REM Diagnostic: compare deployed vs source by SHA-256 to catch wrong
    REM locations, partial copies, or stale files from the release archive.
    where python >nul 2>&1
    if errorlevel 1 (
        echo [quickstart] python not found — skipping shader content validation
    ) else (
        python "%ROOT%\scripts\validate_shaders.py" --root-dir "%ROOT%" --release-dir "%RELEASE_DIR%"
        if errorlevel 1 (
            echo [quickstart] WARNING: Shader validation found issues ^(see above^)
        )
    )
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

set "SCENE_FILE="
if /i "%SCENE%"=="VeachAjar" set "SCENE_FILE=%RELEASE_DIR%\data\ReSTIRPTPass\VeachAjar\VeachAjar.pyscene"
if /i "%SCENE%"=="Bistro" set "SCENE_FILE=%MEDIA_DIR%\Bistro\BistroInterior.pyscene"
if /i "%SCENE%"=="Sponza" set "SCENE_FILE=%MEDIA_DIR%\Sponza\Sponza.pyscene"
if /i "%SCENE%"=="Arcade" set "SCENE_FILE=%MEDIA_DIR%\Arcade\Arcade.pyscene"

if "%SCENE_FILE%"=="" (
    echo [quickstart] step 6 launch -- skipped ^(unknown scene: %SCENE%^)
    goto :done
)

if not exist "%SCENE_FILE%" (
    echo [quickstart] step 6 launch -- skipped ^(scene file not found: %SCENE_FILE%^)
    echo [quickstart] Run scripts\download_scenes.bat first.
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
        echo [quickstart] WARNING: checkout and release are from different commits — shader/binary mismatch possible
    )
)

echo [quickstart] step 6 launch ^(%SCENE%^)
echo [quickstart] %RELEASE_DIR%\Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene %SCENE_FILE%
echo.
set "FALCOR_MEDIA_FOLDERS=%MEDIA_DIR%"
"%RELEASE_DIR%\Mogwai.exe" --script "%RELEASE_DIR%\scripts\VisCache\VisCache_Graph.py" --scene "%SCENE_FILE%"

:done
endlocal
