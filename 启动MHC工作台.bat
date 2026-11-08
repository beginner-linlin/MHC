@echo off
title MHC Workbench - Starting
cd /d "%~dp0"

if not exist "%~dp0mhc-app\run" mkdir "%~dp0mhc-app\run"
echo bat-started >> "%~dp0mhc-app\run\launch_trace.log"

echo.
echo   ==========================================
echo          MHC 预测工作台 - 正在启动
echo   ==========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mhc-app\host\launch.ps1"
set RC=%ERRORLEVEL%
echo launch-exit-%RC% >> "%~dp0mhc-app\run\launch_trace.log"

if not "%RC%"=="0" (
    echo.
    echo   [启动失败] 请把上面的错误信息截图反馈。
    echo.
    if "%MHC_NO_WAIT%"=="" pause
    exit /b %RC%
)

echo.
echo   ------------------------------------------------------------
echo    服务已在后台运行。关闭本窗口不影响使用。
echo    以后想再打开页面：直接访问  http://127.0.0.1:8080/
echo    或再次双击本文件。
echo   ------------------------------------------------------------
echo.
echo   按任意键关闭本窗口...
if "%MHC_NO_WAIT%"=="" pause >nul
exit /b 0
