@echo off
setlocal enabledelayedexpansion
REM mogwai_run.bat — Run Mogwai from release/ with env vars forwarded.
REM Wrapper to avoid cd prompts. All scripts should call this instead of
REM cd release && Mogwai.exe directly.
REM
REM Usage: scripts\mogwai_run.bat [Mogwai args...]
REM   e.g. scripts\mogwai_run.bat --headless -s scripts/VisCache/smoke_test.py
REM
REM Env vars GRAPH_SCRIPT, NUM_FRAMES, SCENE_FILE, GALLERY_DIR, WARMUP_FRAMES,
REM CAPTURE_NAME are forwarded to the Python script.

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "RELEASE=%ROOT%\release"
set "MOGWAI=%RELEASE%\Mogwai.exe"

if not exist "%MOGWAI%" (
    echo [mogwai_run] ERROR: Mogwai.exe not found at %MOGWAI%
    echo [mogwai_run] Run quickstart.bat or download_release.bat first.
    exit /b 1
)

pushd "%RELEASE%"
"%MOGWAI%" %*
set "EC=!errorlevel!"
popd
exit /b %EC%
