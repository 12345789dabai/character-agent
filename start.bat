@echo off
cd /d %~dp0
echo 正在启动永久角色对话 Agent ...
start "" http://127.0.0.1:8000
python web_app.py
pause
