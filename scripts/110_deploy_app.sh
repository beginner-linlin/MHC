#!/bin/bash
# 语法检查 + 部署到 /opt/bio/app
set -u
SRC=/mnt/c/Users/86156/Desktop/大创/软件/mhc-app
DST=/opt/bio/app

echo "=== 1. 语法检查 ==="
cd "$SRC" || exit 1
/opt/bio/app/venv/bin/python -m py_compile \
  mhc/__init__.py mhc/runner.py mhc/jobs.py mhc/exporters.py mhc/pipeline.py mhc/web.py serve.py
echo "py_compile rc=$?"

echo
echo "=== 2. 静态检查（编译所有子模块）==="
/opt/bio/app/venv/bin/python - <<'PY'
import ast, pathlib, sys
root = pathlib.Path("/mnt/c/Users/86156/Desktop/大创/软件/mhc-app")
bad = 0
for p in sorted(root.rglob("*.py")):
    try:
        ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"SYNTAX ERROR {p}: {e}")
        bad += 1
print("files ok" if not bad else f"{bad} file(s) with errors")
PY

echo
echo "=== 3. 部署到 $DST ==="
mkdir -p "$DST"
rm -rf "$DST/mhc"
cp -r "$SRC/mhc" "$DST/mhc"
cp "$SRC/serve.py" "$DST/serve.py"
mkdir -p "$DST/host"
cp -r "$SRC/host/." "$DST/host/"
chmod +x "$DST/host/start_backend.sh" 2>/dev/null
# 清掉编译缓存
find "$DST/mhc" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
echo "deployed:"
find "$DST/mhc" -maxdepth 2 -type f | sort | sed 's|^|  |'
echo "  --- host/"
find "$DST/host" -maxdepth 1 -type f | sort | sed 's|^|  |'

echo
echo "=== 4. 导入测试 ==="
cd "$DST" || exit 1
MHC_APP_ROOT=/opt/bio/app /opt/bio/app/venv/bin/python - <<'PY'
import sys, traceback
sys.path.insert(0, "/opt/bio/app")
try:
    from mhc.web import app, store
    print("import mhc.web OK")
    print("routes:", len(list(app.url_map.iter_rules())))
    for r in sorted(app.url_map.iter_rules(), key=lambda x: str(x)):
        print(f"  {','.join(sorted(r.methods - {'HEAD','OPTIONS'})):12s} {r}")
except Exception:
    traceback.print_exc()
    sys.exit(1)
PY
echo "import rc=$?"

echo
echo "=== 5. 冒烟：健康检查 ==="
MHC_APP_ROOT=/opt/bio/app /opt/bio/app/venv/bin/python - <<'PY'
import sys, json
sys.path.insert(0, "/opt/bio/app")
from mhc.web import app
c = app.test_client()
for path in ["/api/health", "/api/presets", "/api/alleles?q=A02"]:
    r = c.get(path)
    body = r.get_data(as_text=True)
    print(f"{path} -> {r.status_code} ({len(body)} bytes)")
    if path == "/api/health":
        print("   ", body[:400])
    if path == "/api/alleles?q=A02":
        print("   ", body[:200])
PY
