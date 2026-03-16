@echo off
REM update.bat — In-repo equivalent of the one-liner install command.
REM
REM Usage:  update.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]
REM
REM Delegates entirely to scripts\quickstart.bat which handles:
REM   0. git pull
REM   1. download scenes
REM   2. download release
REM   3. copy newer shaders, data, etc. to release
REM   4. run py tests
REM   5. run headless smoke test
REM   6. launch

setlocal enabledelayedexpansion

set "ROOT=%~dp0"

REM ---------------------------------------------------------------------------
REM Collect pass-through arguments for quickstart
REM ---------------------------------------------------------------------------
set "QS_ARGS="
:parse_args
if "%~1"=="" goto :args_done
set "QS_ARGS=%QS_ARGS% %~1"
shift
goto :parse_args
:args_done

call "%ROOT%scripts\quickstart.bat" %QS_ARGS%

REM ---------------------------------------------------------------------------
REM Post-update: Validate NRD (denoiser) in release
REM ---------------------------------------------------------------------------
set "RELEASE_DIR=%ROOT%release"
if exist "%RELEASE_DIR%\Mogwai.exe" (
    set "NRD_OK=1"
    if not exist "%RELEASE_DIR%\NRDPass.dll" (
        echo [update]   NRDPass.dll: MISSING
        set "NRD_OK=0"
    ) else (
        echo [update]   NRDPass.dll: OK
    )
    if not exist "%RELEASE_DIR%\NRD.dll" (
        echo [update]   NRD.dll: MISSING
        set "NRD_OK=0"
    ) else (
        echo [update]   NRD.dll: OK
    )
    if "!NRD_OK!"=="0" (
        echo [update]   WARNING: NRD denoiser not in release — denoised output unavailable.
        echo [update]   Rebuild with D3D12 + packman NRD package, or download a release that includes NRD.
    ) else (
        echo [update]   NRD denoiser: available
    )
)

endlocal
