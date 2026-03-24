@echo off
setlocal enabledelayedexpansion
REM capture_gallery.bat — Capture test images for all 8 renderer+variant combos.
REM
REM VisCache variants also capture diagnostic heatmaps (prediction error,
REM ray savings ratio, noise, composites) alongside the tone-mapped output.
REM
REM Usage: scripts\capture_gallery.bat [WARMUP_FRAMES] [SCENE]
REM   e.g. scripts\capture_gallery.bat 64
REM        scripts\capture_gallery.bat 128 data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "GALLERY=%ROOT%\.tests"
set "WARMUP=%~1"
if "%WARMUP%"=="" set "WARMUP=64"
set "SCENE=%~2"
if "%SCENE%"=="" set "SCENE=data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene"

echo [gallery] Output: %GALLERY%
echo [gallery] Warmup: %WARMUP% frames
echo [gallery] Scene:  %SCENE%
echo.

set "PASS=0"
set "FAIL=0"
set "TOTAL=0"
set "HEATMAPS=0"

for %%R in (MinimalPathTracer PathTracer RTXDI ReSTIRPT) do (
    for %%V in (Graph VisCache_Graph) do (
        set /a TOTAL+=1
        set "GRAPH=scripts/VisCache/%%R_%%V.py"
        set "NAME=%%R_%%V"
        set "NAME=!NAME:_Graph=!"
        echo [gallery] Capturing !NAME! ...

        set "GRAPH_SCRIPT=!GRAPH!"
        set "GALLERY_DIR=%GALLERY%"
        set "WARMUP_FRAMES=%WARMUP%"
        set "CAPTURE_NAME=!NAME!"
        set "SCENE_FILE=%SCENE%"
        call "%ROOT%\scripts\mogwai_run.bat" --headless -s scripts/VisCache/capture_gallery.py >nul 2>&1

        if !errorlevel! equ 0 (
            echo [gallery]   OK
            set /a PASS+=1
            echo !NAME!|find "VisCache" >nul && set /a HEATMAPS+=1
        ) else (
            echo [gallery]   FAIL
            set /a FAIL+=1
        )
    )
)

echo.
echo ========================================
echo  Gallery: !PASS!/!TOTAL! captured to %GALLERY%
if !HEATMAPS! gtr 0 (
    echo  VisCache stats: !HEATMAPS! variant^(s^) with heatmaps
    echo  Colormap outputs: vcRayTracedRatio, vcNoiseEstimate
)
echo ========================================
if !FAIL! gtr 0 exit /b 1
exit /b 0
