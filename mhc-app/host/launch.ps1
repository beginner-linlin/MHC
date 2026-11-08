# MHC 预测工作台 —— 启动脚本（Windows 侧）
# 由「启动MHC工作台.bat」调用；也可在 PowerShell 里直接运行：
#   powershell -ExecutionPolicy Bypass -File launch.ps1
#
# 做四件事：
#   1. 确认 WSL 发行版可用
#   2. 在 WSL 内启动 Flask 后端（若未运行）
#   3. 在 Windows 侧启动 Node 反向代理（若未运行）
#   4. 打开浏览器，并打印本机 / 局域网访问地址

[CmdletBinding()]
param(
    [string]$Distro      = 'Ubuntu-24.04',
    [int]   $ProxyPort   = 8080,
    [int]   $BackendPort = 8008,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$HostDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir  = Split-Path -Parent $HostDir
$RunDir  = Join-Path $AppDir 'run'
$LogDir  = Join-Path $HostDir 'logs'
$NodeExe = 'C:\AI\node.exe'

New-Item -ItemType Directory -Force -Path $RunDir, $LogDir | Out-Null

$NodePidFile = Join-Path $RunDir 'proxy.pid'
$NodeLogFile = Join-Path $LogDir 'node.log'
$NodeErrFile = Join-Path $LogDir 'node.err.log'

function Write-Step($msg) { Write-Host "  $msg" }
function Write-Ok($msg)   { Write-Host "  [OK] $msg"   -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "  [!]  $msg"   -ForegroundColor Yellow }
function Write-Bad($msg)  { Write-Host "  [X]  $msg"   -ForegroundColor Red }

function Test-PortListening([int]$port) {
    # 纯 socket 检测，500ms 超时。
    # 不用 Test-NetConnection：它在多网卡/网络异常时会吊死数分钟（ping+DNS+网卡枚举），
    # 导致双击启动看似「无反应」。
    try {
        $c = New-Object Net.Sockets.TcpClient
        $task = $c.ConnectAsync('127.0.0.1', $port)
        $ok = $task.Wait(500) -and $c.Connected
        $c.Close()
        return $ok
    } catch { return $false }
}

function Wait-Http([string]$url, [int]$timeoutSec = 40) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -TimeoutSec 3 -UseBasicParsing
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

Write-Host ''
Write-Host '==========================================' -ForegroundColor Cyan
Write-Host '        MHC 预测工作台 · 正在启动'        -ForegroundColor Cyan
Write-Host '==========================================' -ForegroundColor Cyan
Write-Host ''

# ───────────────────────── 1. 检查前置条件 ─────────────────────────
Write-Host '[1/4] 检查运行环境'

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Write-Bad '找不到 wsl.exe。请确认已安装 WSL。'
    exit 1
}

$distros = (& wsl.exe --list --quiet) -replace "`0", '' | Where-Object { $_.Trim() }
if ($distros -notcontains $Distro) {
    Write-Bad "找不到 WSL 发行版「$Distro」。当前可用：$($distros -join ', ')"
    exit 1
}
Write-Ok "WSL 发行版 $Distro 可用"

if (-not (Test-Path $NodeExe)) {
    Write-Bad "找不到 Node 运行时：$NodeExe"
    Write-Host '      这个程序依赖该路径下的 node.exe。' -ForegroundColor DarkGray
    exit 1
}
Write-Ok "Node 运行时 $(& $NodeExe -e "process.stdout.write(process.version)")"

# ───────────────────────── 2. 启动 WSL 后端 ─────────────────────────
Write-Host ''
Write-Host '[2/4] 启动预测后端（WSL 内 Flask）'

$backendScript = '/opt/bio/app/host/start_backend.sh'
$status = (& wsl.exe -d $Distro -u root -- bash $backendScript status 2>&1) -join "`n"
if ($status -match 'RUNNING') {
    Write-Ok "后端已在运行（$($status.Trim())）"
} else {
    Write-Step '正在拉起后端进程…'
    $out = (& wsl.exe -d $Distro -u root -- bash $backendScript start 2>&1) -join "`n"
    if ($LASTEXITCODE -eq 0 -and $out -match '已启动') {
        Write-Ok ($out.Trim() -split "`n" | Select-Object -Last 1)
    } else {
        Write-Bad '后端启动失败，输出如下：'
        Write-Host $out -ForegroundColor DarkYellow
        exit 1
    }
}

# WSL2 NAT 模式下 Windows→WSL 的 localhost 转发有 1–3 秒延迟，
# 单次探测会误报「端口未监听」→ 改为轮询（最多 20 秒）
$backendReady = $false
for ($i = 0; $i -lt 40; $i++) {
    if (Test-PortListening $BackendPort) { $backendReady = $true; break }
    Start-Sleep -Milliseconds 500
}
if (-not $backendReady) {
    Write-Bad "后端端口 $BackendPort 仍未监听（等待 20 秒）。"
    Write-Host "      可查看日志：wsl -d $Distro -u root -- bash $backendScript logs 40" -ForegroundColor DarkGray
    exit 1
}
# 端口通了再等 HTTP 真正可用（Flask 首次请求要加载工具版本）
if (-not (Wait-Http "http://127.0.0.1:$BackendPort/api/health" 25)) {
    Write-Bad "后端端口已监听但 /api/health 未响应（等待 25 秒）。"
    Write-Host "      可查看日志：wsl -d $Distro -u root -- bash $backendScript logs 40" -ForegroundColor DarkGray
    exit 1
}
Write-Ok "后端端口 $BackendPort 已监听，健康检查通过"

