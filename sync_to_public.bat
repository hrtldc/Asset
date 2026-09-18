@echo off
setlocal enabledelayedexpansion
title 3D Asset Portal - Update Public Showcase
chcp 65001 >nul
cd /d "%~dp0"

:: 1. Search for available Python executable in order of priority
set "PYTHON_EXE="

if exist "C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"
) else if exist "C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python311\python.exe"
) else if exist "C:\Program Files\Python312\python.exe" (
    set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
) else if exist "G:\JSUDS\IsaacSim\kit\python\python.exe" (
    set "PYTHON_EXE=G:\JSUDS\IsaacSim\kit\python\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [错误] 未能在系统中检测到 Python 运行环境！
    echo 请确认已安装 Python 3.10+。
    pause
    exit /b 1
)

:: 2. Run sync pipeline
"%PYTHON_EXE%" sync_pipeline.py %*

echo.
echo ==============================================================================
echo   按任意键关闭此窗口...
echo ==============================================================================
pause >nul