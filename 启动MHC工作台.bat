@echo off
title MHC 预测工作台 - 启动中
cd /d "%~dp0mhc-app\host"

echo.
echo   ==========================================
echo          MHC 预测工作台 - 正在启动
echo   ==========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mhc-app\host\launch.ps1"
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
    echo.
    echo   [启动失败] 请把上面的错误信息截图反馈。
    echo.
    if "%MHC_NO_WAIT%"=="" pause
    exit /b %RC%
)

echo   窗口将在 8 秒后自动关闭（服务在后台继续运行）。
echo   如需再次打开页面，访问 http://127.0.0.1:8080/
echo.
if "%MHC_NO_WAIT%"=="" timeout /t 8 /nobreak >nul
exit /b 0
