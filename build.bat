@echo off
REM build.bat — Update repo then build Falcor + VisCache from source.
REM
REM Usage:  build.bat [--config Release|Debug] [--preset <preset>] [--skip-setup] [--skip-scenes] [--scene <name>] [--clean] [--open]
REM
REM Presets:  windows-vs2022 (default), windows-ninja-msvc, windows-vs2022-ci, windows-ninja-msvc-ci
REM Configs:  Release (default), Debug
REM
REM Options:
REM   --skip-setup   Skip update + setup (submodules/packman/plugin integration)
REM   --skip-scenes  Skip scene downloads during update
REM   --clean        Remove stale CMakeCache before configure (fixes toolset mismatches)
REM   --open         Open the VS solution after build (VS2022 presets only)
REM
REM Steps:
REM   1. setup-build-system.bat (submodules, packman deps, copy sources, patch CMake)
REM   2. cmake --preset ... && cmake --build ... (parallel: /m for MSBuild, native for Ninja)
REM   3. verify-build-output.bat (check Mogwai.exe + data files)
REM   4. deploy build output to release\
REM
REM Safe to re-run: all steps are idempotent.

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "VISCACHE_ROOT=%ROOT%"
set "FALCOR_ROOT=%ROOT%Falcor"
set "CONFIG=Release"
set "PRESET=windows-vs2022"
set "UPDATE_ARGS="
set "SKIP_SETUP=0"
set "CLEAN_CACHE=0"
set "OPEN_IDE=0"
set "TARGETS="

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--config" (set "CONFIG=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--preset" (set "PRESET=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-setup" (set "SKIP_SETUP=1" & shift & goto :parse_args)
if /i "%~1"=="--skip-scenes" (set "UPDATE_ARGS=!UPDATE_ARGS! --skip-scenes" & shift & goto :parse_args)
if /i "%~1"=="--scene" (set "UPDATE_ARGS=!UPDATE_ARGS! --scene %~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--clean" (set "CLEAN_CACHE=1" & shift & goto :parse_args)
if /i "%~1"=="--open" (set "OPEN_IDE=1" & shift & goto :parse_args)
if /i "%~1"=="--target" (set "TARGETS=!TARGETS! --target %~2" & shift & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--config Release^|Debug] [--preset ^<preset^>] [--target ^<name^>] [--skip-setup] [--skip-scenes] [--scene ^<name^>] [--clean] [--open]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Clean stale CMake cache (before setup, since setup_vs2022.bat also configures)
REM ---------------------------------------------------------------------------
set "BUILD_DIR=%FALCOR_ROOT%\build\%PRESET%"
set "CLEAN_CMAKE=cmake"
if exist "%FALCOR_ROOT%\tools\.packman\cmake\bin\cmake.exe" (
    set "CLEAN_CMAKE=%FALCOR_ROOT%\tools\.packman\cmake\bin\cmake.exe"
)
if "%CLEAN_CACHE%"=="1" (
    if exist "!BUILD_DIR!" (
        echo [build] --clean: cleaning build artifacts...
        REM cmake --build --target clean removes all build outputs via the
        REM native build system (MSBuild/Ninja), ensuring no stale .obj files
        REM survive header changes.
        if exist "!BUILD_DIR!\CMakeCache.txt" (
            "!CLEAN_CMAKE!" --build "!BUILD_DIR!" --target clean 2>nul
        )
        echo [build] --clean: removing CMake cache for full reconfigure...
        if exist "!BUILD_DIR!\CMakeCache.txt" del /q "!BUILD_DIR!\CMakeCache.txt"
        if exist "!BUILD_DIR!\CMakeFiles" rmdir /s /q "!BUILD_DIR!\CMakeFiles"
    )
)

REM ---------------------------------------------------------------------------
REM Step 1: Setup (submodules, packman deps, copy sources, patch CMake)
REM ---------------------------------------------------------------------------
if "%SKIP_SETUP%"=="1" (
    echo.
    echo ========================================
    echo  Step 1: Setup -- skipped ^(--skip-setup^)
    echo ========================================
) else (
    echo.
    echo ========================================
    echo  Step 1: Setup ^(submodules + packman + plugins^)
    echo ========================================
    call "%ROOT%setup-build-system.bat"
    if errorlevel 1 (
        echo [build] ERROR: setup-build-system.bat failed!
        exit /b 1
    )
)

REM ---------------------------------------------------------------------------
REM Step 2: CMake configure + build
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 2: CMake configure + build (%PRESET% / %CONFIG%)
echo ========================================

REM Use packman cmake if available, otherwise system cmake
set "CMAKE=cmake"
if exist "%FALCOR_ROOT%\tools\.packman\cmake\bin\cmake.exe" (
    set "CMAKE=%FALCOR_ROOT%\tools\.packman\cmake\bin\cmake.exe"
)

set "PLUGIN_DIRS=%ROOT%Source\RenderPasses\VisCache;%ROOT%Source\RenderPasses\ReSTIRPTReferencePass;%ROOT%Source\RenderPasses\ReSTIRPTPass;%ROOT%Source\RenderPasses\ReSTIRDIPass;%ROOT%Source\RenderPasses\ReSTIRDIReferencePass;%ROOT%Source\RenderPasses\ReSTIRNEEPass"
echo [build] Configuring: %CMAKE% --preset %PRESET%
"%CMAKE%" --preset %PRESET% -S "%FALCOR_ROOT%" -DFALCOR_PLUGIN_DIRS="!PLUGIN_DIRS!" -DFALCOR_RUNTIME_OUTPUT_DIRECTORY="%ROOT%runtime" -DFALCOR_FLAT_OUTPUT=ON
if errorlevel 1 (
    echo [build] ERROR: CMake configure failed!
    exit /b 1
)

REM VS2022 presets use MSBuild; Ninja presets use native parallel.
REM --target limits the build to specific targets (e.g. --target VisCachePass --target Mogwai).
if "!TARGETS!"=="" (
    echo [build] Building: all targets (%CONFIG%)
) else (
    echo [build] Building:%TARGETS% (%CONFIG%)
)
echo "%PRESET%" | findstr /i "ninja" >nul
if errorlevel 1 (
    "%CMAKE%" --build "%FALCOR_ROOT%\build\%PRESET%" --config %CONFIG% !TARGETS!
) else (
    "%CMAKE%" --build "%FALCOR_ROOT%\build\%PRESET%" --config %CONFIG% !TARGETS!
)
if errorlevel 1 (
    echo [build] ERROR: Build failed!
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Step 3: Verify build output
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 3: Verify build output
echo ========================================
set "BUILD_OUT=%FALCOR_ROOT%\build\%PRESET%\bin\%CONFIG%"

if exist "%ROOT%scripts\verify-build-output.bat" (
    call "%ROOT%scripts\verify-build-output.bat" "!BUILD_OUT!"
    if errorlevel 1 (
        echo [build] WARNING: Build verification found issues
    )
) else (
    echo [build] verify-build-output.bat not found, skipping verification
)

REM ---------------------------------------------------------------------------
REM Step 4: Deploy build output to release\
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 4: Verify runtime output
echo ========================================
set "RUNTIME_DIR=%ROOT%runtime"

if not exist "!BUILD_OUT!\Mogwai.exe" (
    echo [build] WARNING: Mogwai.exe not found at !BUILD_OUT!
    goto :done
)

REM Sync shaders, scripts, data, and scenes from source to runtime.
echo [build] Syncing shaders, scripts, data...
bash "%ROOT%\.scripts\sync_to_runtime.sh"

:done
echo.
echo ========================================
echo  Build complete
echo ========================================
echo [build] Build output: !BUILD_OUT!
echo [build] Deployed to:  %RUNTIME_DIR%\
echo.

REM Open VS solution if requested
if "%OPEN_IDE%"=="1" (
    set "SLN=%FALCOR_ROOT%\build\%PRESET%\Falcor.sln"
    if exist "!SLN!" (
        echo [build] Opening Visual Studio: !SLN!
        start "" "!SLN!"
    ) else (
        echo [build] No .sln found at !SLN! ^(--open only works with VS2022 presets^)
    )
)

endlocal
