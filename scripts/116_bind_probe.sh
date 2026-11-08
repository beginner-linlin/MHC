#!/bin/bash
# 测试 Windows 能否访问 WSL 内绑定在 127.0.0.1 与 0.0.0.0 的服务
set -u
echo "=== 启动测试服务 ==="
cd /tmp
mkdir -p probe && cd probe
printf '{"who":"127"}' > 127.json
printf '{"who":"0000"}' > 0000.json

python3 -m http.server 18801 --bind 127.0.0.1 --directory /tmp/probe >/dev/null 2>&1 &
P1=$!
# 用两个不同目录区分
mkdir -p /tmp/probe2
printf '{"who":"0000"}' > /tmp/probe2/0000.json
python3 -m http.server 18802 --bind 0.0.0.0 --directory /tmp/probe2 >/dev/null 2>&1 &
P2=$!
sleep 1.5
echo "127.0.0.1:18801 -> $(curl -s --max-time 2 http://127.0.0.1:18801/0000.json || echo FAIL)"
echo "0.0.0.0:18802  -> $(curl -s --max-time 2 http://127.0.0.1:18802/0000.json || echo FAIL)"
ss -ltn | grep -E '18801|18802'
echo "P1=$P1 P2=$P2"
# 留给 Windows 侧探测
sleep 25
kill $P1 $P2 2>/dev/null
echo "测试服务已关闭"
