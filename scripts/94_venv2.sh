#!/usr/bin/env bash
# python3-venv package is needed; ensurepip missing.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
APP=/opt/bio/app
echo "############ install python3.12-venv ############"
timeout 300 apt-get install -y -q python3.12-venv 2>&1 | tail -4 | sed 's/^/  /'
echo
echo "############ recreate venv ############"
rm -rf "$APP/venv"
python3 -m venv "$APP/venv" 2>&1 | sed 's/^/  /'
"$APP/venv/bin/python" -V 2>&1 | sed 's/^/  /'
echo
echo "############ install deps ############"
"$APP/venv/bin/pip" install -q --upgrade pip 2>&1 | tail -3 | sed 's/^/  /'
timeout 300 "$APP/venv/bin/pip" install -q flask openpyxl 2>&1 | tail -8 | sed 's/^/  /'
echo
echo "############ verify ############"
"$APP/venv/bin/python" - <<'PY'
import flask, openpyxl, sqlite3, sys
print(f"  python    {sys.version.split()[0]}")
print(f"  flask     {flask.__version__}")
print(f"  openpyxl  {openpyxl.__version__}")
print(f"  sqlite3   {sqlite3.sqlite_version}")
PY
