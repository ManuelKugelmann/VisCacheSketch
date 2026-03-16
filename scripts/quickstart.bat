@echo off
REM quickstart.bat — Run the full VisCacheSketch quickstart sequence (steps 0-6).
REM
REM Usage:  scripts\quickstart.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes] [--skip-pull]
REM
REM Steps:
REM   0. git pull                   (unless --skip-pull)
REM   1. download_scenes.bat        (unless --skip-scenes)
REM   2. download_release.bat       — download latest GitHub release (Mogwai)
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
set "SCENE=Bistro"
set "RELEASE_DIR=%ROOT%\release"
set "MEDIA_DIR=%ROOT%\media"

call "%SCRIPT_DIR%version.bat" quickstart 2>nul
set "SKIP_SCENES=0"
set "SKIP_PULL=0"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-scenes" (set "SKIP_SCENES=1" & shift & goto :parse_args)
if /i "%~1"=="--skip-pull" (set "SKIP_PULL=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene Bistro^|Sponza^|Arcade] [--skip-scenes] [--skip-pull]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Step 0: Pull latest
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 0: Pull latest changes
echo ========================================
if %SKIP_PULL%==1 (
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
REM Step 1: Download scenes
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 1: Download test scenes
echo ========================================
if %SKIP_SCENES%==1 (
    echo [quickstart] step 1 download scenes -- skipped ^(--skip-scenes^)
) else (
    echo [quickstart] step 1 download scenes
    call "%SCRIPT_DIR%download_scenes.bat" --dir "%ROOT%\media" --yes
    if errorlevel 1 echo [quickstart] WARNING: Some scenes failed to download
)

REM ---------------------------------------------------------------------------
REM Step 2: Download release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 2: Download latest release
echo ========================================
echo [quickstart] step 2 download release
call "%SCRIPT_DIR%download_release.bat"

REM ---------------------------------------------------------------------------
REM Step 3: Copy newer shaders, data, etc. to release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 3: Copy newer shaders, data, etc. to release
echo ========================================
if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [quickstart] step 3 copy newer shaders, data, etc. to release

    REM Copy .slang shaders from source tree into release (only newer files)
    for %%P in (VisCache ReSTIRPTPass) do (
        set "SRC=%ROOT%\Source\RenderPasses\%%P"
        set "DST=%RELEASE_DIR%\shaders\RenderPasses\%%P"
        if exist "!SRC!" (
            if not exist "!DST!" mkdir "!DST!"
            set "_COUNT=0"
            for /f "delims=" %%F in ('xcopy "!SRC!\*.slang" "!DST!\" /D /Y /F 2^>nul') do (
                echo [quickstart]   updated: %%F
                set /a "_COUNT+=1"
            )
            if !_COUNT! equ 0 (
                echo [quickstart]   %%P shaders up to date
            ) else (
                echo [quickstart]   %%P !_COUNT! shader^(s^) updated
            )
        )
    )

    REM Copy scripts into release (only newer files)
    set "SCRIPTS_SRC=%ROOT%\scripts"
    set "SCRIPTS_DST=%RELEASE_DIR%\scripts\VisCache"
    if exist "%SCRIPTS_SRC%\smoke_test.py" (
        if not exist "!SCRIPTS_DST!" mkdir "!SCRIPTS_DST!"
        set "_COUNT=0"
        for /f "delims=" %%F in ('xcopy "%SCRIPTS_SRC%\*" "!SCRIPTS_DST!\" /s /D /Y /F 2^>nul') do (
            echo [quickstart]   updated: %%F
            set /a "_COUNT+=1"
        )
        if !_COUNT! equ 0 (
            echo [quickstart]   scripts up to date
        ) else (
            echo [quickstart]   !_COUNT! script^(s^) updated
        )
    )

    REM Copy ReSTIRPTPass data files (only newer files)
    set "DATA_SRC=%ROOT%\Source\RenderPasses\ReSTIRPTPass\Data"
    set "DATA_DST=%RELEASE_DIR%\data\ReSTIRPTPass"
    if exist "!DATA_SRC!\16RooksPattern256.txt" (
        if not exist "!DATA_DST!" mkdir "!DATA_DST!"
        set "_COUNT=0"
        for /f "delims=" %%F in ('xcopy "!DATA_SRC!\*" "!DATA_DST!\" /s /D /Y /F 2^>nul') do (
            echo [quickstart]   updated: %%F
            set /a "_COUNT+=1"
        )
        if !_COUNT! equ 0 (
            echo [quickstart]   ReSTIRPTPass data up to date
        ) else (
            echo [quickstart]   !_COUNT! data file^(s^) updated
        )
    )
) else (
    echo [quickstart] step 3 copy newer shaders, data, etc. to release -- skipped ^(no release found^)
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
REM Step 5: Run headless smoke test
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 5: Headless smoke test
echo ========================================
if exist "%RELEASE_DIR%\Mogwai.exe" (
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
REM Step 6: Launch
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 6: Launch
echo ========================================
if not exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [quickstart] step 6 launch -- skipped ^(Mogwai.exe not found^)
    echo [quickstart] Run scripts\download_release.bat first, or build from source.
    goto :done
)

set "SCENE_FILE="
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

echo [quickstart] step 6 launch ^(%SCENE%^)
echo [quickstart] %RELEASE_DIR%\Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene %SCENE_FILE%
echo.
set "FALCOR_MEDIA_FOLDERS=%MEDIA_DIR%"
"%RELEASE_DIR%\Mogwai.exe" --script "%RELEASE_DIR%\scripts\VisCache\VisCache_Graph.py" --scene "%SCENE_FILE%"

:done
endlocal
