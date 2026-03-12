@echo off
REM sync-submodules.bat — Wrapper that calls sync-submodules.sh via Git Bash.
REM Usage: sync-submodules.bat {from-upstream|to-upstream|check}

where bash >nul 2>&1 || (
    echo ERROR: bash not found. Install Git for Windows (includes Git Bash).
    exit /b 1
)

bash "%~dp0sync-submodules.sh" %*
