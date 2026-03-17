@echo off
REM init-refs.bat — Initialize reference submodules in refs/
REM Usage: scripts\init-refs.bat

where bash >nul 2>&1 || (
    echo ERROR: bash not found. Install Git for Windows ^(includes Git Bash^).
    exit /b 1
)

bash "%~dp0init-refs.sh" %*
