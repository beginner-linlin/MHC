#!/usr/bin/env bash
# Capture the real CLI surface of the three tools (no guessing).
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
CHOP=/opt/bio/netchop-3.1
STAB=/opt/bio/netMHCstabpan-1.0

echo "################ netMHCpan: option list from a real run ################"
cd /tmp && printf 'SLYNTVATL\n' > /tmp/x.pep
"$PAN/netMHCpan" -a HLA-A02:01 -p /tmp/x.pep 2>&1 | grep -E '^#\s+\[-' | sed 's/^#//' | sed 's/  */ /g'
echo
echo "################ netMHCpan: available allele count ################"
"$PAN/netMHCpan" -listMHC 2>/dev/null | wc -l | sed 's/^/  total MHC entries: /'
"$PAN/netMHCpan" -listMHC 2>/dev/null | grep -c '^HLA-A' | sed 's/^/  HLA-A: /'
"$PAN/netMHCpan" -listMHC 2>/dev/null | grep -c '^HLA-B' | sed 's/^/  HLA-B: /'
"$PAN/netMHCpan" -listMHC 2>/dev/null | grep -c '^HLA-C' | sed 's/^/  HLA-C: /'
echo "  first 5 HLA-A entries:"
"$PAN/netMHCpan" -listMHC 2>/dev/null | grep '^HLA-A' | head -5 | sed 's/^/    /'
