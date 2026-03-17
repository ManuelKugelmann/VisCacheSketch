: setup-build-system.bat — VisCache Falcor 8.0 integration setup script (Windows)
: Run from the VisCache package root: .\setup-build-system.bat
:
: What this script does:
:   1. Verifies Falcor root, enables git hooks
:   2. Copies VisCache source files into the Falcor tree
:   3. Patches CMakeLists.txt to register the plugins
:   4. Calls Falcor\setup_vs2022.bat (submodule init, packman deps, VS2022 solution)
:   5. Runs the Python unit tests

@echo off
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set FALCOR_ROOT=%SCRIPT_DIR%Falcor

: Publish the project root so Falcor\setup.bat can find it without relying
: on fragile relative-path navigation.  Falcor is a subtree, not a standalone
: repo, so its setup script cannot know the git root on its own.
: Strip trailing backslash so "git -C "%VISCACHE_ROOT%"" does not see \"
set VISCACHE_ROOT=%SCRIPT_DIR%
if "%VISCACHE_ROOT:~-1%"=="\" set VISCACHE_ROOT=%VISCACHE_ROOT:~0,-1%

: ---------------------------------------------------------------------------
: Step 1: Verify Falcor root
: ---------------------------------------------------------------------------
echo [VisCache] Step 1: SCRIPT_DIR=%SCRIPT_DIR%
echo [VisCache] Step 1: FALCOR_ROOT=%FALCOR_ROOT%
echo [VisCache] Step 1: VISCACHE_ROOT=%VISCACHE_ROOT%

: ---------------------------------------------------------------------------
: Step 1b: Enable git hooks
: ---------------------------------------------------------------------------
if exist "%SCRIPT_DIR%.githooks\" (
    echo [VisCache] Step 1b: Enabling git hooks...
    git -C "%SCRIPT_DIR%." config core.hooksPath .githooks
)

if not exist "%FALCOR_ROOT%\CMakeLists.txt" (
    echo [VisCache] ERROR: CMakeLists.txt not found in %FALCOR_ROOT%
    exit /b 1
)

: ---------------------------------------------------------------------------
: Steps 2-3: Integrate plugins (copy sources + data + tests, patch CMake)
: ---------------------------------------------------------------------------
: NOTE: Sources must be copied BEFORE Falcor setup because setup_vs2022.bat
: runs cmake --preset which configures the project. If CMakeLists.txt already
: has add_subdirectory(ReSTIRPTPass) from a prior run, cmake will fail unless
: the source directories exist.
echo [VisCache] Steps 2-3: Integrating plugins into Falcor tree...

: Restore CMakeLists.txt from git to discard any corruption from prior runs
: (e.g. truncated lines from unescaped batch parentheses).
git -C "%FALCOR_ROOT%" checkout -- Source\RenderPasses\CMakeLists.txt >nul 2>&1

: Delegate to the shared integrate-plugins script (same script used by CI).
call "%SCRIPT_DIR%scripts\integrate-plugins.bat" "%FALCOR_ROOT%"
if errorlevel 1 (
    echo [VisCache] ERROR: integrate-plugins.bat failed!
    exit /b 1
)

: ---------------------------------------------------------------------------
: Step 4: Run Falcor's own setup (submodules, packman deps, VS2022 solution)
: ---------------------------------------------------------------------------
echo [VisCache] Step 4: Running Falcor setup (submodules + packman + VS2022)...

if not exist "%FALCOR_ROOT%\setup_vs2022.bat" (
    echo [VisCache]   WARNING: setup_vs2022.bat not found, skipping Falcor setup.
    echo [VisCache]   You may need to init submodules and fetch packman deps manually.
    goto :skip_falcor_setup
)
REM setup_vs2022.bat runs cmake --preset which needs CWD inside Falcor
pushd "%FALCOR_ROOT%"
call "%FALCOR_ROOT%\setup_vs2022.bat" --host x64
set SETUP_ERR=!errorlevel!
popd
if !SETUP_ERR! neq 0 (
    echo [VisCache] ERROR: Falcor setup failed!
    exit /b 1
)
echo [VisCache]   Falcor setup complete.
:skip_falcor_setup

: ---------------------------------------------------------------------------
: Step 5: Run Python unit tests
: ---------------------------------------------------------------------------
echo [VisCache] Step 5: Running CPU unit tests...
python "%SCRIPT_DIR%tests\test_viscache_convergence.py"
if errorlevel 1 (
    echo [VisCache] ERROR: Unit tests failed!
    exit /b 1
)
echo [VisCache]   All unit tests passed.

: ---------------------------------------------------------------------------
: Done
: ---------------------------------------------------------------------------
echo.
echo [VisCache] Setup complete.
echo.
echo Next steps:
echo   1. Open %FALCOR_ROOT%\build\windows-vs2022\Falcor.sln in Visual Studio
echo   2. Build target: Mogwai (Release, x64)
echo   3. Run: Mogwai.exe --script scripts/VisCache/VisCache_Graph.py --scene BistroInterior.pyscene
echo.

exit /b 0
