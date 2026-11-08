#!/usr/bin/env bash
# Probe what's available for building a GUI app around the three tools.
set -uo pipefail
echo "############ WSL python ############"
for p in python3 python3.12 python3.11 python pip3 pip; do
    printf '  %-12s %s\n' "$p" "$(command -v $p 2>/dev/null || echo '-')"
done
python3 -V 2>&1 | sed 's/^/  version: /'
echo
echo "############ python packages relevant to a web backend ############"
python3 - <<'PY' 2>&1 | sed 's/^/  /'
mods = ["flask","fastapi","uvicorn","jinja2","pandas","openpyxl","numpy","werkzeug","starlette"]
for m in mods:
    try:
        __import__(m); print(f"{m:12s} OK")
    except Exception as e:
        print(f"{m:12s} MISSING")
PY
echo
echo "############ pip availability / offline wheel cache ############"
python3 -m pip --version 2>&1 | sed 's/^/  /'
echo
echo "############ stdlib http.server (always available fallback) ############"
python3 -c "import http.server, socketserver, json, cgi; print('  stdlib http.server OK')" 2>&1
echo
echo "############ WSL network reachability from Windows side ############"
ip -4 addr show eth0 2>/dev/null | grep -oP 'inet \K[\d.]+' | sed 's/^/  WSL eth0 ip: /'
echo "  (WSL2 normally forwards localhost to Windows)"
echo
echo "############ the three tools respond ############"
for t in netMHCpan netchop netMHCstabpan netMHCpan_ctx; do
    printf '  %-16s %s\n' "$t" "$(command -v $t 2>/dev/null || echo MISSING)"
done
