@echo off
REM update.bat — In-repo equivalent of the one-liner install command.
REM
REM Usage:  update.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]
REM
REM Delegates entirely to scripts\quickstart.bat which handles:
REM   0. git pull
REM   1. download scenes
REM   2. download release
REM   3. copy newer shaders, data, etc. to release
REM   4. run py tests
REM   5. run headless smoke test
REM   6. launch

setlocal enabledelayedexpansion

set "ROOT=%~dp0"

REM ---------------------------------------------------------------------------
REM Collect pass-through arguments for quickstart
REM ---------------------------------------------------------------------------
set "QS_ARGS="
:parse_args
if "%~1"=="" goto :args_done
set "QS_ARGS=%QS_ARGS% %~1"
shift
goto :parse_args
:args_done

call "%ROOT%scripts\quickstart.bat" %QS_ARGS%

endlocal
