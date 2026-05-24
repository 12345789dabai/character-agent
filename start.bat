@echo off
chcp 65001 >nul
cd /d %~dp0

echo ========================================
echo   Character Agent v1.0
echo ========================================
echo.

echo [1/3] Starting server ...
start /B python web_app.py > server.log 2>&1

echo [2/3] Waiting for server ready ...
set retries=0

:wait_loop
ping -n 2 127.0.0.1 > nul
set /a retries+=1
if %retries% gtr 15 (
    echo [!] Timeout - check server.log
    pause
    exit /b
)
powershell -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/status' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { exit 1 }" > nul 2>&1
if errorlevel 1 goto wait_loop

echo [3/3] Server ready, opening browser ...
start http://127.0.0.1:8000

echo.
echo Press Ctrl+C to stop the server.
echo Close this window to stop.
echo ========================================
pause > nul
