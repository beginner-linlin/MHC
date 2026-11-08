#!/usr/bin/env bash
# Install backend deps inside WSL.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
echo "############ pip install flask + openpyxl ############"
timeout 300 python3 -m pip install --break-system-packages -q flask openpyxl 2>&1 | tail -8 | sed 's/^/  /'
echo "  exit=$?"
echo
echo "############ verify ############"
python3 - <<'PY'
import flask, openpyxl, sqlite3, sys
print(f"  flask     {flask.__version__}")
print(f"  openpyxl  {openpyxl.__version__}")
print(f"  sqlite3   {sqlite3.sqlite_version}")
print(f"  python    {sys.version.split()[0]}")
PY
