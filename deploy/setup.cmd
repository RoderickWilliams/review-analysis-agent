@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
where python >nul 2>&1
if errorlevel 1 (
  echo 请先安装 Python 3.10 或更新版本并加入 PATH。
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -m pip install -e ".[api,import]"
if errorlevel 1 exit /b 1
echo 安装完成。模型可在运行环境中配置，配置前也可创建研究并导入评论。
echo 运行 start.bat 启动工作台；本脚本不运行检查。