# ───────────────────────── 3. 启动 Node 代理 ─────────────────────────
Write-Host ''
Write-Host '[3/4] 启动局域网访问代理（Windows 侧 Node）'

$healthUrl = "http://127.0.0.1:$ProxyPort/__proxy/health"
$needStart = $true
if (Test-PortListening $ProxyPort) {
    try {
        $h = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3
        if ($h.ok -and $h.role -eq 'proxy') { $needStart = $false }
    } catch { }
}

if (-not $needStart) {
    Write-Ok "代理已在运行（$ProxyPort 端口）"
} else {
    if (Test-PortListening $ProxyPort) {
        Write-Bad "端口 $ProxyPort 被其他程序占用，代理无法启动。"
        exit 1
    }

    Write-Step "启动 node server.js（监听 0.0.0.0:$ProxyPort）…"
    $env:MHC_PROXY_PORT = "$ProxyPort"
    $env:MHC_BACKEND    = "http://127.0.0.1:$BackendPort"

    $proc = Start-Process -FilePath $NodeExe `
        -ArgumentList 'server.js' `
        -WorkingDirectory $HostDir `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $NodeLogFile `
        -RedirectStandardError  $NodeErrFile
    $proc.Id | Set-Content -Path $NodePidFile -Encoding ASCII

    if (Wait-Http $healthUrl 20) {
        Write-Ok "代理已启动（pid $($proc.Id)）"
    } else {
        Write-Bad '代理启动超时，错误日志：'
        if (Test-Path $NodeErrFile) { Get-Content $NodeErrFile -Tail 20 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkYellow } }
        exit 1
    }
}

# ───────────────────────── 4. 打开浏览器 ─────────────────────────
Write-Host ''
Write-Host '[4/4] 准备访问地址'

$lanIps = @()
try {
    # 只查已启用、可单播的 IPv4 地址；超时保护由 -ErrorAction 与外层 try 提供
    $lanIps = @(Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp,Manual -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike '127.*' -and
            $_.IPAddress -notlike '169.254.*' -and
            $_.IPAddress -notlike '172.27.*'
        } |
        Sort-Object -Property { if ($_.InterfaceAlias -match '以太|Ethernet') { 0 } elseif ($_.InterfaceAlias -match 'WLAN|Wi-Fi') { 1 } else { 2 } } |
        Select-Object -ExpandProperty IPAddress -Unique)
} catch { }

$localUrl = "http://127.0.0.1:$ProxyPort/"

# 最终健康检查：确认整条链路都通
$finalOk = $false
try {
    $r = Invoke-RestMethod -Uri "http://127.0.0.1:$ProxyPort/api/health" -TimeoutSec 10
    $finalOk = [bool]$r.ok
    $toolLines = $r.tools.PSObject.Properties | ForEach-Object { "        $($_.Name): $($_.Value)" }
} catch { $toolLines = @() }

Write-Host ''
Write-Host '==========================================' -ForegroundColor Green
if ($finalOk) {
    Write-Host '            启动成功，可以开始使用'      -ForegroundColor Green
} else {
    Write-Host '        服务已启动，但健康检查未通过'    -ForegroundColor Yellow
}
Write-Host '==========================================' -ForegroundColor Green
Write-Host ''
Write-Host '  本机访问：  ' -NoNewline; Write-Host $localUrl -ForegroundColor Cyan
if ($lanIps.Count -gt 0) {
    Write-Host '  局域网访问：' -ForegroundColor Gray
    foreach ($ip in $lanIps) {
        Write-Host "              http://${ip}:$ProxyPort/" -ForegroundColor Cyan
    }
} else {
    Write-Host '  局域网访问：未检测到可用网卡地址' -ForegroundColor DarkGray
}
Write-Host ''
Write-Host '  工具状态：' -ForegroundColor Gray
if ($toolLines.Count) { $toolLines | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray } }
else { Write-Host '        (未能读取)' -ForegroundColor DarkGray }
Write-Host ''
Write-Host '  停止服务：双击「停止MHC工作台.bat」' -ForegroundColor Gray
Write-Host '  查看日志：双击「查看日志.bat」'      -ForegroundColor Gray
Write-Host ''

if (-not $NoBrowser) {
    # 强制新窗口 + 前台弹出：直接调 Edge/Chrome 可执行文件。
    # 不能只 Start-Process $url —— 那会把页面塞进已存在的后台 Edge 窗口，用户前台看不到，
    # 表现为「双击无反应」。
    $opened = $false
    foreach ($exe in @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )) {
        if (Test-Path $exe) {
            try {
                Start-Process -FilePath $exe -ArgumentList '--new-window', $localUrl
                $opened = $true
                break
            } catch { }
        }
    }
    if (-not $opened) {
        try { Start-Process $localUrl } catch { Write-Warn2 '无法自动打开浏览器，请手动复制上面的地址到浏览器。' }
    }
}

Start-Sleep -Seconds 2
