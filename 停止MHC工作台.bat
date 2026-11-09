@echo off
chcp 936 >nul
title MHC Workbench - 停止服务
cd /d "%~dp0"

rem ==== 自动定位 mhc-app 目录（兼容不同摆放位置）====
set "APPDIR="
if exist "%~dp0mhc-app\host\stop_services.ps1" set "APPDIR=%~dp0mhc-app"
if not defined APPDIR if exist "%~dp0mhc-workbench\mhc-app\host\stop_services.ps1" set "APPDIR=%~dp0mhc-workbench\mhc-app"
if not defined APPDIR if exist "%~dp0..\mhc-app\host\stop_services.ps1" set "APPDIR=%~dp0..\mhc-app"
if not defined APPDIR if exist "C:\Users\86156\Desktop\大创\软件\mhc-app\host\stop_services.ps1" set "APPDIR=C:\Users\86156\Desktop\大创\软件\mhc-app"
if not defined APPDIR (
    echo.
    echo   [错误] 未找到 mhc-app 应用目录，无法停止。
    echo.
    if "%MHC_NO_WAIT%"=="" pause
    exit /b 1
)

echo.
echo   ==========================================
echo          MHC 预测工作台 - 正在停止
echo   ==========================================
echo.

if "%MHC_NO_CONFIRM%"=="" (
    set /p CONFIRM="  确认停止所有服务？(Y/N) "
    if /i not "%CONFIRM%"=="Y" (
        echo   已取消。
        timeout /t 2 >nul
        exit /b 0
    )
)

echo.
echo   [1/2] 停止 Windows 侧代理...
powershell -NoProfile -ExecutionPolicy Bypass -File "%APPDIR%\host\stop_services.ps1"
echo         完成

echo   [2/2] 停止 WSL 内后端...
wsl.exe -d Ubuntu-24.04 -u root -- bash /opt/bio/app/host/start_backend.sh stop
if errorlevel 1 (
    echo         后端可能已停止
) else (
    echo         完成
)

echo.
echo   所有服务已停止。
echo.
if "%MHC_NO_WAIT%"=="" timeout /t 3 /nobreak >nul
exit /b 0
