@echo off
REM run_release.bat — Launch Mogwai with a VisCache scene.
REM
REM Usage:  scripts\run_release.bat [--scene Bistro|Sponza|Arcade]
REM
REM Requires: release\Mogwai.exe (run download_release.bat first)
REM           media\ scenes (run download_scenes.bat first)

setlocal enabledelayedexpansion

set "REPO=ManuelKugelmann/VisCacheSketch"
set "ROOT=%~dp0.."
set "RELEASE_DIR=%ROOT%\release"
set "MEDIA_DIR=%ROOT%\media"
set "SCENE=Bistro"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene Bistro^|Sponza^|Arcade]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Deploy data files (e.g. 16RooksPattern256.txt) into release/data/
REM so Falcor's AssetResolver can find them at runtime.
REM ---------------------------------------------------------------------------
set "DATA_SRC=%ROOT%\Source\RenderPasses\ReSTIRPTPass\Data"
set "DATA_DST=%RELEASE_DIR%\data\ReSTIRPTPass"
if exist "%DATA_SRC%" if not exist "%DATA_DST%\16RooksPattern256.txt" (
    if not exist "%DATA_DST%" mkdir "%DATA_DST%"
    xcopy "%DATA_SRC%\*" "%DATA_DST%\" /s /y /q >nul
    echo [launch] Deployed ReSTIRPTPass data files to release\data\
)

REM ---------------------------------------------------------------------------
REM Smoke test
REM ---------------------------------------------------------------------------
if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [smoke] Running smoke test...
    "%RELEASE_DIR%\Mogwai.exe" --headless --script "%RELEASE_DIR%\scripts\VisCache\smoke_test.py"
    if errorlevel 1 (
        echo [smoke] WARNING: Smoke test failed
    ) else (
        echo [smoke] OK
    )
) else (
    echo [launch] Mogwai.exe not found -- no release downloaded.
    echo [launch] Run scripts\download_release.bat first, or build from source.
    echo [launch] Releases: https://github.com/%REPO%/releases
    exit /b 0
)

REM ---------------------------------------------------------------------------
REM Resolve scene path and launch
REM ---------------------------------------------------------------------------
set "SCENE_FILE="
if /i "%SCENE%"=="Bistro" set "SCENE_FILE=%MEDIA_DIR%\Bistro\Bistro_Interior.pyscene"
if /i "%SCENE%"=="Sponza" set "SCENE_FILE=%MEDIA_DIR%\Sponza\Sponza.pyscene"
if /i "%SCENE%"=="Arcade" set "SCENE_FILE=%MEDIA_DIR%\Arcade\Arcade.pyscene"

if "%SCENE_FILE%"=="" (
    echo [launch] Unknown scene: %SCENE%
    echo [launch] Available: Bistro, Sponza, Arcade
    exit /b 1
)

if not exist "%SCENE_FILE%" (
    echo [launch] Scene file not found: %SCENE_FILE%
    echo [launch] Run scripts\download_scenes.bat first.
    exit /b 1
)

echo [launch] Starting Mogwai with %SCENE%...
echo [launch] %RELEASE_DIR%\Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene %SCENE_FILE%
echo.
set "FALCOR_MEDIA_FOLDERS=%MEDIA_DIR%"
"%RELEASE_DIR%\Mogwai.exe" --script "%RELEASE_DIR%\scripts\VisCache\VisCache_Graph.py" --scene "%SCENE_FILE%"

endlocal
