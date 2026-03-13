@echo off
REM run-tests.bat — Run CPU algorithm tests.
call "%~dp0scripts\run-tests.bat" %*
exit /b %ERRORLEVEL%
