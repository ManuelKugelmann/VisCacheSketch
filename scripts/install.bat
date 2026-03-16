@echo off
REM install.bat — Idempotent VisCacheSketch installer (clone + quickstart).
REM
REM One-liner (paste into cmd or PowerShell):
REM   cmd /c "curl -sL https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/install.bat?%RANDOM% -o %TEMP%\vc-install.bat && %TEMP%\vc-install.bat"
REM
REM What it does:
REM   1. Checks git version (2.43+ recommended)
REM   2. Clones the repo (or pulls if it already exists)
REM   3. Runs scripts\quickstart.bat (scenes, release, tests, launch)
REM
REM Safe to re-run: skips clone if the directory exists, pulls latest instead.
REM
REM Options:
REM   install.bat [--dir <name>] [--branch <branch>] [--scene <scene>] [--skip-scenes]

setlocal enabledelayedexpansion

set "DIR=VisCacheSketch"
set "BRANCH=main"
set "SCENE="
set "SKIP_SCENES="
set "REPO_URL=https://github.com/ManuelKugelmann/VisCacheSketch.git"

REM ---------------------------------------------------------------------------
REM Parse arguments
REM ---------------------------------------------------------------------------
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--dir" (set "DIR=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--branch" (set "BRANCH=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--scene" (set "SCENE=%~2" & shift & shift & goto :parse_args)
if /i "%~1"=="--skip-scenes" (set "SKIP_SCENES=--skip-scenes" & shift & goto :parse_args)
if /i "%~1"=="--skip-launch" (set "SKIP_LAUNCH=--skip-launch" & shift & goto :parse_args)
echo Unknown argument: %~1
echo Usage: %~nx0 [--dir ^<name^>] [--branch ^<branch^>] [--scene ^<scene^>] [--skip-scenes] [--skip-launch]
exit /b 1
:args_done

REM ---------------------------------------------------------------------------
REM Check git
REM ---------------------------------------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
    echo [install] ERROR: git not found. Install git 2.43+ from https://git-scm.com
    exit /b 1
)

for /f "tokens=3 delims= " %%V in ('git --version') do set "GIT_VER=%%V"
echo [install] git %GIT_VER%
call "%~dp0version.bat" install 2>nul

REM Parse major.minor for version check
for /f "tokens=1,2 delims=." %%A in ("%GIT_VER%") do (
    set "GIT_MAJOR=%%A"
    set "GIT_MINOR=%%B"
)
if !GIT_MAJOR! LSS 2 (
    echo [install] WARNING: git !GIT_VER! is old. git 2.43+ recommended.
) else if !GIT_MAJOR! EQU 2 if !GIT_MINOR! LSS 43 (
    echo [install] WARNING: git !GIT_VER! detected. git 2.43+ recommended ^(sparse-checkout, filter^).
)

REM ---------------------------------------------------------------------------
REM Clone or pull
REM ---------------------------------------------------------------------------
if exist "%DIR%\.git" (
    echo [install] %DIR% already exists -- pulling latest...
    pushd "%DIR%"
    git fetch origin %BRANCH%
    git checkout %BRANCH% 2>nul
    git pull origin %BRANCH%
    if errorlevel 1 (
        echo [install] WARNING: pull failed, continuing with existing checkout
    )
    popd
) else if exist "%DIR%" (
    echo [install] ERROR: %DIR% exists but is not a git repo.
    echo [install] Remove it or use --dir ^<other-name^>.
    exit /b 1
) else (
    echo [install] Cloning %REPO_URL%...
    git clone --branch %BRANCH% %REPO_URL% "%DIR%"
    if errorlevel 1 (
        echo [install] ERROR: git clone failed.
        exit /b 1
    )
)

REM ---------------------------------------------------------------------------
REM Run quickstart
REM ---------------------------------------------------------------------------
set "QS_ARGS="
if defined SCENE set "QS_ARGS=--scene %SCENE%"
if defined SKIP_SCENES set "QS_ARGS=%QS_ARGS% %SKIP_SCENES%"
if defined SKIP_LAUNCH set "QS_ARGS=%QS_ARGS% %SKIP_LAUNCH%"

REM Resolve absolute path so quickstart.bat's %~dp0 points to scripts\
for %%P in ("%DIR%\scripts\quickstart.bat") do set "QS_SCRIPT=%%~fP"
REM --skip-pull: install.bat already cloned/pulled above
echo [install] Running %QS_SCRIPT% --skip-pull %QS_ARGS%
call "%QS_SCRIPT%" --skip-pull %QS_ARGS%

exit /b %ERRORLEVEL%
