@echo off
setlocal enabledelayedexpansion
title 3D USD Asset Portal - Auto Sync Watcher
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
echo   Auto Sync Watcher
echo   Watching : \\TOP2\Project\SimReady\output
echo   Action   : rebuild + push + verify whenever assets change
echo   Log      : logs\autosync.log
echo   Press Ctrl+C to stop.
echo ======================================================================
echo.

"%PYTHON_EXE%" watch_and_sync.py %*

pause
