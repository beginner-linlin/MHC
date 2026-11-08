#!/usr/bin/env bash
set -uo pipefail
cd /opt/bio/netMHCpan-4.2/test || exit 1
echo "=== test.pep_mhc ==="
cat -A test.pep_mhc | head -20
echo
echo "=== plain ==="
cat test.pep_mhc
echo
echo "=== test.pep_context_mhc ==="
cat test.pep_context_mhc
echo
echo "=== file info ==="
file test.pep_mhc test.pep_context_mhc test.pep
wc -l test.pep_mhc test.pep_context_mhc test.pep
