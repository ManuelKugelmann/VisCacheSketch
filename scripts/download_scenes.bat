@echo off
REM download_scenes.bat — Download test scenes for VisCache paper experiments.
REM
REM Windows port of download_scenes.sh. Requires: curl, tar (both ship with
REM Windows 10+).
REM
REM Usage:
REM     scripts\download_scenes.bat [--dir <path>] [--yes]
REM
REM Default download directory: media\
REM --yes skips interactive prompts (download everything).

setlocal enabledelayedexpansion

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "MEDIA_DIR=%ROOT%\media"
set "SCENES_DIR=%ROOT%\scenes"
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
where tar >nul 2>&1 || (echo ERROR: tar not found in PATH & exit /b 1)

call "%~dp0version.bat" scenes 2>nul

mkdir "%MEDIA_DIR%" 2>nul
echo [scenes] Download directory: %MEDIA_DIR%

REM ---------------------------------------------------------------------------
REM 1. Arcade — bundled in release or Falcor media
REM ---------------------------------------------------------------------------
if not exist "%MEDIA_DIR%\Arcade" (
    if exist "%ROOT%\release\media\Arcade" (
        echo [scenes] Copying Arcade from release bundle...
        xcopy /E /I /Q "%ROOT%\release\media\Arcade" "%MEDIA_DIR%\Arcade" >nul
    ) else if exist "%ROOT%\Falcor\media\Arcade" (
        echo [scenes] Copying Arcade from Falcor\media\...
        xcopy /E /I /Q "%ROOT%\Falcor\media\Arcade" "%MEDIA_DIR%\Arcade" >nul
    ) else (
        echo [scenes] Arcade not found -- download release first or run setup
    )
) else (
    echo [scenes] Arcade already exists, skipping
)

REM ---------------------------------------------------------------------------
REM 2. Cornell Box — bundled in release or Falcor test_scenes
REM ---------------------------------------------------------------------------
if not exist "%MEDIA_DIR%\TestScenes" (
    if exist "%ROOT%\release\media\TestScenes" (
        echo [scenes] Copying TestScenes from release bundle...
        xcopy /E /I /Q "%ROOT%\release\media\TestScenes" "%MEDIA_DIR%\TestScenes" >nul
    ) else if exist "%ROOT%\Falcor\media\TestScenes" (
        echo [scenes] Copying TestScenes from Falcor\media\...
        xcopy /E /I /Q "%ROOT%\Falcor\media\TestScenes" "%MEDIA_DIR%\TestScenes" >nul
    ) else (
        echo [scenes] TestScenes not found -- download release first or run setup
    )
) else (
    echo [scenes] TestScenes already exists, skipping
)
REM Copy CornellBox pyscene from repo if missing
if exist "%MEDIA_DIR%\TestScenes" (
    if not exist "%MEDIA_DIR%\TestScenes\CornellBox.pyscene" (
        if exist "%SCENES_DIR%\CornellBox.pyscene" (
            copy /y "%SCENES_DIR%\CornellBox.pyscene" "%MEDIA_DIR%\TestScenes\CornellBox.pyscene" >nul
            echo [scenes] Copied CornellBox.pyscene from scenes\
        )
    )
)

REM ---------------------------------------------------------------------------
REM 3. Bistro (Amazon Lumberyard / NVIDIA ORCA)
REM    Official NVIDIA ORCA download -- CC-BY 4.0 license.
REM    The URL redirects (302) to a tokenized download; curl -L handles it.
REM    Previously: casual-effects.com/g3d/.../Bistro_v5_2.zip (dead as of 2025)
REM ---------------------------------------------------------------------------
set "BISTRO_URL=https://developer.nvidia.com/downloads/bistro"

if not exist "%MEDIA_DIR%\Bistro" (
    echo.
    echo [scenes] === Bistro ^(Amazon Lumberyard^) ===
    echo [scenes] Source: developer.nvidia.com/orca ^(NVIDIA ORCA^)
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
    REM Flatten: if zip produced a single subdirectory (e.g. Bistro_v5_2\), move contents up
    for /f "delims=" %%S in ('dir /b /ad "%MEDIA_DIR%\Bistro" 2^>nul') do (
        if exist "%MEDIA_DIR%\Bistro\%%S\*" (
            echo [scenes] Flattening %%S\ into Bistro\
            xcopy /E /I /Q /Y "%MEDIA_DIR%\Bistro\%%S\*" "%MEDIA_DIR%\Bistro\" >nul 2>nul
            rmdir /S /Q "%MEDIA_DIR%\Bistro\%%S" 2>nul
        )
    )
    REM Copy pyscenes from repo if not already present (NVIDIA ORCA ships its own too)
    for %%P in (BistroInterior.pyscene BistroExterior.pyscene) do (
        if not exist "%MEDIA_DIR%\Bistro\%%P" (
            if exist "%SCENES_DIR%\%%P" (
                copy /y "%SCENES_DIR%\%%P" "%MEDIA_DIR%\Bistro\%%P" >nul
                echo [scenes] Copied %%P from scenes\
            )
        )
    )
    echo [scenes] Bistro ready
) else (
    echo [scenes] Bistro already exists, skipping
)

REM ---------------------------------------------------------------------------
REM 4. Sponza (Crytek)
REM    GitHub mirror of the Crytek Sponza OBJ model (Frank Meinl).
REM    Previously: casual-effects.com/g3d/.../CrytekSponza/sponza.zip (dead as of 2025)
REM ---------------------------------------------------------------------------
:sponza
set "SPONZA_URL=https://github.com/jimmiebergmann/Sponza/archive/refs/heads/master.zip"

if not exist "%MEDIA_DIR%\Sponza" (
    echo.
    echo [scenes] === Sponza ^(Crytek^) ===
    echo [scenes] Source: github.com/jimmiebergmann/Sponza ^(OBJ mirror^)
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
    REM Flatten: if zip produced a single subdirectory (e.g. Sponza-master\), move contents up
    for /f "delims=" %%S in ('dir /b /ad "%MEDIA_DIR%\Sponza" 2^>nul') do (
        if exist "%MEDIA_DIR%\Sponza\%%S\*" (
            echo [scenes] Flattening %%S\ into Sponza\
            xcopy /E /I /Q /Y "%MEDIA_DIR%\Sponza\%%S\*" "%MEDIA_DIR%\Sponza\" >nul 2>nul
            rmdir /S /Q "%MEDIA_DIR%\Sponza\%%S" 2>nul
        )
    )
    REM Copy pyscene from repo if not already present
    if not exist "%MEDIA_DIR%\Sponza\Sponza.pyscene" (
        if exist "%SCENES_DIR%\Sponza.pyscene" (
            copy /y "%SCENES_DIR%\Sponza.pyscene" "%MEDIA_DIR%\Sponza\Sponza.pyscene" >nul
            echo [scenes] Copied Sponza.pyscene from scenes\
        )
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
echo.
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
echo   Mogwai.exe --scene "%MEDIA_DIR%\Bistro\BistroInterior.pyscene"
echo.


endlocal
