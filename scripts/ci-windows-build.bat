@echo off
REM ci-windows-build.bat — Shared CI build pipeline for Windows (VS2022 + Ninja).
REM
REM Usage:  ci-windows-build.bat <FALCOR_DIR> <PRESET> <CONFIG> [--sccache]
REM
REM Steps:  clean stale cache, configure, check NRD, build, verify,
REM         deploy scripts, smoke test, slim cache, bundle scenes.
REM
REM Called by build.yml after checkout/MSVC/submodules/packman/plugins are done.

setlocal enabledelayedexpansion

if "%~3"=="" (
    echo Usage: %~nx0 ^<FALCOR_DIR^> ^<PRESET^> ^<CONFIG^> [--sccache]
    exit /b 1
)

set "FALCOR_DIR=%~1"
set "PRESET=%~2"
set "CONFIG=%~3"
set "USE_SCCACHE=0"
if /i "%~4"=="--sccache" set "USE_SCCACHE=1"

set "BUILD_DIR=%FALCOR_DIR%\build\%PRESET%"
set "OUTDIR=%BUILD_DIR%\bin\%CONFIG%"

REM Use packman cmake if available, otherwise system cmake
set "CMAKE=cmake"
if exist "%FALCOR_DIR%\tools\.packman\cmake\bin\cmake.exe" (
    set "CMAKE=%FALCOR_DIR%\tools\.packman\cmake\bin\cmake.exe"
)

REM ---------------------------------------------------------------------------
REM 1. Clean stale CMake cache
REM ---------------------------------------------------------------------------
if not exist "%BUILD_DIR%\CMakeCache.txt" goto :configure

REM Check for source directory mismatch (repo rename, different runner path).
REM CMake stores paths with forward slashes — convert for comparison.
for %%I in ("%FALCOR_DIR%") do set "FALCOR_ABS=%%~fI"
set "FALCOR_FWD=!FALCOR_ABS:\=/!"
findstr /C:"!FALCOR_FWD!" "%BUILD_DIR%\CMakeCache.txt" >nul 2>&1
if errorlevel 1 goto :clean_cache

REM Check for toolchain mismatch
findstr /C:"host=x64" "%BUILD_DIR%\CMakeCache.txt" >nul 2>&1
if not errorlevel 1 goto :configure

:clean_cache
echo [build] Stale CMakeCache.txt detected, removing...
del /q "%BUILD_DIR%\CMakeCache.txt"
if exist "%BUILD_DIR%\CMakeFiles" rmdir /s /q "%BUILD_DIR%\CMakeFiles"

