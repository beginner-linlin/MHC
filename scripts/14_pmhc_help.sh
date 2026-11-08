#!/usr/bin/env bash
set -uo pipefail
cd /opt/bio/netMHCpan-4.2/test || exit 1
echo "=== man: -pmhc ==="
grep -n -A6 -B2 'pmhc' ../netMHCpan.1 | head -60
echo
echo "=== help output (-h) grep pmhc ==="
../netMHCpan -h 2>&1 | grep -i -A3 -B3 'pmhc' | head -40
