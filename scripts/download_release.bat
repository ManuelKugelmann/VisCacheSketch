@echo off
REM download_release.bat — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
REM
REM Usage:  scripts\download_release.bat
REM
REM Downloads the dev-latest prerelease archive and extracts to release\.
REM Re-downloads if a newer release is available (uses ETag to check).
REM
REM Requires: curl, tar (both ship with Windows 10+)

setlocal enabledelayedexpansion

set "REPO=ManuelKugelmann/VisCacheSketch"
set "ROOT=%~dp0.."
set "RELEASE_DIR=%ROOT%\release"
set "DOWNLOAD_URL=https://github.com/%REPO%/releases/download/dev-latest/viscache-windows-Release.tar.gz"
set "ETAG_FILE=%RELEASE_DIR%\.release-etag"
set "ARCHIVE=%TEMP%\viscache-latest.tar.gz"

where curl >nul 2>&1 || (echo [release] ERROR: curl not found in PATH & exit /b 1)
where tar >nul 2>&1 || (echo [release] ERROR: tar not found in PATH & exit /b 1)

mkdir "%RELEASE_DIR%" 2>nul

REM ---------------------------------------------------------------------------
REM Check for newer release via ETag
REM ---------------------------------------------------------------------------
if exist "%RELEASE_DIR%\Mogwai.exe" if exist "%ETAG_FILE%" (
    set /p OLD_ETAG=<"%ETAG_FILE%"
    echo [release] Checking for newer release...
    for /f "delims=" %%E in ('curl -fsSL -H "Cache-Control: no-cache" -I "%DOWNLOAD_URL%" 2^>nul ^| findstr /i "^etag:"') do set "ETAG_LINE=%%E"
    if defined ETAG_LINE (
        REM Compare stored ETag with remote
        echo !ETAG_LINE! | findstr /c:"!OLD_ETAG!" >nul 2>&1
        if not errorlevel 1 (
            echo [release] Mogwai.exe is up to date.
            exit /b 0
        )
        echo [release] Newer release available, updating...
    ) else (
        echo [release] Could not check remote -- keeping existing release.
        exit /b 0
    )
) else if exist "%RELEASE_DIR%\Mogwai.exe" (
    REM Mogwai exists but no ETag saved -- re-download to establish baseline
    echo [release] Mogwai.exe exists but no version info. Re-downloading...
)

REM ---------------------------------------------------------------------------
REM Download
REM ---------------------------------------------------------------------------
echo [release] Downloading: %DOWNLOAD_URL%
curl -fSL --progress-bar -H "Cache-Control: no-cache" -D "%TEMP%\vc-release-headers.txt" -o "%ARCHIVE%" "%DOWNLOAD_URL%"
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

REM Save ETag for future update checks
for /f "tokens=2 delims= " %%E in ('findstr /i "^etag:" "%TEMP%\vc-release-headers.txt" 2^>nul') do (
    echo %%E> "%ETAG_FILE%"
)
del "%TEMP%\vc-release-headers.txt" 2>nul

REM ---------------------------------------------------------------------------
REM Clean old release — move aside so tar doesn't hit "Refusing to overwrite"
REM ---------------------------------------------------------------------------
set "OLD_RELEASE=%TEMP%\viscache-old-release-%RANDOM%"
if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [release] Moving old release aside...
    move /y "%RELEASE_DIR%" "%OLD_RELEASE%" >nul 2>&1
    mkdir "%RELEASE_DIR%" 2>nul
    REM Preserve ETag file
    if exist "%OLD_RELEASE%\.release-etag" copy /y "%OLD_RELEASE%\.release-etag" "%ETAG_FILE%" >nul 2>&1
)

echo [release] Extracting to %RELEASE_DIR%...
tar xzf "%ARCHIVE%" -C "%RELEASE_DIR%"
if errorlevel 1 (
    echo [release] ERROR: Extraction failed.
    if exist "%OLD_RELEASE%\Mogwai.exe" (
        echo [release] Restoring previous release...
        rd /s /q "%RELEASE_DIR%" 2>nul
        move /y "%OLD_RELEASE%" "%RELEASE_DIR%" >nul 2>&1
    )
    del "%ARCHIVE%" 2>nul
    exit /b 1
)
del "%ARCHIVE%" 2>nul

REM Remove old release now that extraction succeeded
if exist "%OLD_RELEASE%" rd /s /q "%OLD_RELEASE%" 2>nul

if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [release] OK: Mogwai.exe ready
) else (
    echo [release] WARNING: Mogwai.exe not found after extraction.
    echo [release] Archive contents:
    dir /b "%RELEASE_DIR%"
)

endlocal
