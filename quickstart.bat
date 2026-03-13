@echo off
REM quickstart.bat — Convenience wrapper at repo root.
REM
REM Usage:  quickstart.bat [--scene Bistro|Sponza|Arcade] [--skip-scenes]

call "%~dp0scripts\quickstart.bat" %*
exit /b %ERRORLEVEL%
