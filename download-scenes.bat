@echo off
REM download-scenes.bat — Fetch test scenes.
call "%~dp0scripts\download_scenes.bat" %*
exit /b %ERRORLEVEL%
