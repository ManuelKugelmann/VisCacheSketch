@echo off
REM run-release.bat — Smoke test + launch Mogwai.
call "%~dp0scripts\run_release.bat" %*
exit /b %ERRORLEVEL%
