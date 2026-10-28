@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m reviewagent serve --host 127.0.0.1 --port 8000
  exit /b
)
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" -m reviewagent serve --host 127.0.0.1 --port 8000
  exit /b
)
echo 尚未安装项目。请先在此目录运行 deploy\setup.cmd。
echo 安装后打开 http://127.0.0.1:8000/app/
pause
exit /b 1
