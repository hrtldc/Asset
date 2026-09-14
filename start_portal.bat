@echo off
setlocal enabledelayedexpansion
title 3D USD Asset Portal Server [Port 8088]
cd /d "%~dp0"

echo ======================================================================
echo   Starting 3D USD Asset Portal...
echo   Local Web URL: http://127.0.0.1:8088
echo ======================================================================

set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"

if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

:: Wait 1.5s then open default browser automatically
start "" /b powershell -NoProfile -Command "Start-Sleep -Milliseconds 1500; Start-Process 'http://127.0.0.1:8088/'"

:: Run FastAPI server
"%PYTHON_EXE%" server.py

if errorlevel 1 (
    echo.
    echo [ERROR] Server exited with error code %errorlevel%
    pause
)
