@echo off
chcp 65001 >nul
title ReviewAgent 一键启动

setlocal enabledelayedexpansion

:: ============================================
:: ReviewAgent 一键启动脚本（含 Python 自动安装）
:: 项目目录：脚本所在目录（任意位置均可）
:: Python 目录：%LOCALAPPDATA%\Programs\Python\Python312
:: ============================================

:: 脚本所在目录即项目目录
set "INSTALL_DIR=%~dp0"
:: 去掉末尾反斜杠
if "%INSTALL_DIR:~-1%"=="\" set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"

set "PYTHON_DIR=%LOCALAPPDATA%\Programs\Python\Python312"
set "PYTHON_VER=3.12.10"
set "PYTHON_INSTALLER=%TEMP%\python-%PYTHON_VER%-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VER%/python-%PYTHON_VER%-amd64.exe"

echo.
echo ============================================
echo   ReviewAgent 智能评论分析 Agent
echo ============================================
echo.

:: ------------------------------------------
:: 1. 检查项目目录
:: ------------------------------------------
if not exist "%INSTALL_DIR%\app.py" (
    echo [初始化] 项目目录不存在: %INSTALL_DIR%
    echo.
    echo 请将项目文件放到任意目录，然后双击本脚本启动。
    echo 获取项目:
    echo   git clone https://github.com/RoderickWilliams/review-analysis-agent.git
    echo   或下载 ZIP 解压后将 start.bat 放入项目根目录。
    echo.
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"
echo [1/6] 项目目录: %CD%

:: ------------------------------------------
:: 2. 检查 Python（系统已有则检查版本，没有则安装）
:: ------------------------------------------
set "PYTHON_EXE="

echo [2/6] 检查 Python 环境...

:: 先检查本地安装的 Python
if exist "%PYTHON_DIR%\python.exe" (
    for /f "tokens=2" %%v in ('"%PYTHON_DIR%\python.exe" --version 2^>^&1') do set VER=%%v
    for /f "tokens=1,2 delims=." %%a in ("!VER!") do (
        set MAJOR=%%a
        set MINOR=%%b
    )
    if !MAJOR! GEQ 3 if !MINOR! GEQ 10 (
        set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
        echo       找到本地 Python !VER! (%PYTHON_DIR%)
    )
)

:: 再检查系统 PATH 中的 Python
if not defined PYTHON_EXE (
    python --version >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2" %%v in ('python --version 2^>^&1') do set VER=%%v
        for /f "tokens=1,2 delims=." %%a in ("!VER!") do (
            set MAJOR=%%a
            set MINOR=%%b
        )
        if !MAJOR! GEQ 3 if !MINOR! GEQ 10 (
            set "PYTHON_EXE=python"
            echo       找到系统 Python !VER!
        ) else (
            echo       系统 Python !VER! 版本过低（需要 3.10+），将安装新版本
        )
    )
)

:: 都没有或版本过低，自动下载安装
if not defined PYTHON_EXE (
    echo       未检测到合适的 Python，开始自动安装 Python %PYTHON_VER%...
    echo       下载地址: %PYTHON_URL%
    echo.

    :: 下载 Python 安装包
    where curl >nul 2>&1
    if not errorlevel 1 (
        curl -L -o "%PYTHON_INSTALLER%" "%PYTHON_URL%" --progress-bar
    ) else (
        powershell -Command "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"
    )

    if not exist "%PYTHON_INSTALLER%" (
        echo.
        echo [错误] Python 安装包下载失败，请检查网络连接
        echo 你也可以手动安装 Python 3.10+ : https://www.python.org/downloads/
        echo.
        pause
        exit /b 1
    )

    echo       正在静默安装到 %PYTHON_DIR% ...
    "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%PYTHON_DIR%" PrependPath=0 Include_test=0 Include_doc=0 Include_launcher=0 Shortcuts=0

    timeout /t 5 /nobreak >nul

    if exist "%PYTHON_DIR%\python.exe" (
        set "PYTHON_EXE=%PYTHON_DIR%\python.exe"
        echo       Python %PYTHON_VER% 安装成功
        del "%PYTHON_INSTALLER%" 2>nul
    ) else (
        echo.
        echo [错误] Python 安装失败，请手动安装:
        echo   1. 访问 https://www.python.org/downloads/
        echo   2. 下载 Python 3.10+ 并安装
        echo   3. 重新运行此脚本
        echo.
        pause
        exit /b 1
    )
)

for /f "tokens=2" %%v in ('"%PYTHON_EXE%" --version 2^>^&1') do echo       使用 Python %%v

:: ------------------------------------------
:: 3. 创建虚拟环境 + 安装依赖
:: ------------------------------------------
if not exist "venv\Scripts\python.exe" (
    echo [3/6] 首次运行，创建虚拟环境...
    "%PYTHON_EXE%" -m venv venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
) else (
    echo [3/6] 虚拟环境已存在
)

echo       安装/更新依赖（首次需要几分钟）...
"venv\Scripts\python.exe" -m pip install --upgrade pip -q 2>nul
"venv\Scripts\pip.exe" install -r requirements.txt -q
if errorlevel 1 (
    echo [警告] 部分依赖安装可能失败，尝试继续启动...
)

:: ------------------------------------------
:: 4. 安装 Patchright 浏览器
:: ------------------------------------------
echo [4/6] 检查浏览器...
"venv\Scripts\patchright.exe" install chromium 2>nul
if errorlevel 1 (
    echo       浏览器已安装或跳过
)

:: ------------------------------------------
:: 5. 检查 .env 配置
:: ------------------------------------------
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo [5/6] 已从 .env.example 创建 .env
        echo.
        echo ============================================
        echo   重要：请编辑 .env 文件填入 API Key
        echo   文件位置: %INSTALL_DIR%\.env
        echo ============================================
        echo.
        echo 按任意键打开 .env 进行编辑...
        pause >nul
        notepad .env
    )
) else (
    echo [5/6] .env 配置文件已存在
)

:: ------------------------------------------
:: 6. 检查 Chrome 浏览器（DrissionPage 依赖）
:: ------------------------------------------
echo [6/6] 检查 Chrome 浏览器...
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>&1
if errorlevel 1 (
    reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo [提示] 未检测到 Chrome 浏览器，京东链接采集需要 Chrome。
        echo 淘宝采集和 CSV/截图分析不受影响。
        echo 如需京东采集，请安装 Chrome: https://www.google.com/chrome/
        echo.
        timeout /t 3 /nobreak >nul
    ) else (
        echo       Chrome 已安装
    )
) else (
    echo       Chrome 已安装
)

:: ------------------------------------------
:: 启动
:: ------------------------------------------
echo.
echo ============================================
echo   启动 ReviewAgent...
echo   浏览器将自动打开 http://127.0.0.1:8501
echo   关闭此窗口即可停止服务
echo ============================================
echo.

"venv\Scripts\python.exe" -m streamlit run app.py --server.headless=true --server.port=8501 --server.address=127.0.0.1

pause
