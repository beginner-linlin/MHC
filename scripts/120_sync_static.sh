#!/usr/bin/env bash
# 快速同步前端静态文件 + 重启后端
set -euo pipefail

SRC="/mnt/c/Users/86156/Desktop/大创/软件/mhc-app"
DST="/opt/bio/app"

echo "=== 1. 同步静态文件 ==="
for f in index.html style.css app.js; do
  s="$SRC/mhc/static/$f"
  d="$DST/mhc/static/$f"
  if [ -f "$s" ]; then
    cp -f "$s" "$d"
    printf '  %-14s %8d B  md5=%s\n' "$f" "$(stat -c%s "$d")" "$(md5sum "$d" | cut -c1-12)"
  else
    echo "  !! 缺失 $s"
  fi
done

echo
echo "=== 2. 同步 python 源码（如有变化） ==="
for f in "$SRC"/mhc/*.py "$SRC"/serve.py; do
  [ -f "$f" ] || continue
  base=$(basename "$f")
  if [ "$base" = "serve.py" ]; then
    cp -f "$f" "$DST/serve.py"
  else
    cp -f "$f" "$DST/mhc/$base"
  fi
done
find "$DST" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
echo "  已同步"

echo
echo "=== 3. 语法检查 ==="
"$DST/venv/bin/python" -m py_compile "$DST"/mhc/*.py "$DST"/serve.py && echo "  OK"

echo
echo "=== 4. 重启后端 ==="
bash "$DST/host/start_backend.sh" restart
sleep 1
bash "$DST/host/start_backend.sh" status
