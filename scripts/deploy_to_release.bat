@echo off
REM deploy_to_release.bat — Deploy shaders, scripts, and data from source tree to release/.
REM
REM Called by: quickstart.bat (step 3), run_release.bat (before launch).
REM Idempotent: safe to re-run.
REM
REM Expects caller to set: ROOT, RELEASE_DIR

setlocal enabledelayedexpansion

if not defined ROOT (
    echo [deploy] ERROR: ROOT not set
    exit /b 1
)
if not defined RELEASE_DIR (
    echo [deploy] ERROR: RELEASE_DIR not set
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Deploy scripts from source tree into release/scripts/VisCache/
REM ---------------------------------------------------------------------------
set "SCRIPTS_SRC=%ROOT%\scripts"
set "SCRIPTS_DST=%RELEASE_DIR%\scripts\VisCache"
if exist "%SCRIPTS_SRC%\smoke_test.py" (
    if not exist "%SCRIPTS_DST%" mkdir "%SCRIPTS_DST%"
    set "_COUNT=0"
    for /f "delims=" %%F in ('xcopy "%SCRIPTS_SRC%\*" "%SCRIPTS_DST%\" /s /D /Y /F 2^>nul') do (
        echo [deploy]   updated: %%F
        set /a "_COUNT+=1"
    )
    if !_COUNT! gtr 0 echo [deploy] !_COUNT! script^(s^) updated in release\scripts\VisCache\
)

REM ---------------------------------------------------------------------------
REM Deploy data files (e.g. 16RooksPattern256.txt) into release/data/
REM ---------------------------------------------------------------------------
set "DATA_SRC=%ROOT%\Source\RenderPasses\ReSTIRPTPass\Data"
set "DATA_DST=%RELEASE_DIR%\data\ReSTIRPTPass"
if not exist "%DATA_DST%\16RooksPattern256.txt" (
    if exist "%DATA_SRC%\16RooksPattern256.txt" (
        if not exist "%DATA_DST%" mkdir "%DATA_DST%"
        xcopy "%DATA_SRC%\*" "%DATA_DST%\" /s /y /q >nul
        echo [deploy] Deployed ReSTIRPTPass data files to release\data\
    ) else (
        echo [deploy] WARNING: %DATA_SRC%\16RooksPattern256.txt not found in source tree
    )
)
if not exist "%DATA_DST%\16RooksPattern256.txt" (
    echo [deploy] WARNING: 16RooksPattern256.txt missing -- ReSTIRPTPass will fail to load
    echo [deploy] Expected at: %DATA_DST%\16RooksPattern256.txt
)

REM ---------------------------------------------------------------------------
REM Deploy shaders from source tree (source is always authoritative)
REM ---------------------------------------------------------------------------
REM Force-copy all .slang from source -> release/shaders/ so deployed shaders
REM always match the current checkout.  Git timestamps are unreliable.

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
echo [deploy] Shaders deployed from source tree

REM ---------------------------------------------------------------------------
REM Validate NRD (denoiser) availability
REM ---------------------------------------------------------------------------
set "NRD_OK=1"
if not exist "%RELEASE_DIR%\plugins\NRDPass.dll" (
    echo [deploy]   NRDPass.dll: MISSING
    set "NRD_OK=0"
) else (
    echo [deploy]   NRDPass.dll: OK
)
if not exist "%RELEASE_DIR%\NRD.dll" (
    echo [deploy]   NRD.dll: MISSING
    set "NRD_OK=0"
) else (
    echo [deploy]   NRD.dll: OK
)
if "!NRD_OK!"=="0" (
    echo [deploy]   WARNING: NRD denoiser not in release -- output will be raw noisy radiance.
    echo [deploy]   Rebuild with D3D12 + packman NRD package, or download a release that includes NRD.
) else (
    echo [deploy]   NRD denoiser: available
)

REM ---------------------------------------------------------------------------
REM Validate shaders (content hash)
REM ---------------------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    REM Fallback: at least check sentinel file exists
    if not exist "%RELEASE_DIR%\shaders\Scene\Material\TextureSampler.slang" (
        echo [deploy] ERROR: Falcor shaders missing from release\shaders\ after deploy
        echo [deploy] Check that Falcor\Source\Falcor\ contains .slang files.
        exit /b 1
    )
) else (
    python "%ROOT%\scripts\validate_shaders.py" --root-dir "%ROOT%" --release-dir "%RELEASE_DIR%"
    if errorlevel 1 (
        echo [deploy] WARNING: Shader validation found issues -- see above
    )
)

endlocal
