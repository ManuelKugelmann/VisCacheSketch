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

if exist "%EXT_CMAKE%" (
    REM C4996: fmt uses deprecated stdext::checked_array_iterator (MSVC 14.44+)
    findstr /C:"_SILENCE_STDEXT_ARR_ITERS_DEPRECATION_WARNING" "%EXT_CMAKE%" >nul 2>&1
    if errorlevel 1 call :patch_fmt

    REM TBB deprecation: OpenVDB pulls in tbb/task.h which TBB marks deprecated.
    findstr /C:"TBB_SUPPRESS_DEPRECATED_MESSAGES" "%EXT_CMAKE%" >nul 2>&1
    if errorlevel 1 call :patch_tbb
) else (
    echo [integrate] WARNING: %EXT_CMAKE% not found, skipping deprecation patches
)

REM ------------------------------------------------------------------
REM 4. Patch Falcor linker flags for Debug builds
REM ------------------------------------------------------------------
set "FALCOR_CMAKE=%FALCOR%\Source\Falcor\CMakeLists.txt"

REM LNK4098: release CRT vs debug CRT mismatch — append NODEFAULTLIB if missing
if exist "%FALCOR_CMAKE%" (
    findstr /C:"NODEFAULTLIB:MSVCRT" "%FALCOR_CMAKE%" >nul 2>&1
    if errorlevel 1 call :patch_linker
) else (
    echo [integrate] WARNING: %FALCOR_CMAKE% not found, skipping linker patch
)

REM ------------------------------------------------------------------
REM 5. Strip CI path prefix from diagnostics and PDB source paths
REM ------------------------------------------------------------------
set "ROOT_CMAKE=%FALCOR%\CMakeLists.txt"

if exist "%ROOT_CMAKE%" (
    findstr /C:"d1trimfile" "%ROOT_CMAKE%" >nul 2>&1
    if errorlevel 1 call :patch_trimfile
) else (
    echo [integrate] WARNING: %ROOT_CMAKE% not found, skipping d1trimfile patch
)

echo [integrate] Done.
type "%RP_CMAKE%"
goto :eof

REM === Subroutines (outside block nesting, so <> and () are safe in echo) ===

:patch_fmt
copy /Y "%EXT_CMAKE%" "%EXT_CMAKE%.tmp" >nul
>> "%EXT_CMAKE%.tmp" echo.
>> "%EXT_CMAKE%.tmp" echo target_compile_definitions(fmt PRIVATE _SILENCE_STDEXT_ARR_ITERS_DEPRECATION_WARNING)
move /Y "%EXT_CMAKE%.tmp" "%EXT_CMAKE%" >nul
echo [integrate] Patched fmt deprecation warning
goto :eof

:patch_tbb
copy /Y "%EXT_CMAKE%" "%EXT_CMAKE%.tmp" >nul
>> "%EXT_CMAKE%.tmp" echo.
>> "%EXT_CMAKE%.tmp" echo target_compile_definitions(tbb INTERFACE TBB_SUPPRESS_DEPRECATED_MESSAGES=1)
move /Y "%EXT_CMAKE%.tmp" "%EXT_CMAKE%" >nul
echo [integrate] Patched TBB deprecation warning
goto :eof

:patch_linker
REM Append NODEFAULTLIB:MSVCRT linker flag for Debug builds (avoids CRT mismatch LNK4098)
copy /Y "%FALCOR_CMAKE%" "%FALCOR_CMAKE%.tmp" >nul
>> "%FALCOR_CMAKE%.tmp" echo.
>> "%FALCOR_CMAKE%.tmp" echo target_link_options(Falcor PUBLIC $^<$^<AND:$^<CXX_COMPILER_ID:MSVC^>,$^<CONFIG:Debug^>^>:/NODEFAULTLIB:MSVCRT^>)
move /Y "%FALCOR_CMAKE%.tmp" "%FALCOR_CMAKE%" >nul
echo [integrate] Patched Falcor linker flags (NODEFAULTLIB:MSVCRT)
goto :eof

:patch_trimfile
REM Append /d1trimfile to strip CI path prefix from diagnostics
for %%I in ("%FALCOR%") do set "TRIM_PATH=%%~fI"
set "TRIM_PATH=!TRIM_PATH:\=/!"
copy /Y "%ROOT_CMAKE%" "%ROOT_CMAKE%.tmp" >nul
>> "%ROOT_CMAKE%.tmp" echo.
>> "%ROOT_CMAKE%.tmp" echo add_compile_options(/d1trimfile:!TRIM_PATH!/)
move /Y "%ROOT_CMAKE%.tmp" "%ROOT_CMAKE%" >nul
echo [integrate] Patched d1trimfile path stripping
goto :eof
