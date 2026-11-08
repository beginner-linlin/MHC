#!/usr/bin/env bash
# dpkg was interrupted by the timeout on a previous apt run. Repair, then venv.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive
APP=/opt/bio/app
echo "############ dpkg --configure -a ############"
timeout 300 dpkg --configure -a 2>&1 | tail -10 | sed 's/^/  /'
echo "  exit=$?"
echo
echo "############ apt fix-broken ############"
timeout 300 apt-get install -y -q -f 2>&1 | tail -5 | sed 's/^/  /'
echo
echo "############ python3.12-venv ############"
timeout 300 apt-get install -y -q python3.12-venv 2>&1 | tail -5 | sed 's/^/  /'
echo
echo "############ venv ############"
rm -rf "$APP/venv"
python3 -m venv "$APP/venv" 2>&1 | sed 's/^/  /'
if [ -x "$APP/venv/bin/pip" ]; then
  echo "  pip present"
  timeout 300 "$APP/venv/bin/pip" install -q flask openpyxl 2>&1 | tail -6 | sed 's/^/  /'
  "$APP/venv/bin/python" -c "import flask,openpyxl,sys;print('  python',sys.version.split()[0]);print('  flask',flask.__version__);print('  openpyxl',openpyxl.__version__)"
else
  echo "  pip STILL MISSING"
fi
