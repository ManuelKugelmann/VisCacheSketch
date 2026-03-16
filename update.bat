@echo off
REM update.bat — Pull latest + download release + deploy shaders/data.
REM
REM Usage:  update.bat [--skip-scenes]
REM
REM For the full flow (tests + smoke test + launch), use quickstart.bat instead.

setlocal enabledelayedexpansion

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
set "RELEASE_DIR=%ROOT%\release"
set "MEDIA_DIR=%ROOT%\release\media"
set "SKIP_SCENES=0"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--skip-scenes" (set "SKIP_SCENES=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--skip-scenes]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Step 1: Pull latest
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 1: Pull latest changes
echo ========================================
for /f "delims=" %%B in ('git -C "%ROOT%." rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%B"
if defined BRANCH (
    echo [update] branch: !BRANCH!
    git -C "%ROOT%." pull origin !BRANCH!
    if errorlevel 1 echo [update] WARNING: pull failed, continuing with current checkout
) else (
    echo [update] not a git repo, skipping pull
)

REM ---------------------------------------------------------------------------
REM Step 2: Download release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 2: Download latest release
echo ========================================
call "%ROOT%\scripts\download_release.bat"

REM ---------------------------------------------------------------------------
REM Step 3: Download scenes
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 3: Download scenes
echo ========================================
if "%SKIP_SCENES%"=="1" (
    echo [update] skipping scene download ^(--skip-scenes^)
) else (
    call "%ROOT%\scripts\download_scenes.bat" --dir "%MEDIA_DIR%" --yes
    if errorlevel 1 echo [update] WARNING: Some scenes failed to download
)

REM ---------------------------------------------------------------------------
REM Step 4: Deploy shaders, data, scripts to release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 4: Deploy shaders and data
echo ========================================
if exist "%RELEASE_DIR%\Mogwai.exe" (
    REM ---- Deploy ALL .slang shaders (source tree is authoritative) ----
    set "FALCOR_SRC=%ROOT%\Falcor\Source\Falcor"
    set "FALCOR_DST=%RELEASE_DIR%\shaders"
    if exist "!FALCOR_SRC!" (
        xcopy "!FALCOR_SRC!\*.slang" "!FALCOR_DST!\" /s /Y /q >nul 2>&1
        echo [update]   Falcor built-in shaders deployed
    )

    REM Custom render pass shaders
    for %%P in (VisCache ReSTIRPTPass) do (
        set "SRC=%ROOT%\Source\RenderPasses\%%P"
        set "DST=%RELEASE_DIR%\shaders\RenderPasses\%%P"
        if exist "!SRC!" (
            if not exist "!DST!" mkdir "!DST!"
            xcopy "!SRC!\*.slang" "!DST!\" /Y /q >nul 2>&1
            echo [update]   %%P shaders deployed
        )
    )

    REM ---- Deploy scripts ----
    set "SCRIPTS_SRC=%ROOT%\scripts"
    set "SCRIPTS_DST=%RELEASE_DIR%\scripts\VisCache"
    if exist "%SCRIPTS_SRC%\smoke_test.py" (
        if not exist "!SCRIPTS_DST!" mkdir "!SCRIPTS_DST!"
        xcopy "%SCRIPTS_SRC%\*" "!SCRIPTS_DST!\" /s /Y /q >nul 2>&1
        echo [update]   scripts deployed
    )

    REM ---- Deploy ReSTIRPTPass data files ----
    set "DATA_SRC=%ROOT%\Source\RenderPasses\ReSTIRPTPass\Data"
    set "DATA_DST=%RELEASE_DIR%\data\ReSTIRPTPass"
    if exist "!DATA_SRC!\16RooksPattern256.txt" (
        if not exist "!DATA_DST!" mkdir "!DATA_DST!"
        xcopy "!DATA_SRC!\*" "!DATA_DST!\" /s /Y /q >nul 2>&1
        echo [update]   ReSTIRPTPass data deployed
    )

    REM ---- Validate NRD ----
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
        echo [update]   WARNING: NRD denoiser not in release.
    ) else (
        echo [update]   NRD denoiser: available
    )

    REM ---- Validate shaders ----
    where python >nul 2>&1
    if errorlevel 1 (
        echo [update] python not found — skipping shader validation
    ) else (
        python "%ROOT%\scripts\validate_shaders.py" --root-dir "%ROOT%" --release-dir "%RELEASE_DIR%"
        if errorlevel 1 echo [update] WARNING: Shader validation found issues
    )
) else (
    echo [update] no release found — skipping deploy
)

REM ---------------------------------------------------------------------------
REM Done
REM ---------------------------------------------------------------------------
echo.
echo [update] Done. Run quickstart.bat to also run tests and launch.

endlocal
