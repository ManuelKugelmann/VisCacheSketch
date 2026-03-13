@echo off
REM download_release.bat — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
REM
REM Usage:  scripts\download_release.bat
REM
REM Downloads the dev-latest prerelease archive and extracts to release\.
REM Idempotent: skips if Mogwai.exe already exists. Delete release\ to re-download.
REM
REM Requires: curl, tar (both ship with Windows 10+)

setlocal enabledelayedexpansion

set "REPO=ManuelKugelmann/VisCacheSketch"
set "ROOT=%~dp0.."
set "RELEASE_DIR=%ROOT%\release"

if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [release] Mogwai.exe already exists in %RELEASE_DIR%
    echo [release] Delete %RELEASE_DIR% to re-download.
    exit /b 0
)

where curl >nul 2>&1 || (echo [release] ERROR: curl not found in PATH & exit /b 1)
where tar >nul 2>&1 || (echo [release] ERROR: tar not found in PATH & exit /b 1)

REM Direct download from the dev-latest prerelease (fixed archive name).
REM No API query or JSON parsing needed — just a single curl redirect.
set "DOWNLOAD_URL=https://github.com/%REPO%/releases/download/dev-latest/viscache-windows-Release.tar.gz"
echo [release] Downloading: %DOWNLOAD_URL%
mkdir "%RELEASE_DIR%" 2>nul

set "ARCHIVE=%TEMP%\viscache-latest.tar.gz"
curl -fSL --progress-bar -o "%ARCHIVE%" "%DOWNLOAD_URL%"
if errorlevel 1 (
    echo [release] Download failed -- no dev-latest release yet. Skipping.
    echo [release] This is normal for first-time setup or pre-release branches.
    echo [release]
    echo [release] To get Mogwai manually:
    echo [release]   Download: https://github.com/%REPO%/releases
    echo [release]   Build:    run setup.bat, then cmake --preset windows-vs2022-ci
    del "%ARCHIVE%" 2>nul
    exit /b 0
)

echo [release] Extracting to %RELEASE_DIR%...
tar xzf "%ARCHIVE%" -C "%RELEASE_DIR%"
del "%ARCHIVE%" 2>nul

if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [release] OK: Mogwai.exe ready
) else (
    echo [release] WARNING: Mogwai.exe not found after extraction.
    echo [release] Archive contents:
    dir /b "%RELEASE_DIR%"
)

endlocal
