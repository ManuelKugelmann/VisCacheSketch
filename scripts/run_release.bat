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

set "REPO=ManuelKugelmann/VisCacheSketch"
for %%I in ("%~dp0..") do set "ROOT=%%~fI"

call "%~dp0version.bat" launch 2>nul
set "RELEASE_DIR=%ROOT%\release"
set "MEDIA_DIR=%ROOT%\release\media"
set "SCENE=VeachAjar"
set "RENDERER=viscache"
set "VARIANT="
set "INTERACTIVE=0"

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
echo    5. VisCache           — full VisCache pipeline (ReSTIR PT + visibility cache)
echo.
set /p "RCHOICE=  Choice [1-5, default=5]: "
if "%RCHOICE%"=="" set "RCHOICE=5"
if "%RCHOICE%"=="1" set "RENDERER=minimal"
if "%RCHOICE%"=="2" set "RENDERER=pathtracer"
if "%RCHOICE%"=="3" set "RENDERER=rtxdi"
if "%RCHOICE%"=="4" set "RENDERER=restirpt"
if "%RCHOICE%"=="5" set "RENDERER=viscache"

REM Ask variant for all renderers except viscache (already includes VisCache)
if /i "%RENDERER%"=="viscache" goto :ask_scene_launch

echo.
echo  Select variant:
echo    1. Vanilla   — no visibility cache
echo    2. VisCache  — with visibility cache
echo.
set /p "VCHOICE=  Choice [1-2, default=1]: "
if "%VCHOICE%"=="" set "VCHOICE=1"
if "%VCHOICE%"=="1" set "VARIANT=vanilla"
if "%VCHOICE%"=="2" (
    set "RENDERER=viscache"
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
if /i "%RENDERER%"=="viscache"    set "GRAPH_SCRIPT=VisCache_Graph.py"
if /i "%RENDERER%"=="minimal"     set "GRAPH_SCRIPT=MinimalPathTracer_Graph.py"
if /i "%RENDERER%"=="pathtracer"  set "GRAPH_SCRIPT=PathTracer_Graph.py"
if /i "%RENDERER%"=="rtxdi"       set "GRAPH_SCRIPT=RTXDI_Graph.py"
if /i "%RENDERER%"=="restirpt"    set "GRAPH_SCRIPT=ReSTIRPT_Graph.py"

REM Apply --variant viscache: switch to per-renderer VisCache graph
if /i "%VARIANT%"=="viscache" (
    if /i "%RENDERER%"=="minimal"     set "GRAPH_SCRIPT=MinimalPathTracer_VisCache_Graph.py"
    if /i "%RENDERER%"=="pathtracer"  set "GRAPH_SCRIPT=PathTracer_VisCache_Graph.py"
    if /i "%RENDERER%"=="rtxdi"       set "GRAPH_SCRIPT=RTXDI_VisCache_Graph.py"
    if /i "%RENDERER%"=="restirpt"    set "GRAPH_SCRIPT=VisCache_Graph.py"
)
if "%GRAPH_SCRIPT%"=="" (
    echo [launch] Unknown renderer: %RENDERER%
    echo [launch] Available: viscache, restirpt, rtxdi, pathtracer, minimal
    echo [launch] Add --variant viscache to enable visibility cache with any renderer
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Deploy fresh scripts from source tree into release/scripts/VisCache/
REM so the release always uses up-to-date graph configs and smoke tests.
REM ---------------------------------------------------------------------------
set "SCRIPTS_SRC=%ROOT%\scripts"
set "SCRIPTS_DST=%RELEASE_DIR%\scripts\VisCache"
if exist "%SCRIPTS_SRC%\smoke_test.py" (
    if not exist "%SCRIPTS_DST%" mkdir "%SCRIPTS_DST%"
    set "_COUNT=0"
    for /f "delims=" %%F in ('xcopy "%SCRIPTS_SRC%\*" "%SCRIPTS_DST%\" /s /D /Y /F 2^>nul') do (
        echo [launch]   updated: %%F
        set /a "_COUNT+=1"
    )
    if !_COUNT! gtr 0 echo [launch] !_COUNT! script^(s^) updated in release\scripts\VisCache\
)

REM ---------------------------------------------------------------------------
REM Deploy data files (e.g. 16RooksPattern256.txt) into release/data/
REM so Falcor's AssetResolver can find them at runtime.
REM ---------------------------------------------------------------------------
set "DATA_SRC=%ROOT%\Source\RenderPasses\ReSTIRPTPass\Data"
set "DATA_DST=%RELEASE_DIR%\data\ReSTIRPTPass"
if not exist "%DATA_DST%\16RooksPattern256.txt" (
    if exist "%DATA_SRC%\16RooksPattern256.txt" (
        if not exist "%DATA_DST%" mkdir "%DATA_DST%"
        xcopy "%DATA_SRC%\*" "%DATA_DST%\" /s /y /q >nul
        echo [launch] Deployed ReSTIRPTPass data files to release\data\
    ) else (
        echo [launch] WARNING: %DATA_SRC%\16RooksPattern256.txt not found in source tree
    )
)
REM Verify data file is present before smoke test
if not exist "%DATA_DST%\16RooksPattern256.txt" (
    echo [launch] WARNING: 16RooksPattern256.txt missing -- ReSTIRPTPass will fail to load
    echo [launch] Expected at: %DATA_DST%\16RooksPattern256.txt
)

REM ---------------------------------------------------------------------------
REM Deploy shaders from source tree (source is always authoritative)
REM ---------------------------------------------------------------------------
REM Force-copy all .slang from source → release/shaders/ so deployed shaders
REM always match the current checkout.  Git timestamps are unreliable, so we
REM skip date checks and always overwrite.

REM Falcor built-in shaders
set "FALCOR_SRC=%ROOT%\Falcor\Source\Falcor"
if exist "%FALCOR_SRC%" (
    xcopy "%FALCOR_SRC%\*.slang" "%RELEASE_DIR%\shaders\" /s /Y /q >nul 2>&1
)

REM Custom render pass shaders
for %%P in (VisCache ReSTIRPTPass) do (
    set "PASS_SRC=%ROOT%\Source\RenderPasses\%%P"
    set "PASS_DST=%RELEASE_DIR%\shaders\RenderPasses\%%P"
    if exist "!PASS_SRC!" (
        if not exist "!PASS_DST!" mkdir "!PASS_DST!"
        xcopy "!PASS_SRC!\*.slang" "!PASS_DST!\" /Y /q >nul 2>&1
    )
)
echo [launch] Shaders deployed from source tree

REM ---- Validate NRD (denoiser) availability in release ----
set "NRD_OK=1"
if not exist "%RELEASE_DIR%\NRDPass.dll" (
    echo [launch]   NRDPass.dll: MISSING
    set "NRD_OK=0"
) else (
    echo [launch]   NRDPass.dll: OK
)
if not exist "%RELEASE_DIR%\NRD.dll" (
    echo [launch]   NRD.dll: MISSING
    set "NRD_OK=0"
) else (
    echo [launch]   NRD.dll: OK
)
if "!NRD_OK!"=="0" (
    echo [launch]   WARNING: NRD denoiser not in release -- output will be raw noisy radiance.
    echo [launch]   Rebuild with D3D12 + packman NRD package, or download a release that includes NRD.
) else (
    echo [launch]   NRD denoiser: available
)

REM Validate (diagnostic -- catch wrong locations, partial copies, etc.)
where python >nul 2>&1
if errorlevel 1 (
    REM Fallback: at least check sentinel file exists
    if not exist "%RELEASE_DIR%\shaders\Scene\Material\TextureSampler.slang" (
        echo [launch] ERROR: Falcor shaders missing from release\shaders\ after deploy
        echo [launch] Check that Falcor\Source\Falcor\ contains .slang files.
        exit /b 1
    )
) else (
    python "%ROOT%\scripts\validate_shaders.py" --root-dir "%ROOT%" --release-dir "%RELEASE_DIR%"
    if errorlevel 1 (
        echo [launch] WARNING: Shader validation found issues -- see above
        echo [launch] Continuing launch, but expect shader compilation errors.
    )
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
if /i "%SCENE%"=="VeachAjar" set "SCENE_FILE=%RELEASE_DIR%\data\ReSTIRPTPass\VeachAjar\VeachAjar.pyscene"
if /i "%SCENE%"=="Bistro" set "SCENE_FILE=%MEDIA_DIR%\Bistro\BistroInterior.pyscene"
if /i "%SCENE%"=="Sponza" set "SCENE_FILE=%MEDIA_DIR%\Sponza\Sponza.pyscene"
if /i "%SCENE%"=="Arcade" set "SCENE_FILE=%MEDIA_DIR%\Arcade\Arcade.pyscene"
if /i "%SCENE%"=="CornellBox" set "SCENE_FILE=%ROOT%\scenes\CornellBox.pyscene"

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
set "SCRIPT_PATH=%RELEASE_DIR%\scripts\VisCache\%GRAPH_SCRIPT%"
if not exist "%SCRIPT_PATH%" (
    echo [launch] ERROR: Graph script not found: %SCRIPT_PATH%
    echo [launch] Check that scripts were deployed to release\scripts\VisCache\
    exit /b 1
)

echo [launch] Starting Mogwai with %SCENE% (renderer: %RENDERER%)...
echo [launch] %RELEASE_DIR%\Mogwai.exe --script scripts\VisCache\%GRAPH_SCRIPT% --scene %SCENE_FILE%
echo.
set "FALCOR_MEDIA_FOLDERS=%MEDIA_DIR%"
"%RELEASE_DIR%\Mogwai.exe" --script "%SCRIPT_PATH%" --scene "%SCENE_FILE%"

endlocal
