@echo off
REM build.bat — Build VisCacheSketch from source (local developer build).
REM
REM Usage:
REM     scripts\build.bat [--preset <preset>] [--config <config>] [--skip-setup] [--open]
REM
REM Presets:  windows-vs2022 (default), windows-ninja-msvc
REM Configs:  Release (default), Debug
REM
REM Steps:
REM   1. Init submodules + fetch packman dependencies (Falcor\setup.bat)
REM   2. Integrate VisCache/ReSTIRPTPass plugins into Falcor tree
REM   3. CMake configure
REM   4. CMake build
REM   5. Verify build output
REM
REM Requires: Visual Studio 2022 (MSVC v143), Windows SDK 10.0.19041.0, git

setlocal enabledelayedexpansion

REM Resolve paths
for %%F in ("%~f0") do set "SCRIPT_DIR=%%~dpF"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"
set "FALCOR_DIR=%ROOT%\Falcor"

set "PRESET=windows-vs2022"
set "CONFIG=Release"
set "SKIP_SETUP=0"
set "OPEN_IDE=0"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--preset" (set "PRESET=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--config" (set "CONFIG=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-setup" (set "SKIP_SETUP=1" & shift & goto :parse_args)
if /i "%~1"=="--open" (set "OPEN_IDE=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--preset windows-vs2022^|windows-ninja-msvc] [--config Release^|Debug] [--skip-setup] [--open]
exit /b 1
:args_done

echo.
echo ========================================
echo  VisCacheSketch Build
echo ========================================
echo  Preset: %PRESET%
echo  Config: %CONFIG%
echo  Falcor: %FALCOR_DIR%
echo ========================================
echo.

REM ---------------------------------------------------------------------------
REM Step 1: Setup — submodules + packman dependencies
REM ---------------------------------------------------------------------------
if "%SKIP_SETUP%"=="1" (
    echo [build] step 1 setup -- skipped ^(--skip-setup^)
) else (
    echo [build] step 1 setup ^(submodules + packman deps^)

    where git >nul 2>&1
    if errorlevel 1 (
        echo [build] ERROR: git not found on PATH
        exit /b 1
    )

    pushd "%FALCOR_DIR%"
    set "VISCACHE_ROOT=%ROOT%"
    call setup.bat
    if errorlevel 1 (
        echo [build] ERROR: Falcor setup failed
        popd
        exit /b 1
    )
    popd
    echo [build] step 1 setup -- done
)
echo.

REM ---------------------------------------------------------------------------
REM Step 2: Integrate VisCache plugins into Falcor tree
REM ---------------------------------------------------------------------------
echo [build] step 2 integrate plugins

where pwsh >nul 2>&1
if errorlevel 1 (
    where powershell >nul 2>&1
    if errorlevel 1 (
        echo [build] ERROR: Neither pwsh nor powershell found on PATH
        exit /b 1
    )
    set "PS_EXE=powershell"
) else (
    set "PS_EXE=pwsh"
)

pushd "%ROOT%"
!PS_EXE! -ExecutionPolicy Bypass -File "%SCRIPT_DIR%integrate-plugins.ps1" -FalcorDir "%FALCOR_DIR%"
if errorlevel 1 (
    echo [build] ERROR: Plugin integration failed
    popd
    exit /b 1
)
popd
echo [build] step 2 integrate plugins -- done
echo.

REM ---------------------------------------------------------------------------
REM Step 3: CMake configure
REM ---------------------------------------------------------------------------
echo [build] step 3 cmake configure ^(preset: %PRESET%^)

set "CMAKE_EXE=%FALCOR_DIR%\tools\.packman\cmake\bin\cmake.exe"
if not exist "%CMAKE_EXE%" (
    echo [build] ERROR: Packman cmake not found at %CMAKE_EXE%
    echo [build] Run without --skip-setup to fetch dependencies.
    exit /b 1
)

pushd "%FALCOR_DIR%"
"%CMAKE_EXE%" --preset %PRESET%
if errorlevel 1 (
    echo [build] ERROR: CMake configure failed
    popd
    exit /b 1
)
popd
echo [build] step 3 cmake configure -- done
echo.

REM ---------------------------------------------------------------------------
REM Step 4: Build
REM ---------------------------------------------------------------------------
echo [build] step 4 cmake build ^(%CONFIG%^)

pushd "%FALCOR_DIR%"
REM VS2022 preset uses MSBuild (/m for parallel), Ninja uses native parallel
if /i "%PRESET%"=="windows-vs2022" (
    "%CMAKE_EXE%" --build "build\%PRESET%" --config %CONFIG% -- /m
) else (
    "%CMAKE_EXE%" --build "build\%PRESET%" --config %CONFIG%
)
if errorlevel 1 (
    echo [build] ERROR: Build failed
    popd
    exit /b 1
)
popd
echo [build] step 4 cmake build -- done
echo.

REM ---------------------------------------------------------------------------
REM Step 5: Verify build output
REM ---------------------------------------------------------------------------
echo [build] step 5 verify build output

if /i "%PRESET%"=="windows-vs2022" (
    set "OUTDIR=%FALCOR_DIR%\build\%PRESET%\bin\%CONFIG%"
) else (
    set "OUTDIR=%FALCOR_DIR%\build\%PRESET%\bin\%CONFIG%"
)

call "%SCRIPT_DIR%verify-build-output.bat" "!OUTDIR!"
if errorlevel 1 (
    echo [build] WARNING: Build verification found issues
) else (
    echo [build] step 5 verify -- done
)
echo.

REM ---------------------------------------------------------------------------
REM Summary
REM ---------------------------------------------------------------------------
echo ========================================
echo  Build complete!
echo ========================================
echo  Output: !OUTDIR!
echo.
echo  Next steps:
echo    Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene ^<scene^>
echo.

if /i "%PRESET%"=="windows-vs2022" if "%OPEN_IDE%"=="1" (
    set "SLN=%FALCOR_DIR%\build\%PRESET%\Falcor.sln"
    if exist "!SLN!" (
        echo [build] Opening Visual Studio...
        start "" "!SLN!"
    )
)

endlocal
exit /b 0
