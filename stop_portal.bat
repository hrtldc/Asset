@echo off
title Stop 3D USD Asset Portal Server
echo ======================================================================
echo   Stopping 3D USD Asset Portal Server (Port 8088)...
echo ======================================================================

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8088" ^| findstr "LISTENING"') do (
    echo Terminating PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo [SUCCESS] Local portal server stopped.
timeout /t 2 >nul
