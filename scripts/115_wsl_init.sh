#!/bin/bash
echo "=== systemd 是否作为 PID 1 ==="
ps -p 1 -o comm= 2>/dev/null
echo
echo "=== /etc/wsl.conf ==="
cat /etc/wsl.conf 2>/dev/null || echo "(不存在)"
echo
echo "=== wsl.exe 版本 ==="
/mnt/c/Windows/System32/wsl.exe --version 2>/dev/null | head -6
echo
echo "=== 当前监听的端口 ==="
ss -ltnp 2>/dev/null | head -20
echo
echo "=== 可选端口占用检查（8008/8080） ==="
for p in 8008 8080; do
  if ss -ltn 2>/dev/null | grep -q ":$p "; then echo "  $p 已被占用"; else echo "  $p 空闲"; fi
done
