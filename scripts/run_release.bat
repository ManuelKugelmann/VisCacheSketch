@echo off
REM run_release.bat — Launch Mogwai with a VisCache scene.
REM
REM Usage:  scripts\run_release.bat [--scene VeachAjar|Bistro|Sponza|Arcade]
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

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene VeachAjar^|Bistro^|Sponza^|Arcade]
exit /b 1
:args_done

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
    echo [launch] WARNING: 16RooksPattern256.txt missing — ReSTIRPTPass will fail to load
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

REM Validate (diagnostic — catch wrong locations, partial copies, etc.)
where python >nul 2>&1 && (
    python "%ROOT%\scripts\validate_shaders.py" --root-dir "%ROOT%" --release-dir "%RELEASE_DIR%"
    if errorlevel 1 (
        echo [launch] WARNING: Shader validation found issues — see above
        echo [launch] Continuing launch, but expect shader compilation errors.
    )
) || (
    REM Fallback: at least check sentinel file exists
    if not exist "%RELEASE_DIR%\shaders\Scene\Material\TextureSampler.slang" (
        echo [launch] ERROR: Falcor shaders missing from release\shaders\ after deploy
        echo [launch] Check that Falcor\Source\Falcor\ contains .slang files.
        exit /b 1
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

if "%SCENE_FILE%"=="" (
    echo [launch] Unknown scene: %SCENE%
    echo [launch] Available: VeachAjar, Bistro, Sponza, Arcade
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
