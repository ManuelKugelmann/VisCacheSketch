@echo off
REM version.bat — Print git SHA + timestamp for version tracking.
REM
REM Usage: call scripts\version.bat [prefix]
REM   Prints: [prefix] version: <short-sha> (<date> <time>)
REM   Sets:   VCS_SHA, VCS_TIMESTAMP
REM
REM Example output:
REM   [install] version: 2f115e6 (2026-03-13 14:05:02)

setlocal enabledelayedexpansion

set "PREFIX=%~1"
if "%PREFIX%"=="" set "PREFIX=version"

REM --- Git SHA ---
set "VCS_SHA=unknown"
where git >nul 2>&1 && (
    for /f "tokens=*" %%H in ('git rev-parse --short HEAD 2^>nul') do set "VCS_SHA=%%H"
)

REM --- Timestamp ---
set "VCS_TIMESTAMP=%DATE% %TIME:~0,8%"

echo [%PREFIX%] version: %VCS_SHA% (%VCS_TIMESTAMP%)

endlocal & set "VCS_SHA=%VCS_SHA%" & set "VCS_TIMESTAMP=%VCS_TIMESTAMP%"
