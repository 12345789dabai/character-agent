@echo off
cd /d %~dp0
echo ========================================
echo   打包永久角色对话 Agent
echo ========================================
echo.

REM 安装 PyInstaller
echo [1/3] 安装 PyInstaller ...
pip install pyinstaller

REM 清理旧构建
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

REM 打包
echo [2/3] 正在打包（可能需要 2-5 分钟）...
pyinstaller --onefile ^
  --noconsole ^
  --name "CharacterAgent" ^
  --add-data "static;static" ^
  --add-data "characters;characters" ^
  --add-data "config.py;." ^
  --hidden-import chromadb ^
  --hidden-import chromadb.utils.embedding_functions ^
  --hidden-import sentence_transformers ^
  --hidden-import uvicorn ^
  --hidden-import uvicorn.loggers ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols.http.auto ^
  launcher.py

echo.
echo [3/3] 打包完成！
echo.
echo 输出文件：dist\CharacterAgent.exe
echo 双击即可运行，约 %~z0 字节
echo.
pause
