@echo off
setlocal enabledelayedexpansion
title 3D USD Asset Portal - Full Public Sync
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"
) else if exist "C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python311\python.exe"
) else if exist "C:\Program Files\Python312\python.exe" (
    set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_EXE=python"
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python runtime not found. Please install Python 3.10+.
    pause
    exit /b 1
)

echo ======================================================================
echo   Full Public Sync
echo   1) Rebuild static showcase from G:\Simreay\output
echo   2) Push media first, then metadata (atomic consistency)
echo   3) Verify the public site matches local item by item
echo ======================================================================
echo.

"%PYTHON_EXE%" sync_pipeline.py %*

echo.
echo ======================================================================
echo   Waiting for Cloudflare Pages deployment and verifying...
echo ======================================================================
"%PYTHON_EXE%" verify_sync.py --wait 240

echo.
echo ======================================================================
echo   Done. Press any key to close this window.
echo ======================================================================
pause >nul
