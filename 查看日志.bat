@echo off
title MHC Workbench - 日志与状态
cd /d "%~dp0"

rem ==== 自动定位 mhc-app 目录（兼容不同摆放位置）====
set "APPDIR="
if exist "%~dp0mhc-app\host\server.js" set "APPDIR=%~dp0mhc-app"
if not defined APPDIR if exist "%~dp0mhc-workbench\mhc-app\host\server.js" set "APPDIR=%~dp0mhc-workbench\mhc-app"
if not defined APPDIR if exist "%~dp0..\mhc-app\host\server.js" set "APPDIR=%~dp0..\mhc-app"
if not defined APPDIR if exist "C:\Users\86156\Desktop\大创\软件\mhc-app\host\server.js" set "APPDIR=C:\Users\86156\Desktop\大创\软件\mhc-app"
if not defined APPDIR (
    echo.
    echo   [错误] 未找到 mhc-app 应用目录。
    echo.
    pause
    exit /b 1
)

:menu
echo.
echo   ==========================================
echo          MHC 预测工作台 - 日志与状态
echo   ==========================================
echo.
echo     [1] 查看服务状态
echo     [2] 查看后端日志（最近 60 行）
echo     [3] 查看代理日志（最近 40 行）
echo     [4] 实时跟踪后端日志（Ctrl+C 退出）
echo     [5] 打开历史记录数据库所在目录
echo     [6] 清空所有历史记录
echo     [0] 退出
echo.
set /p CHOICE="  请输入编号: "

if "%CHOICE%"=="1" goto status
if "%CHOICE%"=="2" goto backendlog
if "%CHOICE%"=="3" goto proxylog
if "%CHOICE%"=="4" goto followlog
if "%CHOICE%"=="5" goto opendir
if "%CHOICE%"=="6" goto clearhist
if "%CHOICE%"=="0" exit /b 0
goto menu

:status
echo.
echo   --- Windows 侧代理 ---
powershell -NoProfile -Command "try { $h = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/__proxy/health' -TimeoutSec 3; Write-Host ('    运行中  pid=' + $h.pid + '  监听=' + $h.listen + '  后端=' + $h.backend) -ForegroundColor Green } catch { Write-Host '    未运行' -ForegroundColor Red }"
echo   --- WSL 内后端 ---
wsl.exe -d Ubuntu-24.04 -u root -- bash /opt/bio/app/host/start_backend.sh status
echo.
pause
goto menu

:backendlog
echo.
wsl.exe -d Ubuntu-24.04 -u root -- bash /opt/bio/app/host/start_backend.sh logs 60
echo.
pause
goto menu

:proxylog
echo.
if exist "%APPDIR%\host\logs\proxy.log" (
    powershell -NoProfile -Command "Get-Content '%APPDIR%\host\logs\proxy.log' -Tail 40"
) else (
    echo     暂无日志文件（代理尚未从本目录启动过）
)
echo.
pause
goto menu

:followlog
echo.
echo   按 Ctrl+C 退出跟踪...
echo.
wsl.exe -d Ubuntu-24.04 -u root -- bash -c "tail -f /opt/bio/app/run/backend.log"
goto menu

:opendir
start "" "\\wsl.localhost\Ubuntu-24.04\opt\bio\app\data"
goto menu

:clearhist
echo.
set /p YES="  确认清空所有历史记录？(Y/N) "
if /i not "%YES%"=="Y" goto menu
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/history/clear' -Method Post -TimeoutSec 10; Write-Host ('    已删除 ' + $r.deleted + ' 条记录') -ForegroundColor Green } catch { Write-Host ('    失败: ' + $_.Exception.Message) -ForegroundColor Red }"
echo.
pause
goto menu
