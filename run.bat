@echo off
chcp 65001 >nul
title 3D USD Asset Portal - Cyberpunk Edition

echo ========================================================
echo    3D USD 资产展示与下载平台 (Cyberpunk Edition)
echo    端口已设置为 8088 (避免与 AutoDoFT/SimReady 8000 端口冲突)
echo ========================================================
echo 正在启动资产服务并在浏览器打开...
cd /d "%~dp0"

start "" http://127.0.0.1:8088
python server.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 启动失败，请检查 Python 是否已正确安装并在系统 PATH 中。
    pause
)