REM ---------------------------------------------------------------------------
REM 2. CMake Configure
REM ---------------------------------------------------------------------------
:configure
echo [build] Configuring: %CMAKE% --preset %PRESET%
if "%USE_SCCACHE%"=="1" (
    "%CMAKE%" --preset %PRESET% -S "%FALCOR_DIR%" -DCMAKE_C_COMPILER_LAUNCHER=sccache -DCMAKE_CXX_COMPILER_LAUNCHER=sccache
) else (
    "%CMAKE%" --preset %PRESET% -S "%FALCOR_DIR%"
)
if errorlevel 1 (
    echo [build] ERROR: CMake configure failed!
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM 3. Check NRD availability
REM ---------------------------------------------------------------------------
if exist "%BUILD_DIR%\Source\RenderPasses\NRDPass" (
    echo [build] NRDPass: ENABLED
) else (
    echo.
    echo ========================================================
    echo  WARNING: NRDPass DISABLED - missing NRD package or D3D12
    echo  The release will NOT include NRD denoiser support.
    echo  Output will be raw noisy radiance.
    echo ========================================================
    echo.
    echo ::warning::NRDPass DISABLED - release will not include NRD denoiser
)

REM ---------------------------------------------------------------------------
REM 4. Build
REM ---------------------------------------------------------------------------
echo [build] Building: %CMAKE% --build ... --config %CONFIG%
echo "%PRESET%" | findstr /i "ninja" >nul
if errorlevel 1 (
    "%CMAKE%" --build "%BUILD_DIR%" --config %CONFIG% -- /m
) else (
    "%CMAKE%" --build "%BUILD_DIR%" --config %CONFIG%
)
if errorlevel 1 (
    echo [build] ERROR: Build failed!
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM 5. Print sccache stats (if enabled)
REM ---------------------------------------------------------------------------
if "%USE_SCCACHE%"=="1" (
    sccache --show-stats 2>nul
)

REM ---------------------------------------------------------------------------
REM 6. Verify build output
REM ---------------------------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%verify-build-output.bat" (
    call "%SCRIPT_DIR%verify-build-output.bat" "%OUTDIR%"
)

REM ---------------------------------------------------------------------------
REM 7. Deploy scripts to build output
REM ---------------------------------------------------------------------------
if /i not "%CONFIG%"=="Release" goto :skip_deploy
if not exist "%OUTDIR%\scripts\VisCache" mkdir "%OUTDIR%\scripts\VisCache"
xcopy "%SCRIPT_DIR%*" "%OUTDIR%\scripts\VisCache\" /s /y /q >nul
echo [build] Deployed scripts to %OUTDIR%\scripts\VisCache\
:skip_deploy

REM ---------------------------------------------------------------------------
REM 8. Headless smoke test (Release only, expected to fail without GPU)
REM ---------------------------------------------------------------------------
if /i not "%CONFIG%"=="Release" goto :skip_smoke
echo [build] Attempting headless smoke test (no GPU expected)...
"%OUTDIR%\Mogwai.exe" --headless --script "%OUTDIR%\scripts\VisCache\smoke_test.py" 2>&1 || (
    echo [build] Mogwai exited — expected without GPU
)
:skip_smoke

REM ---------------------------------------------------------------------------
REM 9. Slim CMake build cache (strip PDB/ILK to cut ~60-80% size)
REM ---------------------------------------------------------------------------
echo [build] Slimming build cache...
echo [cache] Before cleanup:
powershell -NoProfile -Command "$s=(Get-ChildItem '%BUILD_DIR%' -Recurse -File -ErrorAction SilentlyContinue|Measure-Object -Property Length -Sum).Sum; '{0:N0} MB' -f ($s/1MB)"
del /s /q "%BUILD_DIR%\*.pdb" >nul 2>&1
del /s /q "%BUILD_DIR%\*.ilk" >nul 2>&1
del /s /q "%BUILD_DIR%\*.exp" >nul 2>&1
del /s /q "%BUILD_DIR%\*.ipdb" >nul 2>&1
del /s /q "%BUILD_DIR%\*.iobj" >nul 2>&1
if exist "%BUILD_DIR%\bin" rmdir /s /q "%BUILD_DIR%\bin"
echo [cache] After cleanup:
powershell -NoProfile -Command "$s=(Get-ChildItem '%BUILD_DIR%' -Recurse -File -ErrorAction SilentlyContinue|Measure-Object -Property Length -Sum).Sum; '{0:N0} MB' -f ($s/1MB)"

REM ---------------------------------------------------------------------------
REM 10. Bundle Falcor media scenes (Release only)
REM ---------------------------------------------------------------------------
if /i not "%CONFIG%"=="Release" goto :done
if exist "%FALCOR_DIR%\media\Arcade" (
    xcopy "%FALCOR_DIR%\media\Arcade" "%OUTDIR%\media\Arcade\" /s /y /q >nul
    echo [build] Bundled Arcade scene
)
if exist "%FALCOR_DIR%\media\TestScenes" (
    xcopy "%FALCOR_DIR%\media\TestScenes" "%OUTDIR%\media\TestScenes\" /s /y /q >nul
    echo [build] Bundled TestScenes
)

:done
echo [build] CI build pipeline complete (%PRESET% / %CONFIG%)
exit /b 0
