@echo off
title MHC Workbench - Starting
cd /d "%~dp0"

rem ==== 自动定位 mhc-app 目录（兼容不同摆放位置）====
set "APPDIR="
if exist "%~dp0mhc-app\host\launch.ps1" set "APPDIR=%~dp0mhc-app"
if not defined APPDIR if exist "%~dp0mhc-workbench\mhc-app\host\launch.ps1" set "APPDIR=%~dp0mhc-workbench\mhc-app"
if not defined APPDIR if exist "%~dp0..\mhc-app\host\launch.ps1" set "APPDIR=%~dp0..\mhc-app"
if not defined APPDIR if exist "C:\Users\86156\Desktop\大创\软件\mhc-app\host\launch.ps1" set "APPDIR=C:\Users\86156\Desktop\大创\软件\mhc-app"
if not defined APPDIR (
    echo.
    echo   [错误] 未找到 mhc-app 应用目录。
    echo   请把本文件放回以下任一位置后重试：
    echo     - 与 mhc-app 文件夹同一层
    echo     - 与 mhc-workbench 文件夹同一层
    echo.
    if "%MHC_NO_WAIT%"=="" pause
    exit /b 1
)

if not exist "%APPDIR%\run" mkdir "%APPDIR%\run"
echo bat-started >> "%APPDIR%\run\launch_trace.log"

echo.
echo   ==========================================
echo          MHC 预测工作台 - 正在启动
echo   ==========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%APPDIR%\host\launch.ps1"
set RC=%ERRORLEVEL%
echo launch-exit-%RC% >> "%APPDIR%\run\launch_trace.log"

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
