@echo off
cd /d %~dp0
echo ========================================
echo   永久角色对话 Agent v1.0
echo ========================================
echo.

REM 启动服务（后台运行）
echo [1/3] 正在启动服务 ...
start /B python web_app.py > server.log 2>&1

REM 等待服务就绪，最多等 30 秒
echo [2/3] 等待服务就绪 ...
set retries=0
:wait_loop
ping -n 2 127.0.0.1 > nul
set /a retries+=1
if %retries% gtr 15 (
    echo [!] 启动超时，请检查 server.log
    pause
    exit /b
)
powershell -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/status' -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { exit 1 }" > nul 2>&1
if errorlevel 1 goto wait_loop

REM 打开浏览器
echo [3/3] 服务已就绪，正在打开浏览器 ...
start http://127.0.0.1:8000

REM 保持窗口打开以便停止服务
echo.
echo 按 Ctrl+C 停止服务，或直接关闭此窗口。
echo ========================================
pause > nul
