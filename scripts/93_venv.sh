#!/usr/bin/env bash
# Use a clean venv instead of fighting Debian-managed packages.
set -uo pipefail
APP=/opt/bio/app
mkdir -p "$APP"
echo "############ venv ############"
if ! python3 -c "import venv" 2>/dev/null; then
  echo "  installing python3-venv..."
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv 2>&1 | tail -3 | sed 's/^/  /'
fi
rm -rf "$APP/venv"
python3 -m venv "$APP/venv" 2>&1 | sed 's/^/  /'
echo "  created: $APP/venv"
echo
echo "############ install deps inside venv ############"
"$APP/venv/bin/pip" install -q --upgrade pip 2>&1 | tail -3 | sed 's/^/  /'
timeout 300 "$APP/venv/bin/pip" install -q flask openpyxl 2>&1 | tail -8 | sed 's/^/  /'
echo "  pip exit=$?"
echo
echo "############ verify ############"
"$APP/venv/bin/python" - <<'PY'
import flask, openpyxl, sqlite3, sys
print(f"  python    {sys.version.split()[0]}")
print(f"  flask     {flask.__version__}")
print(f"  openpyxl  {openpyxl.__version__}")
print(f"  sqlite3   {sqlite3.sqlite_version}")
PY
