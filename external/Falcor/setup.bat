: This script is fetching all dependencies via packman.

@echo off
setlocal

set PACKMAN=%~dp0\tools\packman\packman.cmd
set PLATFORM=windows-x86_64

echo Fetching pinned submodules ...

where /q git
if errorlevel 1 (
    echo Cannot find git on PATH! Please initialize submodules manually and rerun.
    exit /b 1
)

for /f "usebackq tokens=1,2,3" %%A in (`findstr /v "^#" %~dp0\external\submodules.txt`) do (
    if not exist %~dp0\external\%%A\CMakeLists.txt (
        if not exist %~dp0\external\%%A\imgui.h (
            echo   Fetching %%A @ %%C
            if exist %~dp0\external\%%A rmdir /s /q %~dp0\external\%%A
            mkdir %~dp0\external\%%A
            git -C %~dp0\external\%%A init -q
            git -C %~dp0\external\%%A remote add origin %%B
            git -C %~dp0\external\%%A fetch --depth 1 origin %%C
            git -C %~dp0\external\%%A checkout FETCH_HEAD -q
        )
    ) else (
        echo   %%A already present, skipping
    )
)

echo Fetching dependencies ...

call %PACKMAN% pull --platform %PLATFORM% %~dp0\dependencies.xml
if errorlevel 1 goto error

if not exist %~dp0\.vscode\ (
    echo Setting up VS Code workspace ...
    xcopy %~dp0\.vscode-default\ %~dp0\.vscode\ /y
)

exit /b 0

:error
echo Failed to fetch dependencies!
exit /b 1
