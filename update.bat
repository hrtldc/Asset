@echo off
chcp 65001 >nul
title 3D USD 资产全量更新同步工具 (One-Click Asset Update)

echo ========================================================
echo    3D USD 资产全量一键更新推送 (One-Click Update)
echo ========================================================
cd /d "%~dp0"

python update.py

echo.
echo 按任意键关闭窗口...
pause >nul