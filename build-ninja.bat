@echo off
REM build-ninja.bat — Build with Ninja/MSVC (faster than VS2022 MSBuild).
REM
REM Usage:  build-ninja.bat [--config Release|Debug] [--skip-setup] [--clean]
REM
REM All arguments are forwarded to build.bat with --preset windows-ninja-msvc.

call "%~dp0build.bat" --preset windows-ninja-msvc %*
