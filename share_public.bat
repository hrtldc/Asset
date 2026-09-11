@echo off
chcp 65001 >nul
title Cloudflare 免费公网隧道 (Cloudflare Tunnel)

echo ======================================================================
echo   正在通过 Cloudflare Tunnel 为您的 3D 资产库建立全球公网安全隧道...
echo   (外部用户无需上传 5.4GB 资产，直接通过云端高速访问您本地 G 盘)
echo ======================================================================
cd /d "%~dp0"

echo 正在检查本地 8088 服务...
netstat -ano | findstr :8088 >nul
if errorlevel 1 (
    echo [提示] 正在自动启动后台 8088 资产服务...
    start /b python server.py
    timeout /t 3 /nobreak >nul
)

echo.
echo ======================================================================
echo   正在申请 Cloudflare 全球 HTTPS 免费安全链接，请稍候几秒钟...
echo   (生成后会显示在下方以 https://xxx.trycloudflare.com 开头的网址)
echo ======================================================================
echo.

"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8088

pause