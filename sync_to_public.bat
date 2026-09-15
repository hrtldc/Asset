@echo off
setlocal enabledelayedexpansion
title Update Public Showcase to Cloudflare Pages
cd /d "%~dp0"
chcp 65001 >nul

echo ======================================================================
echo   1. 正在提取最新的 3D USD 物理属性 (质量、关节参数、本体 QCode)...
echo ======================================================================

set "ISAAC_PYTHON=g:\jsuds\isaacsim\kit\python\python.exe"
if exist "%ISAAC_PYTHON%" (
    "%ISAAC_PYTHON%" extract_usd_physics.py
)

echo ======================================================================
echo   2. 正在扫描 G:\Simreay\output 构建轻量化展示数据与媒体...
echo ======================================================================

set "PYTHON_EXE=C:\Users\ruotong.huang\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" build_static_showcase.py

copy /y "static\index.html" "index.html" >nul

echo ======================================================================
echo   3. 正在提交并自动推送到 GitHub (触发 Cloudflare Pages 自动部署)...
echo ======================================================================

set "GIT_EXE=C:\Program Files\Git\bin\git.exe"
if exist "%GIT_EXE%" (
    "%GIT_EXE%" add -A
    "%GIT_EXE%" commit -m "update: sync latest 3D assets and videos"
    "%GIT_EXE%" push origin main
)

echo.
echo ======================================================================
echo   [完成] 数据已同步推送至 GitHub！
echo   Cloudflare Pages 将在 1~2 分钟内自动部署最新页面与视频。
echo ======================================================================

pause

