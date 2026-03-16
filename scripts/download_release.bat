@echo off
REM download_release.bat — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
REM
REM Usage:  scripts\download_release.bat
REM
REM Downloads the dev-latest prerelease archive and extracts to release\.
REM Re-downloads if a newer release is available (compares commit SHA via API).
REM
REM Requires: curl, tar (both ship with Windows 10+)

setlocal enabledelayedexpansion

set "REPO=ManuelKugelmann/VisCacheSketch"
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "RELEASE_DIR=%ROOT%\release"
set "DOWNLOAD_URL=https://github.com/%REPO%/releases/download/dev-latest/viscache-windows-Release.tar.gz"
set "SHA_FILE=%RELEASE_DIR%\.release-sha"
set "VERSION_FILE=%RELEASE_DIR%\.release-version"
set "ARCHIVE=%TEMP%\viscache-latest.tar.gz"
set "API_URL=https://api.github.com/repos/%REPO%/releases/tags/dev-latest"

where curl >nul 2>&1 || (echo [release] ERROR: curl not found in PATH & exit /b 1)
where tar >nul 2>&1 || (echo [release] ERROR: tar not found in PATH & exit /b 1)

mkdir "%RELEASE_DIR%" 2>nul

REM ---------------------------------------------------------------------------
REM Query remote release info from GitHub API (single call)
REM ---------------------------------------------------------------------------
set "REMOTE_TAG="
set "REMOTE_DATE="
set "REMOTE_SHA="
set "API_JSON=%TEMP%\vc-release-api.json"
curl -fsSL "%API_URL%" -o "%API_JSON%" 2>nul
if not errorlevel 1 (
    for /f "tokens=2 delims=:, " %%A in ('findstr /i "\"tag_name\"" "%API_JSON%" 2^>nul') do if not defined REMOTE_TAG set "REMOTE_TAG=%%~A"
    REM Extract just the date (YYYY-MM-DD) from published_at to avoid colon issues
    for /f "tokens=2 delims=:, " %%A in ('findstr /i "\"published_at\"" "%API_JSON%" 2^>nul') do if not defined REMOTE_DATE (
        set "_RAW=%%~A"
        for /f "tokens=1 delims=T" %%D in ("!_RAW!") do set "REMOTE_DATE=%%D"
    )
    for /f "tokens=2 delims=:, " %%A in ('findstr /i "\"target_commitish\"" "%API_JSON%" 2^>nul') do if not defined REMOTE_SHA set "REMOTE_SHA=%%~A"
)
del "%API_JSON%" 2>nul

REM ---------------------------------------------------------------------------
REM Check for newer release via commit SHA from GitHub API
REM ---------------------------------------------------------------------------
if exist "%RELEASE_DIR%\Mogwai.exe" if exist "%SHA_FILE%" (
    set /p OLD_SHA=<"%SHA_FILE%"
    set "INSTALLED_VER=unknown"
    if exist "%VERSION_FILE%" set /p INSTALLED_VER=<"%VERSION_FILE%"
    echo [release] Checking for newer release...
    set "OLD_SHA_SHORT=!OLD_SHA:~0,7!"
    echo [release]   Installed: !INSTALLED_VER! [!OLD_SHA_SHORT!]
    if defined REMOTE_TAG (
        if defined REMOTE_SHA (
            set "REMOTE_SHA_SHORT=!REMOTE_SHA:~0,7!"
            echo [release]   Remote:    !REMOTE_TAG! ^(!REMOTE_DATE!^) [!REMOTE_SHA_SHORT!]
        ) else (
            echo [release]   Remote:    !REMOTE_TAG! ^(!REMOTE_DATE!^)
        )
    ) else (
        echo [release]   Remote:    ^(could not query GitHub API^)
    )
    if defined REMOTE_SHA (
        if "!OLD_SHA!"=="!REMOTE_SHA!" (
            echo [release] Mogwai.exe is up to date.
            exit /b 0
        )
        echo [release] Newer release available, updating...
    ) else (
        echo [release] Could not check remote -- keeping existing release.
        exit /b 0
    )
) else if exist "%RELEASE_DIR%\Mogwai.exe" (
    REM Mogwai exists but no SHA saved -- re-download to establish baseline
    echo [release] Mogwai.exe exists but no version info. Re-downloading...
)

REM ---------------------------------------------------------------------------
REM Download
REM ---------------------------------------------------------------------------
echo [release] Downloading: %DOWNLOAD_URL%
curl -fSL --progress-bar -H "Cache-Control: no-cache" -o "%ARCHIVE%" "%DOWNLOAD_URL%"
if errorlevel 1 (
    echo [release] Download failed -- no dev-latest release yet. Skipping.
    echo [release] This is normal for first-time setup or pre-release branches.
    echo [release]
    echo [release] To get Mogwai manually:
    echo [release]   Download: https://github.com/%REPO%/releases
    echo [release]   Build:    run setup-build-system.bat, then cmake --preset windows-vs2022-ci
    del "%ARCHIVE%" 2>nul
    exit /b 0
)

REM Save commit SHA for future update checks
if defined REMOTE_SHA (
    echo !REMOTE_SHA!> "%SHA_FILE%"
)

REM Save release version for display on next update check
if defined REMOTE_TAG (
    echo !REMOTE_TAG! ^(!REMOTE_DATE!^)> "%VERSION_FILE%"
) else (
    echo dev-latest> "%VERSION_FILE%"
)

REM ---------------------------------------------------------------------------
REM Clean old release — move aside so tar doesn't hit "Refusing to overwrite"
REM ---------------------------------------------------------------------------
set "OLD_RELEASE=%TEMP%\viscache-old-release-%RANDOM%"
if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [release] Moving old release aside...
    move /y "%RELEASE_DIR%" "%OLD_RELEASE%" >nul 2>&1
    mkdir "%RELEASE_DIR%" 2>nul
    REM Preserve SHA and version files
    if exist "%OLD_RELEASE%\.release-sha" copy /y "%OLD_RELEASE%\.release-sha" "%SHA_FILE%" >nul 2>&1
    if exist "%OLD_RELEASE%\.release-version" copy /y "%OLD_RELEASE%\.release-version" "%VERSION_FILE%" >nul 2>&1
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
