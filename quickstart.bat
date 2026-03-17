@echo off
REM quickstart.bat — Convenience wrapper at repo root.
REM
REM Usage:  quickstart.bat [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
REM                        [--renderer viscache|minimal] [--skip-scenes]

call "%~dp0scripts\quickstart.bat" %*
exit /b %ERRORLEVEL%
