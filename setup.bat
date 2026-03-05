: setup.bat — MLVHF Falcor 8.0 integration setup script (Windows)
: Run from the MLVHF package root: .\setup.bat
:
: What this script does:
:   1. Calls Falcor\setup_vs2022.bat (submodule init, packman deps, VS2022 solution)
:   2. Copies MLVHF source files into the Falcor tree
:   3. Patches CMakeLists.txt to register the plugins
:   4. Runs the Python unit tests

@echo off
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set FALCOR_ROOT=%SCRIPT_DIR%Falcor

: ---------------------------------------------------------------------------
: Step 1: Verify Falcor root
: ---------------------------------------------------------------------------
echo [MLVHF] Step 1: Using Falcor at: %FALCOR_ROOT%

: ---------------------------------------------------------------------------
: Step 1b: Enable git hooks
: ---------------------------------------------------------------------------
if exist "%SCRIPT_DIR%.githooks\" (
    echo [MLVHF] Step 1b: Enabling git hooks...
    git -C "%SCRIPT_DIR%." config core.hooksPath .githooks
)

if not exist "%FALCOR_ROOT%\CMakeLists.txt" (
    echo [MLVHF] ERROR: CMakeLists.txt not found in %FALCOR_ROOT%
    exit /b 1
)

: ---------------------------------------------------------------------------
: Step 2: Run Falcor's own setup (submodules, packman deps, VS2022 solution)
: ---------------------------------------------------------------------------
echo [MLVHF] Step 2: Running Falcor setup (submodules + packman + VS2022)...

if exist "%FALCOR_ROOT%\setup_vs2022.bat" (
    call "%FALCOR_ROOT%\setup_vs2022.bat"
    if errorlevel 1 (
        echo [MLVHF] ERROR: Falcor setup failed!
        exit /b 1
    )
    echo [MLVHF]   Falcor setup complete.
) else (
    echo [MLVHF]   WARNING: setup_vs2022.bat not found, skipping Falcor setup.
    echo [MLVHF]   You may need to init submodules and fetch packman deps manually.
)

: ---------------------------------------------------------------------------
: Step 3: Copy MLVHF sources into Falcor tree
: ---------------------------------------------------------------------------
echo [MLVHF] Step 3: Copying MLVHF RenderPass sources...

: VisHashFilter
set VHF_DST=%FALCOR_ROOT%\Source\RenderPasses\VisHashFilter
if not exist "%VHF_DST%" mkdir "%VHF_DST%"
xcopy "%SCRIPT_DIR%Source\RenderPasses\VisHashFilter\*" "%VHF_DST%\" /s /y /q
echo [MLVHF]   Copied: VisHashFilter

: ReSTIRGIPass
set GI_DST=%FALCOR_ROOT%\Source\RenderPasses\ReSTIRGIPass
if not exist "%GI_DST%" mkdir "%GI_DST%"
xcopy "%SCRIPT_DIR%Source\RenderPasses\ReSTIRGIPass\*" "%GI_DST%\" /s /y /q
echo [MLVHF]   Copied: ReSTIRGIPass

: Scripts
set SCRIPT_DST=%FALCOR_ROOT%\scripts\MLVHF
if not exist "%SCRIPT_DST%" mkdir "%SCRIPT_DST%"
xcopy "%SCRIPT_DIR%scripts\*" "%SCRIPT_DST%\" /s /y /q
echo [MLVHF]   Copied: scripts

: Tests
set TEST_DST=%FALCOR_ROOT%\scripts\MLVHF\tests
if not exist "%TEST_DST%" mkdir "%TEST_DST%"
xcopy "%SCRIPT_DIR%tests\*" "%TEST_DST%\" /s /y /q
echo [MLVHF]   Copied: tests

: ---------------------------------------------------------------------------
: Step 4: Patch CMakeLists.txt to register plugins
: ---------------------------------------------------------------------------
echo [MLVHF] Step 4: Patching Source\RenderPasses\CMakeLists.txt...

set RP_CMAKE=%FALCOR_ROOT%\Source\RenderPasses\CMakeLists.txt
if not exist "%RP_CMAKE%" (
    echo [MLVHF] ERROR: Could not find %RP_CMAKE%
    exit /b 1
)

findstr /c:"add_subdirectory(VisHashFilter)" "%RP_CMAKE%" >nul 2>&1
if errorlevel 1 (
    echo add_subdirectory(VisHashFilter)>> "%RP_CMAKE%"
    echo [MLVHF]   Added: add_subdirectory(VisHashFilter)
) else (
    echo [MLVHF]   Already present: VisHashFilter (skipped)
)

findstr /c:"add_subdirectory(ReSTIRGIPass)" "%RP_CMAKE%" >nul 2>&1
if errorlevel 1 (
    echo add_subdirectory(ReSTIRGIPass)>> "%RP_CMAKE%"
    echo [MLVHF]   Added: add_subdirectory(ReSTIRGIPass)
) else (
    echo [MLVHF]   Already present: ReSTIRGIPass (skipped)
)

: ---------------------------------------------------------------------------
: Step 5: Run Python unit tests
: ---------------------------------------------------------------------------
echo [MLVHF] Step 5: Running CPU unit tests...
python "%SCRIPT_DIR%tests\test_vhf_convergence.py"
if errorlevel 1 (
    echo [MLVHF] ERROR: Unit tests failed!
    exit /b 1
)
echo [MLVHF]   All unit tests passed.

: ---------------------------------------------------------------------------
: Done
: ---------------------------------------------------------------------------
echo.
echo [MLVHF] Setup complete.
echo.
echo Next steps:
echo   1. Open %FALCOR_ROOT%\build\windows-vs2022\Falcor.sln in Visual Studio
echo   2. Build target: Mogwai (Release, x64)
echo   3. Run: Mogwai.exe --script scripts/MLVHF/MLVHF_Graph.py --scene Bistro_Interior.pyscene
echo.

exit /b 0
