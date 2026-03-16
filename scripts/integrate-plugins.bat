@echo off
setlocal enabledelayedexpansion
REM integrate-plugins.bat — Copy VisCache/ReSTIRPTPass into Falcor tree and patch CMake.
REM
REM Usage (from repo root):
REM     scripts\integrate-plugins.bat [FalcorDir]
REM
REM Called by build.yml (Windows VS2022 + Ninja jobs) and usable locally.

set "FALCOR=%~1"
if "%FALCOR%"=="" set "FALCOR=Falcor"

REM ------------------------------------------------------------------
REM 1. Copy plugin sources into Falcor render-passes directory
REM ------------------------------------------------------------------
for %%P in (VisCache ReSTIRPTPass) do (
    set "DEST=%FALCOR%\Source\RenderPasses\%%P"
    if not exist "!DEST!" mkdir "!DEST!"
    xcopy /E /Y /Q "Source\RenderPasses\%%P\*" "!DEST!\" >nul
    echo [integrate] Copied %%P -^> !DEST!
)

REM Copy scripts
if not exist "%FALCOR%\scripts\VisCache" mkdir "%FALCOR%\scripts\VisCache"
xcopy /E /Y /Q "scripts\*" "%FALCOR%\scripts\VisCache\" >nul
echo [integrate] Copied scripts -^> %FALCOR%\scripts\VisCache\

REM ------------------------------------------------------------------
REM 2. Patch RenderPasses/CMakeLists.txt to add our subdirectories
REM ------------------------------------------------------------------
set "RP_CMAKE=%FALCOR%\Source\RenderPasses\CMakeLists.txt"
for %%S in (VisCache ReSTIRPTPass) do (
    findstr /C:"add_subdirectory(%%S)" "!RP_CMAKE!" >nul 2>&1
    if errorlevel 1 (
        echo.>> "!RP_CMAKE!"
        echo add_subdirectory(%%S)>> "!RP_CMAKE!"
        echo [integrate] Patched !RP_CMAKE!: added %%S
    )
)

REM ------------------------------------------------------------------
REM 3. Patch external/CMakeLists.txt to silence upstream build warnings
REM ------------------------------------------------------------------
set "EXT_CMAKE=%FALCOR%\external\CMakeLists.txt"

REM C4996: fmt uses deprecated stdext::checked_array_iterator (MSVC 14.44+)
findstr /C:"_SILENCE_STDEXT_ARR_ITERS_DEPRECATION_WARNING" "%EXT_CMAKE%" >nul 2>&1
if errorlevel 1 (
    echo.>> "%EXT_CMAKE%"
    echo target_compile_definitions(fmt PRIVATE _SILENCE_STDEXT_ARR_ITERS_DEPRECATION_WARNING)>> "%EXT_CMAKE%"
    echo [integrate] Patched fmt deprecation warning
)

REM TBB deprecation: OpenVDB pulls in tbb/task.h which TBB marks deprecated.
findstr /C:"TBB_SUPPRESS_DEPRECATED_MESSAGES" "%EXT_CMAKE%" >nul 2>&1
if errorlevel 1 (
    echo.>> "%EXT_CMAKE%"
    echo target_compile_definitions(tbb INTERFACE TBB_SUPPRESS_DEPRECATED_MESSAGES=1)>> "%EXT_CMAKE%"
    echo [integrate] Patched TBB deprecation warning
)

REM ------------------------------------------------------------------
REM 4. Patch Falcor linker flags for Debug builds
REM ------------------------------------------------------------------
set "FALCOR_CMAKE=%FALCOR%\Source\Falcor\CMakeLists.txt"

REM LNK4098: release CRT vs debug CRT mismatch — append NODEFAULTLIB if missing
findstr /C:"NODEFAULTLIB:MSVCRT" "%FALCOR_CMAKE%" >nul 2>&1
if errorlevel 1 (
    REM Use PowerShell one-liner for regex insertion (no .ps1 execution policy needed)
    powershell -NoProfile -Command "$c = Get-Content '%FALCOR_CMAKE%' -Raw; $c = $c -replace '(target_link_options\(Falcor\s+PUBLIC\s+# MSVC flags\.)', \"`$1`n        `$<`$<AND:`$<CXX_COMPILER_ID:MSVC>,`$<CONFIG:Debug>>:/NODEFAULTLIB:MSVCRT>\"; Set-Content '%FALCOR_CMAKE%' $c -NoNewline"
    echo [integrate] Patched Falcor linker flags (NODEFAULTLIB:MSVCRT^)
)

REM ------------------------------------------------------------------
REM 5. Strip CI path prefix from diagnostics and PDB source paths
REM ------------------------------------------------------------------
set "ROOT_CMAKE=%FALCOR%\CMakeLists.txt"

findstr /C:"d1trimfile" "%ROOT_CMAKE%" >nul 2>&1
if errorlevel 1 (
    REM Resolve absolute path with forward slashes for /d1trimfile
    for %%I in ("%FALCOR%") do set "TRIM_PATH=%%~fI"
    set "TRIM_PATH=!TRIM_PATH:\=/!"
    REM Use PowerShell one-liner for regex insertion
    powershell -NoProfile -Command "$c = Get-Content '%ROOT_CMAKE%' -Raw; $c = $c -replace '(project\(Falcor[^)]*\))', \"`$1`nadd_compile_options(/d1trimfile:!TRIM_PATH!/)\"; Set-Content '%ROOT_CMAKE%' $c -NoNewline"
    echo [integrate] Patched d1trimfile path stripping
)

echo [integrate] Done.
type "%RP_CMAKE%"
