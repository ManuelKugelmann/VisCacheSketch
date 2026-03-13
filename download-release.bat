@echo off
REM download-release.bat — Download latest GitHub release (Mogwai + plugins).
call "%~dp0scripts\download_release.bat" %*
exit /b %ERRORLEVEL%
