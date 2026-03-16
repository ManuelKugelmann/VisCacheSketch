@echo off
REM download_release.bat — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
REM
REM Usage:  scripts\download_release.bat
REM
REM Finds the newest dev-* versioned prerelease via the GitHub API,
REM downloads its archive, and extracts to release\.
REM Re-downloads if a newer release is available (compares commit SHA).
REM
REM Requires: curl, tar (both ship with Windows 10+)

setlocal enabledelayedexpansion

set "REPO=ManuelKugelmann/VisCacheSketch"
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "RELEASE_DIR=%ROOT%\release"
set "SHA_FILE=%RELEASE_DIR%\.release-sha"
set "VERSION_FILE=%RELEASE_DIR%\.release-version"
set "ARCHIVE=%TEMP%\viscache-latest.tar.gz"

where curl >nul 2>&1
if errorlevel 1 (
    echo [release] ERROR: curl not found in PATH
    exit /b 1
)
where tar >nul 2>&1
if errorlevel 1 (
    echo [release] ERROR: tar not found in PATH
    exit /b 1
)

mkdir "%RELEASE_DIR%" 2>nul

REM ---------------------------------------------------------------------------
REM Step 1: Find the latest dev-* prerelease tag via GitHub API
REM ---------------------------------------------------------------------------
set "REMOTE_TAG="
set "API_LIST=%TEMP%\vc-release-list.json"
curl -fsSL -H "Cache-Control: no-cache" -H "Pragma: no-cache" "https://api.github.com/repos/%REPO%/releases?per_page=10" -o "%API_LIST%" 2>nul
if errorlevel 1 (
    echo [release] WARNING: Could not query GitHub releases API.
    del "%API_LIST%" 2>nul
    goto :try_existing
)

REM Find first tag_name matching dev-2* (versioned tags sort newest first)
for /f "tokens=2 delims=:, " %%A in ('findstr /i "\"tag_name\"" "%API_LIST%" 2^>nul') do (
    set "_TAG=%%~A"
    if not defined REMOTE_TAG (
        if "!_TAG:~0,5!"=="dev-2" set "REMOTE_TAG=!_TAG!"
    )
)
del "%API_LIST%" 2>nul

if not defined REMOTE_TAG (
    echo [release] No dev-* prerelease found on GitHub.
    goto :try_existing
)

echo [release] Latest prerelease tag: !REMOTE_TAG!

REM ---------------------------------------------------------------------------
REM Step 2: Fetch details for that specific release
REM ---------------------------------------------------------------------------
set "REMOTE_DATE="
set "REMOTE_SHA="
set "API_JSON=%TEMP%\vc-release-api.json"
curl -fsSL -H "Cache-Control: no-cache" -H "Pragma: no-cache" "https://api.github.com/repos/%REPO%/releases/tags/!REMOTE_TAG!" -o "%API_JSON%" 2>nul
if not errorlevel 1 (
    REM Extract date+time (YYYY-MM-DD HH:MM:SS) from published_at
    REM JSON field: "published_at": "2026-03-16T14:48:02Z"
    REM With delims=:, <space> tokens split as:
    REM   1="published_at"  2="2026-03-16T14"  3=48  4=02Z"
    for /f "tokens=2,3,4 delims=:, " %%A in ('findstr /i "\"published_at\"" "%API_JSON%" 2^>nul') do if not defined REMOTE_DATE (
        set "_DATE_HOUR=%%~A"
        set "_MIN=%%B"
        set "_SECZ=%%C"
        for /f "tokens=1,2 delims=T" %%D in ("!_DATE_HOUR!") do (
            set "REMOTE_DATE=%%D"
            set "_HOUR=%%E"
        )
        for /f "tokens=1 delims=Z^" " %%S in ("!_SECZ!") do set "_SEC=%%S"
        if defined _HOUR if defined _MIN if defined _SEC (
            set "REMOTE_DATE=!REMOTE_DATE! !_HOUR!:!_MIN!:!_SEC!"
        )
    )
    for /f "tokens=2 delims=:, " %%A in ('findstr /i "\"target_commitish\"" "%API_JSON%" 2^>nul') do if not defined REMOTE_SHA set "REMOTE_SHA=%%~A"
)
del "%API_JSON%" 2>nul

REM ---------------------------------------------------------------------------
REM Check for newer release via commit SHA
REM ---------------------------------------------------------------------------
if exist "%RELEASE_DIR%\Mogwai.exe" if exist "%SHA_FILE%" (
    set /p OLD_SHA=<"%SHA_FILE%"
    set "INSTALLED_VER=unknown"
    if exist "%VERSION_FILE%" set /p INSTALLED_VER=<"%VERSION_FILE%"
    echo [release] Checking for newer release...
    set "OLD_SHA_SHORT=!OLD_SHA:~0,7!"
    echo [release]   Installed: !INSTALLED_VER! [!OLD_SHA_SHORT!]
    if defined REMOTE_SHA (
        set "REMOTE_SHA_SHORT=!REMOTE_SHA:~0,7!"
        echo [release]   Remote:    !REMOTE_TAG! ^(!REMOTE_DATE!^) [!REMOTE_SHA_SHORT!]
    ) else (
        echo [release]   Remote:    !REMOTE_TAG! ^(!REMOTE_DATE!^)
    )
    if defined REMOTE_SHA (
        if "!OLD_SHA!"=="!REMOTE_SHA!" (
            echo [release] Mogwai.exe is up to date.
            exit /b 0
        )
        echo [release] Newer release available, updating...
    ) else (
        echo [release] Could not verify remote SHA -- keeping existing release.
        exit /b 0
    )
) else if exist "%RELEASE_DIR%\Mogwai.exe" (
    REM Mogwai exists but no SHA saved -- re-download to establish baseline
    echo [release] Mogwai.exe exists but no version info. Re-downloading...
)

REM ---------------------------------------------------------------------------
REM Download from the versioned tag
REM ---------------------------------------------------------------------------
set "DOWNLOAD_URL=https://github.com/%REPO%/releases/download/!REMOTE_TAG!/viscache-windows-Release.tar.gz"
echo [release] Downloading: !DOWNLOAD_URL!
curl -fSL --progress-bar -H "Cache-Control: no-cache" -o "%ARCHIVE%" "!DOWNLOAD_URL!"
if errorlevel 1 (
    echo [release] Download failed. Skipping.
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
echo !REMOTE_TAG! ^(!REMOTE_DATE!^)> "%VERSION_FILE%"

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
exit /b 0

:try_existing
if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [release] Could not check remote -- keeping existing release.
    exit /b 0
) else (
    echo [release] No existing release and could not query remote.
    echo [release] To get Mogwai manually:
    echo [release]   Download: https://github.com/%REPO%/releases
    echo [release]   Build:    run setup-build-system.bat, then cmake --preset windows-vs2022-ci
    exit /b 0
)
