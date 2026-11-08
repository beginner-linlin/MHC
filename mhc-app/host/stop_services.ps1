# 停止 MHC 工作台的服务（由 停止MHC工作台.bat 调用）
# 优先按 run\proxy.pid 停止代理；pid 文件缺失或失效时按 8080 端口找 node 进程兜底
$ErrorActionPreference = 'SilentlyContinue'
$AppDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RunDir = Join-Path $AppDir 'run'
$PidFile = Join-Path $RunDir 'proxy.pid'

$killed = @()

# 1) pid 文件
if (Test-Path $PidFile) {
    $p = Get-Content $PidFile | Select-Object -First 1
    if ($p) {
        $proc = Get-Process -Id ([int]$p) -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match 'node') {
            Stop-Process -Id $p -Force
            $killed += "pid $p (pid 文件)"
        }
    }
    Remove-Item $PidFile -Force
}

# 2) 端口兜底：任何监听 8080 的 node 进程
$conns = netstat -ano | Select-String 'LISTENING' | Select-String ':8080\s'
foreach ($c in $conns) {
    $parts = ($c.ToString().Trim() -split '\s+')
    $procId = [int]$parts[-1]
    if ($procId -gt 4) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -match 'node') {
            Stop-Process -Id $procId -Force
            $killed += "pid $procId (端口 8080)"
        }
    }
}

if ($killed) {
    Write-Host "        已停止代理: $($killed -join ', ')"
} else {
    Write-Host '        代理未在运行'
}
