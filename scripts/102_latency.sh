#!/usr/bin/env bash
# The app's Windows Node process will call WSL per-request. Measure spawn overhead.
set -uo pipefail
echo "  wsl spawn latency test: 5 sequential calls"
for i in 1 2 3 4 5; do
  s=$(date +%s%N)
  out=$(netMHCpan -p /tmp/fmt/one.pep -a HLA-A02:01 2>/dev/null | grep -c 'HLA-A\*')
  e=$(date +%s%N)
  echo "    run $i: $(( (e-s)/1000000 ))ms rows=$out"
done
echo
echo "  python import overhead (venv):"
s=$(date +%s%N); /opt/bio/app/venv/bin/python -c "pass"; e=$(date +%s%N)
echo "    bare import: $(( (e-s)/1000000 ))ms"
