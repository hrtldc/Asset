@echo off
setlocal enabledelayedexpansion
title Update Public Showcase to Cloudflare Pages
cd /d "%~dp0"

echo ======================================================================
echo   [1/3] Extracting latest USD physics attributes...
echo ======================================================================

set "ISAAC_PYTHON=g:\jsuds\isaacsim\kit\python\python.exe"
if exist "%ISAAC_PYTHON%" (
    "%ISAAC_PYTHON%" extract_usd_physics.py
)

echo ======================================================================
echo   [2/3] Building lightweight showcase data and media...
echo ======================================================================

set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" build_static_showcase.py

copy /y "static\index.html" "index.html" >nul

echo ======================================================================
echo   [3/3] Committing and pushing to GitHub...
echo ======================================================================

set "GIT_EXE=C:\Program Files\Git\bin\git.exe"
if exist "%GIT_EXE%" (
    "%GIT_EXE%" add -A
    "%GIT_EXE%" commit -m "update: sync latest 3D assets and videos"
    "%GIT_EXE%" push origin main
)

echo.
echo ======================================================================
echo   [SUCCESS] Assets and videos synced and pushed to GitHub!
echo   Cloudflare Pages will update automatically in 1-2 minutes.
echo ======================================================================

pause