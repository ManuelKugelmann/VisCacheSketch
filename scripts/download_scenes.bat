@echo off
REM download_scenes.bat — Download test scenes for VisCache paper experiments.
REM
REM Windows port of download_scenes.sh. Requires: curl, tar (both ship with
REM Windows 10+). On older systems, or if you prefer, run via WSL:
REM     wsl bash scripts/download_scenes.sh
REM
REM Usage:
REM     scripts\download_scenes.bat [--dir <path>] [--yes]
REM
REM Default download directory: media\
REM --yes skips interactive prompts (download everything).

setlocal enabledelayedexpansion

set "ROOT=%~dp0.."
set "MEDIA_DIR=%ROOT%\media"
set "AUTO_YES=0"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--dir" (set "MEDIA_DIR=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--yes" (set "AUTO_YES=1" & shift & goto :parse_args)
if /i "%~1"=="-y" (set "AUTO_YES=1" & shift & goto :parse_args)
echo Usage: %~nx0 [--dir ^<path^>] [--yes]
exit /b 1
:args_done

where curl >nul 2>&1 || (echo ERROR: curl not found in PATH & exit /b 1)
where tar >nul 2>&1 || (echo ERROR: tar not found in PATH. Try: wsl bash scripts/download_scenes.sh & exit /b 1)

mkdir "%MEDIA_DIR%" 2>nul
echo [scenes] Download directory: %MEDIA_DIR%

REM ---------------------------------------------------------------------------
REM 1. Arcade — bundled with Falcor
REM ---------------------------------------------------------------------------
if exist "%ROOT%\Falcor\media\Arcade" (
    if not exist "%MEDIA_DIR%\Arcade" (
        echo [scenes] Copying Arcade from Falcor\media\...
        xcopy /E /I /Q "%ROOT%\Falcor\media\Arcade" "%MEDIA_DIR%\Arcade" >nul
    ) else (
        echo [scenes] Arcade already exists, skipping
    )
) else (
    echo [scenes] WARNING: Falcor\media\Arcade not found -- run setup first
)

REM ---------------------------------------------------------------------------
REM 2. Cornell Box — from Falcor test_scenes
REM ---------------------------------------------------------------------------
if exist "%ROOT%\Falcor\media\TestScenes" (
    if not exist "%MEDIA_DIR%\TestScenes" (
        echo [scenes] Copying TestScenes from Falcor\media\...
        xcopy /E /I /Q "%ROOT%\Falcor\media\TestScenes" "%MEDIA_DIR%\TestScenes" >nul
    ) else (
        echo [scenes] TestScenes already exists, skipping
    )
)

REM ---------------------------------------------------------------------------
REM 3. Bistro (Amazon Lumberyard / NVIDIA ORCA)
REM ---------------------------------------------------------------------------
set "BISTRO_URL=https://casual-effects.com/g3d/data10/research/model/Amazon_Lumberyard_Bistro/Bistro_v5_2.zip"

if not exist "%MEDIA_DIR%\Bistro" (
    echo.
    echo [scenes] === Bistro ^(Amazon Lumberyard^) ===
    echo [scenes] Source: casual-effects.com ^(Morgan McGuire mirror^)
    echo [scenes] Size: ~3.2 GB compressed
    echo.
    if %AUTO_YES%==0 (
        set /p "YN=[scenes] Download Bistro? [y/N] "
        if /i not "!YN!"=="y" (
            echo [scenes] Skipping Bistro
            goto :sponza
        )
    )
    echo [scenes] Downloading Bistro...
    set "TMPZIP=%TEMP%\Bistro_%RANDOM%.zip"
    curl -fSL --progress-bar -o "!TMPZIP!" "%BISTRO_URL%"
    if errorlevel 1 (
        echo [scenes] ERROR: Bistro download failed.
        goto :sponza
    )
    echo [scenes] Extracting Bistro...
    mkdir "%MEDIA_DIR%\Bistro" 2>nul
    tar xf "!TMPZIP!" -C "%MEDIA_DIR%\Bistro"
    del "!TMPZIP!" 2>nul
    REM Create .pyscene wrapper
    if not exist "%MEDIA_DIR%\Bistro\Bistro_Interior.pyscene" (
        (
            echo # Bistro Interior -- convenience wrapper for VisCache experiments
            echo import falcor
            echo sceneBuilder = SceneBuilder^(^)
            echo sceneBuilder.importScene^('BistroInterior.fbx'^)
        ) > "%MEDIA_DIR%\Bistro\Bistro_Interior.pyscene"
        echo [scenes] Created Bistro_Interior.pyscene wrapper
    )
    echo [scenes] Bistro ready
) else (
    echo [scenes] Bistro already exists, skipping
)

REM ---------------------------------------------------------------------------
REM 4. Sponza (Crytek / NVIDIA ORCA)
REM ---------------------------------------------------------------------------
:sponza
set "SPONZA_URL=https://casual-effects.com/g3d/data10/common/model/CrytekSponza/sponza.zip"

