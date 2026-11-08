# 停止 MHC 工作台的服务（由 停止MHC工作台.bat 调用）
# 三级兜底：① run\proxy.pid ② 监听 8080 的 node ③ 命令行含 server.js 的 node
$ErrorActionPreference = 'SilentlyContinue'
$AppDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RunDir = Join-Path $AppDir 'run'
$PidFile = Join-Path $RunDir 'proxy.pid'

$killed = @()
$seen = @{}

function Stop-NodePid([int]$procId, [string]$why) {
    if ($procId -le 4) { return }
    if ($seen.ContainsKey($procId)) { return }
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -match 'node') {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        $seen[$procId] = $true
        $script:killed += "pid $procId ($why)"
    }
}

# 1) pid 文件
if (Test-Path $PidFile) {
    $p = Get-Content $PidFile | Select-Object -First 1
    if ($p) { Stop-NodePid ([int]$p) 'pid 文件' }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 2) 端口兜底：监听 8080 的 node
$conns = netstat -ano | Select-String 'LISTENING' | Select-String ':8080\s'
foreach ($c in $conns) {
    $parts = ($c.ToString().Trim() -split '\s+')
    Stop-NodePid ([int]$parts[-1]) '端口 8080'
}

# 3) 命令行兜底：进程表里带 server.js 的 node（pid 文件丢失 + 端口已释放的孤儿）
$procs = Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue
foreach ($pr in $procs) {
    if ($pr.CommandLine -and $pr.CommandLine -match 'server\.js') {
        Stop-NodePid ([int]$pr.ProcessId) '命令行 server.js'
    }
}

if ($killed) {
    Write-Host "        已停止代理: $($killed -join ', ')"
} else {
    Write-Host '        代理未在运行'
}
