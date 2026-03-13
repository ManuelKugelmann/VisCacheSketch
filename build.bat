@echo off
REM build.bat — Update repo then build Falcor + VisCache from source.
REM
REM Usage:  build.bat [--config Release|Debug] [--preset windows-vs2022-ci|windows-ninja-msvc-ci] [--skip-scenes] [--scene <name>]
REM
REM Steps:
REM   1. update.bat  (git pull + quickstart: scenes, release, tests)
REM   2. setup.bat   (submodules, packman deps, copy sources, patch CMake)
REM   3. cmake --preset ... && cmake --build ...
REM
REM Safe to re-run: all steps are idempotent.

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "FALCOR_ROOT=%ROOT%Falcor"
set "CONFIG=Release"
set "PRESET=windows-vs2022-ci"
set "UPDATE_ARGS="

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--config" (set "CONFIG=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--preset" (set "PRESET=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-scenes" (set "UPDATE_ARGS=!UPDATE_ARGS! --skip-scenes" & shift & goto :parse_args)
if /i "%~1"=="--scene" (set "UPDATE_ARGS=!UPDATE_ARGS! --scene %~2" & shift & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--config Release^|Debug] [--preset windows-vs2022-ci^|windows-ninja-msvc-ci] [--skip-scenes] [--scene ^<name^>]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Step 1: Update (pull + quickstart)
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 1: Update (pull + quickstart)
echo ========================================
call "%ROOT%update.bat" %UPDATE_ARGS%

REM ---------------------------------------------------------------------------
REM Step 2: Setup (copies sources, patches CMake, etc.)
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 2: Setup
echo ========================================
call "%ROOT%setup.bat"
if errorlevel 1 (
    echo [build] ERROR: setup.bat failed!
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Step 3: CMake configure + build
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 3: CMake configure + build (%PRESET% / %CONFIG%)
echo ========================================

REM Use packman cmake if available, otherwise system cmake
set "CMAKE=cmake"
if exist "%FALCOR_ROOT%\tools\.packman\cmake\bin\cmake.exe" (
    set "CMAKE=%FALCOR_ROOT%\tools\.packman\cmake\bin\cmake.exe"
)

echo [build] Configuring: %CMAKE% --preset %PRESET%
"%CMAKE%" --preset %PRESET% -S "%FALCOR_ROOT%"
if errorlevel 1 (
    echo [build] ERROR: CMake configure failed!
    exit /b 1
)

echo [build] Building: %CMAKE% --build ... --config %CONFIG%
"%CMAKE%" --build "%FALCOR_ROOT%\build\%PRESET%" --config %CONFIG% -- /m
if errorlevel 1 (
    echo [build] ERROR: Build failed!
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Done
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Build complete
echo ========================================
echo [build] Output: %FALCOR_ROOT%\build\%PRESET%\bin\%CONFIG%
echo.

endlocal