if not exist "%MEDIA_DIR%\Sponza" (
    echo.
    echo [scenes] === Sponza ^(Crytek^) ===
    echo [scenes] Source: casual-effects.com ^(Morgan McGuire mirror^)
    echo [scenes] Size: ~70 MB compressed
    echo.
    if %AUTO_YES%==0 (
        set /p "YN=[scenes] Download Sponza? [y/N] "
        if /i not "!YN!"=="y" (
            echo [scenes] Skipping Sponza
            goto :veachajar
        )
    )
    echo [scenes] Downloading Sponza...
    set "TMPZIP=%TEMP%\Sponza_%RANDOM%.zip"
    curl -fSL --progress-bar -o "!TMPZIP!" "%SPONZA_URL%"
    if errorlevel 1 (
        echo [scenes] ERROR: Sponza download failed.
        goto :veachajar
    )
    echo [scenes] Extracting Sponza...
    mkdir "%MEDIA_DIR%\Sponza" 2>nul
    tar xf "!TMPZIP!" -C "%MEDIA_DIR%\Sponza"
    del "!TMPZIP!" 2>nul
    if not exist "%MEDIA_DIR%\Sponza\Sponza.pyscene" (
        (
            echo # Crytek Sponza -- convenience wrapper for VisCache experiments
            echo import falcor
            echo sceneBuilder = SceneBuilder^(^)
            echo sceneBuilder.importScene^('sponza.obj'^)
        ) > "%MEDIA_DIR%\Sponza\Sponza.pyscene"
        echo [scenes] Created Sponza.pyscene wrapper
    )
    echo [scenes] Sponza ready
) else (
    echo [scenes] Sponza already exists, skipping
)

REM ---------------------------------------------------------------------------
REM 5. VeachAjar — Bitterli scene, DQLin OBJ conversion
REM    Requires git for sparse clone.
REM ---------------------------------------------------------------------------
:veachajar
set "VEACHAJAR_DEST=%ROOT%\Source\RenderPasses\ReSTIRPTPass\Data\VeachAjar"

if exist "%VEACHAJAR_DEST%\models" if exist "%VEACHAJAR_DEST%\textures" (
    echo [scenes] VeachAjar already exists, skipping
    goto :summary
)

where git >nul 2>&1 || (
    echo [scenes] git not found -- skipping VeachAjar ^(requires git for sparse clone^)
    goto :summary
)

echo.
echo [scenes] === VeachAjar ^(Bitterli scene, DQLin OBJ conversion^) ===
echo [scenes] Source: github.com/DQLin/ReSTIR_PT
echo [scenes] Size: ~62 MB ^(OBJ models + textures^)
echo.
if %AUTO_YES%==0 (
    set /p "YN=[scenes] Download VeachAjar? [y/N] "
    if /i not "!YN!"=="y" (
        echo [scenes] Skipping VeachAjar
        goto :summary
    )
)

set "VEACH_TMP=%TEMP%\veach-ajar-%RANDOM%"
echo [scenes] Cloning DQLin/ReSTIR_PT ^(sparse, models+textures only^)...
git clone --depth 1 --filter=blob:none --sparse "https://github.com/DQLin/ReSTIR_PT" "%VEACH_TMP%\repo"
if errorlevel 1 (
    echo [scenes] ERROR: git clone failed.
    goto :summary
)

pushd "%VEACH_TMP%\repo"
git sparse-checkout set "Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar/models" "Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar/textures"
popd

set "VEACH_SRC=%VEACH_TMP%\repo\Source\RenderPasses\ReSTIRPTPass\Data\VeachAjar"
if exist "%VEACH_SRC%\models" (
    mkdir "%VEACHAJAR_DEST%\models" 2>nul
    xcopy /E /I /Q "%VEACH_SRC%\models" "%VEACHAJAR_DEST%\models" >nul
) else (
    echo [scenes] ERROR: models\ not found in cloned repo
    rmdir /S /Q "%VEACH_TMP%" 2>nul
    goto :summary
)
if exist "%VEACH_SRC%\textures" (
    mkdir "%VEACHAJAR_DEST%\textures" 2>nul
    xcopy /E /I /Q "%VEACH_SRC%\textures" "%VEACHAJAR_DEST%\textures" >nul
)
rmdir /S /Q "%VEACH_TMP%" 2>nul
echo [scenes] VeachAjar ready at %VEACHAJAR_DEST%

REM ---------------------------------------------------------------------------
REM Summary
REM ---------------------------------------------------------------------------
:summary
echo.
echo [scenes] === Available scenes ===
for /d %%D in ("%MEDIA_DIR%\*") do echo   %%~nxD
if exist "%VEACHAJAR_DEST%\models" echo   VeachAjar ^(in Source tree^)

echo.
echo [scenes] Set FALCOR_MEDIA_FOLDERS to use with Mogwai:
echo   set FALCOR_MEDIA_FOLDERS=%MEDIA_DIR%
echo.
echo [scenes] Or pass --scene with full path:
echo   Mogwai.exe --scene "%MEDIA_DIR%\Bistro\Bistro_Interior.pyscene"
echo.
echo [scenes] WSL alternative: wsl bash scripts/download_scenes.sh

endlocal
