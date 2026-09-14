@echo off
setlocal enabledelayedexpansion
title Update Public Showcase to Cloudflare Pages
cd /d "%~dp0"

echo ======================================================================
echo   1. ???? G:\Simreay\output ???????...
echo ======================================================================

set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" build_static_showcase.py

copy /y "static\index.html" "index.html" >nul

echo ======================================================================
echo   2. ???????? GitHub (???? Cloudflare Pages ??)...
echo ======================================================================

set "GIT_EXE=C:\Program Files\Git\bin\git.exe"
if exist "%GIT_EXE%" (
    "%GIT_EXE%" add static/media static/data/assets.json index.html static/index.html
    "%GIT_EXE%" commit -m "update: sync latest 3D assets and videos"
)

echo.
echo ======================================================================
echo   [??] ????????
echo   ????? GitHub Desktop ???????Push origin???????????
echo ======================================================================

start "" "%LOCALAPPDATA%\GitHubDesktop\GitHubDesktop.exe"
pause
