@echo off
REM VisCacheSketch quickstart — download latest release, fetch scenes, run.
REM
REM Usage:  scripts\quickstart.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]
REM
REM Steps:
REM   1. Download latest GitHub release (Mogwai + plugins)
REM   2. Download test scenes (Arcade, Bistro, Sponza)
REM   3. Run smoke test
REM   4. Launch Mogwai with selected scene
REM
REM Requires: curl, tar, python3 (for tests), git 2.43+ (for VeachAjar sparse clone)
REM Optional: PowerShell 5+ (used for JSON parsing via built-in cmdlets)
REM
REM Idempotent: safe to re-run. Skips steps that are already complete.
REM
REM One-liner (cmd or PowerShell, idempotent):
REM   curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/bootstrap.bat -o %TEMP%\vc-bootstrap.bat && %TEMP%\vc-bootstrap.bat
REM
REM WSL alternative (runs .sh scripts directly):
REM     wsl bash scripts/download_scenes.sh
REM     wsl bash scripts/run_paper_experiments.sh

setlocal enabledelayedexpansion

set "REPO=ManuelKugelmann/VisCacheSketch"
set "ROOT=%~dp0.."
set "RELEASE_DIR=%ROOT%\release"
set "MEDIA_DIR=%ROOT%\media"
set "SCENE=Bistro"
set "SKIP_SCENES=0"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-scenes" (set "SKIP_SCENES=1" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--scene Bistro^|Sponza^|Arcade] [--skip-scenes]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM 1. Download latest release
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 1: Download latest release
echo ========================================

if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [release] Mogwai.exe already exists in %RELEASE_DIR%
    echo [release] Delete %RELEASE_DIR% to re-download.
    goto :step2
)

where curl >nul 2>&1 || (echo ERROR: curl not found in PATH & exit /b 1)
where tar >nul 2>&1 || (echo ERROR: tar not found in PATH & exit /b 1)

echo [release] Querying latest release from %REPO%...

REM Use curl to fetch release JSON, then PowerShell to parse it.
REM Two-step approach avoids all cmd/PowerShell pipe escaping issues.
set "API_JSON=%TEMP%\vc-release-%RANDOM%.json"
curl -fsSL -o "!API_JSON!" "https://api.github.com/repos/%REPO%/releases/latest"
if errorlevel 1 (
    echo [release] No release found (API returned 404). Skipping download.
    echo [release] This is normal for first-time setup or pre-release branches.
    del "!API_JSON!" 2>nul
    goto :step2
)
REM Parse JSON with PowerShell — use -Command with semicolons, no pipes needed.
REM .Where() method avoids the | pipe character entirely (requires PS 4+).
for /f "usebackq delims=" %%U in (`powershell -NoProfile -Command "$r = Get-Content -Raw '!API_JSON!'; $j = ConvertFrom-Json $r; $m = $j.assets.Where({$_.name -match 'viscache-windows.*Release.*\.tar\.gz'}); if ($m.Count) { $m[0].browser_download_url } else { 'NONE' }"`) do set "DOWNLOAD_URL=%%U"
del "!API_JSON!" 2>nul

if "%DOWNLOAD_URL%"=="NONE" (
    echo [release] No Windows Release asset found in latest release. Skipping.
    goto :step2
)
if "%DOWNLOAD_URL%"=="" (
    echo [release] Could not parse release info. Skipping download.
    goto :step2
)

echo [release] Downloading: %DOWNLOAD_URL%
mkdir "%RELEASE_DIR%" 2>nul

set "ARCHIVE=%TEMP%\viscache-latest.tar.gz"
curl -fSL --progress-bar -o "%ARCHIVE%" "%DOWNLOAD_URL%"
if errorlevel 1 (
    echo [release] ERROR: Download failed. Retrying...
    timeout /t 2 /nobreak >nul
    curl -fSL --progress-bar -o "%ARCHIVE%" "%DOWNLOAD_URL%"
    if errorlevel 1 (echo [release] ERROR: Download failed after retry. & exit /b 1)
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

REM ---------------------------------------------------------------------------
REM 2. Download scenes
REM ---------------------------------------------------------------------------
:step2
if %SKIP_SCENES%==1 (
    echo.
    echo [scenes] Skipping scene download (--skip-scenes)
    goto :step3
)

echo.
echo ========================================
echo  Step 2: Download test scenes
echo ========================================

call "%~dp0download_scenes.bat" --dir "%MEDIA_DIR%" --yes
if errorlevel 1 echo [scenes] WARNING: Some scenes failed to download

REM ---------------------------------------------------------------------------
REM 3. Run CPU tests + smoke test
REM ---------------------------------------------------------------------------
:step3
echo.
echo ========================================
echo  Step 3: Validate
echo ========================================

where python >nul 2>&1 && (
    echo [test] Running algorithm tests...
    python "%ROOT%\tests\test_viscache_convergence.py"
    if errorlevel 1 echo [test] WARNING: convergence tests failed
    python "%ROOT%\tests\test_restir_variants.py"
    if errorlevel 1 echo [test] WARNING: ReSTIR variant tests failed
    python "%ROOT%\tests\test_paper_ablations.py"
    if errorlevel 1 echo [test] WARNING: ablation config tests failed
) || (
    echo [test] python not found — skipping algorithm tests
)

if exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [smoke] Running smoke test...
    "%RELEASE_DIR%\Mogwai.exe" --headless --script "%RELEASE_DIR%\scripts\VisCache\smoke_test.py"
    if errorlevel 1 (
        echo [smoke] WARNING: Smoke test failed
    ) else (
        echo [smoke] OK
    )
) else (
    echo [smoke] Mogwai.exe not found — skipping smoke test
)

REM ---------------------------------------------------------------------------
REM 4. Resolve scene path and launch
REM ---------------------------------------------------------------------------
echo.
echo ========================================
echo  Step 4: Launch
echo ========================================

set "SCENE_FILE="
if /i "%SCENE%"=="Bistro" set "SCENE_FILE=%MEDIA_DIR%\Bistro\Bistro_Interior.pyscene"
if /i "%SCENE%"=="Sponza" set "SCENE_FILE=%MEDIA_DIR%\Sponza\Sponza.pyscene"
if /i "%SCENE%"=="Arcade" set "SCENE_FILE=%MEDIA_DIR%\Arcade\Arcade.pyscene"

if not exist "%RELEASE_DIR%\Mogwai.exe" (
    echo [launch] Mogwai.exe not found — no release downloaded.
    echo [launch] Build from source or grab a release: https://github.com/%REPO%/releases
    echo [launch] Tests and setup completed successfully.
    exit /b 0
)

if "%SCENE_FILE%"=="" (
    echo [launch] Unknown scene: %SCENE%
    echo [launch] Available: Bistro, Sponza, Arcade
    exit /b 1
)

if not exist "%SCENE_FILE%" (
    echo [launch] Scene file not found: %SCENE_FILE%
    echo [launch] Re-run without --skip-scenes to download.
    exit /b 1
)

echo [launch] Starting Mogwai with %SCENE%...
echo [launch] %RELEASE_DIR%\Mogwai.exe --script scripts\VisCache\VisCache_Graph.py --scene %SCENE_FILE%
echo.
set "FALCOR_MEDIA_FOLDERS=%MEDIA_DIR%"
"%RELEASE_DIR%\Mogwai.exe" --script "%RELEASE_DIR%\scripts\VisCache\VisCache_Graph.py" --scene "%SCENE_FILE%"

endlocal
