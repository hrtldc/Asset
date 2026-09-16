@echo off
setlocal enabledelayedexpansion
title 3D Asset Portal - Update Public Showcase
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" sync_pipeline.py

echo.
pause