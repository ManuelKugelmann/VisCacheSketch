@echo off
REM run_release.bat — Launch Mogwai with a VisCache scene.
REM
REM Usage:  scripts\run_release.bat [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
REM                                 [--renderer viscache|restirpt|rtxdi|pathtracer|minimal]
REM                                 [--variant vanilla|viscache] [--interactive]
REM
REM Requires: release\Mogwai.exe (run download_release.bat first)
REM           media\ scenes (run download_scenes.bat first)

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "REPO=ManuelKugelmann/VisCache"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"

call "%SCRIPT_DIR%version.bat" launch 2>nul
set "RUNTIME_DIR=%ROOT%\runtime"
set "MEDIA_DIR=%ROOT%\runtime\media"
set "SCENE=VeachAjar"
set "RENDERER=restirpt"
set "VARIANT="
REM Default to interactive when no arguments given
if "%~1"=="" (set "INTERACTIVE=1") else (set "INTERACTIVE=0")

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--renderer" (set "RENDERER=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--variant" (set "VARIANT=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--interactive" (set "INTERACTIVE=1" & shift & goto :parse_args)
if /i "%~1"=="-i" (set "INTERACTIVE=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene ...] [--renderer ...] [--variant vanilla^|viscache] [--interactive]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Interactive selection (if --interactive or -i)
REM ---------------------------------------------------------------------------
if "%INTERACTIVE%"=="0" goto :skip_interactive_launch

echo.
echo ========================================
echo  VisCacheSketch — Interactive Launch
echo ========================================
echo.
echo  Select renderer:
echo    1. MinimalPathTracer  — lightweight, progressive accumulation
echo    2. PathTracer         — full Falcor path tracer (NEE, MIS, volumes)
echo    3. RTXDI              — ReSTIR DI direct lighting only
echo    4. ReSTIR PT          — ReSTIR path tracing (indirect + direct)
echo.
set /p "RCHOICE=  Choice [1-4, default=4]: "
if "%RCHOICE%"=="" set "RCHOICE=4"
if "%RCHOICE%"=="1" set "RENDERER=minimal"
if "%RCHOICE%"=="2" set "RENDERER=pathtracer"
if "%RCHOICE%"=="3" set "RENDERER=rtxdi"
if "%RCHOICE%"=="4" set "RENDERER=restirpt"

echo.
echo  Select variant:
echo    1. Vanilla   — no visibility cache
echo    2. VisCache  — with visibility cache
echo.
set /p "VCHOICE=  Choice [1-2, default=1]: "
if "%VCHOICE%"=="" set "VCHOICE=1"
if "%VCHOICE%"=="1" set "VARIANT=vanilla"
if "%VCHOICE%"=="2" (
    set "RENDERER=restirpt"
    set "VARIANT="
)

:ask_scene_launch
echo.
echo  Select scene:
echo    1. VeachAjar   — small test scene (no download needed)
echo    2. Bistro      — restaurant interior (~3.2 GB download)
echo    3. Sponza      — classic atrium (~70 MB download)
echo    4. Arcade      — game arcade (bundled with release)
echo    5. CornellBox  — simple box scene
echo.
set /p "SCHOICE=  Choice [1-5, default=1]: "
if "%SCHOICE%"=="" set "SCHOICE=1"
if "%SCHOICE%"=="1" set "SCENE=VeachAjar"
if "%SCHOICE%"=="2" set "SCENE=Bistro"
if "%SCHOICE%"=="3" set "SCENE=Sponza"
if "%SCHOICE%"=="4" set "SCENE=Arcade"
if "%SCHOICE%"=="5" set "SCENE=CornellBox"

echo.
echo  Selected: renderer=%RENDERER%, scene=%SCENE%
if defined VARIANT echo  Variant: %VARIANT%
echo.

:skip_interactive_launch

REM ---------------------------------------------------------------------------
REM Select graph script based on renderer + variant
REM ---------------------------------------------------------------------------
set "GRAPH_SCRIPT="
if /i "%RENDERER%"=="minimal"     set "GRAPH_SCRIPT=MinimalPathTracer_Graph.py"
if /i "%RENDERER%"=="pathtracer"  set "GRAPH_SCRIPT=PathTracer_Graph.py"
if /i "%RENDERER%"=="rtxdi"       set "GRAPH_SCRIPT=RTXDI_Graph.py"
if /i "%RENDERER%"=="restirpt"    set "GRAPH_SCRIPT=ReSTIRPT_Graph.py"

REM Apply --variant viscache: switch to per-renderer VisCache graph
if /i "%VARIANT%"=="viscache" (
    if /i "%RENDERER%"=="minimal"     set "GRAPH_SCRIPT=MinimalPathTracer_VisCache_Graph.py"
    if /i "%RENDERER%"=="pathtracer"  set "GRAPH_SCRIPT=PathTracer_VisCache_Graph.py"
    if /i "%RENDERER%"=="rtxdi"       set "GRAPH_SCRIPT=RTXDI_VisCache_Graph.py"
    if /i "%RENDERER%"=="restirpt"    set "GRAPH_SCRIPT=ReSTIRPT_VisCache_Graph.py"
)
if "%GRAPH_SCRIPT%"=="" (
    echo [launch] Unknown renderer: %RENDERER%
    echo [launch] Available: restirpt, rtxdi, pathtracer, minimal
    echo [launch] Add --variant viscache to enable visibility cache
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Sync shaders, scripts, data from source to release/
REM ---------------------------------------------------------------------------
bash "%ROOT%\.scripts\sync_to_runtime.sh"

REM ---------------------------------------------------------------------------
REM Check Mogwai.exe exists
REM ---------------------------------------------------------------------------
if not exist "%RUNTIME_DIR%\Mogwai.exe" (
    echo [launch] Mogwai.exe not found -- no release downloaded.
    echo [launch] Run scripts\download_release.bat first, or build from source.
    echo [launch] Releases: https://github.com/%REPO%/releases
    exit /b 0
)

REM ---------------------------------------------------------------------------
REM Resolve scene path and launch
REM ---------------------------------------------------------------------------
set "SCENE_FILE="
if /i "%SCENE%"=="VeachAjar" set "SCENE_FILE=%RUNTIME_DIR%\data\ReSTIRPTPass\VeachAjar\VeachAjar.pyscene"
if /i "%SCENE%"=="Bistro" set "SCENE_FILE=%MEDIA_DIR%\Bistro\BistroInterior.pyscene"
if /i "%SCENE%"=="Sponza" set "SCENE_FILE=%MEDIA_DIR%\Sponza\Sponza.pyscene"
if /i "%SCENE%"=="Arcade" set "SCENE_FILE=%MEDIA_DIR%\Arcade\Arcade.pyscene"
if /i "%SCENE%"=="CornellBox" set "SCENE_FILE=%ROOT%\scenes\CornellBox_1AreaLight.pyscene"

if "%SCENE_FILE%"=="" (
    echo [launch] Unknown scene: %SCENE%
    echo [launch] Available: VeachAjar, Bistro, Sponza, Arcade, CornellBox
    exit /b 1
)

if not exist "%SCENE_FILE%" (
    echo [launch] Scene file not found: %SCENE_FILE%
    echo [launch] Run scripts\download_scenes.bat first.
    exit /b 1
)

REM Build full script path and validate before launch.
REM Quoting a path ending in "\" on Windows causes the MSVC CRT to interpret
REM \" as an escaped quote, merging subsequent arguments into the path.
set "SCRIPT_PATH=%RUNTIME_DIR%\scripts\VisCache\%GRAPH_SCRIPT%"
if not exist "%SCRIPT_PATH%" (
    echo [launch] ERROR: Graph script not found: %SCRIPT_PATH%
    echo [launch] Check that scripts were deployed to release\scripts\VisCache\
    exit /b 1
)

echo [launch] Starting Mogwai with %SCENE% (renderer: %RENDERER%)...
echo [launch] %RUNTIME_DIR%\Mogwai.exe --script scripts\VisCache\%GRAPH_SCRIPT% --scene %SCENE_FILE%
echo.
set "FALCOR_MEDIA_FOLDERS=%MEDIA_DIR%"
"%RUNTIME_DIR%\Mogwai.exe" --script "%SCRIPT_PATH%" --scene "%SCENE_FILE%"

endlocal
