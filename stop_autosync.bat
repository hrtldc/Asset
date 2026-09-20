@echo off
setlocal enabledelayedexpansion
title 3D USD Asset Portal - Stop Auto Sync
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE="
if exist "C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"
) else if exist "C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python311\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 set "PYTHON_EXE=python"
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python runtime not found.
    pause
    exit /b 1
)

"%PYTHON_EXE%" stop_autosync.py

echo.
echo Press any key to close this window.
pause >nul
