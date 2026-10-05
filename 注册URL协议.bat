@echo off
chcp 65001 >nul
echo 正在注册 reviewagent:// URL 协议...

reg add "HKCU\Software\Classes\reviewagent" /ve /d "URL:ReviewAgent Protocol" /f >nul
reg add "HKCU\Software\Classes\reviewagent" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\reviewagent\shell" /f >nul
reg add "HKCU\Software\Classes\reviewagent\shell\open" /f >nul
reg add "HKCU\Software\Classes\reviewagent\shell\open\command" /ve /d "\"E:\review-analysis-agent\启动ReviewAgent.bat\"" /f >nul

echo.
echo ============================================
echo   注册成功！
echo   在浏览器地址栏输入 reviewagent:// 即可启动
echo ============================================
echo.
pause
