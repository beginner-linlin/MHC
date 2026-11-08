#!/usr/bin/env bash
# netMHCstabpan: inspect what -affpred expects and how the launcher wires NetMHCpan.
set -uo pipefail
STAB=/opt/bio/netMHCstabpan-1.0
echo "=== test/comm (the vendor test command list) ==="
cat "$STAB/test/comm"
echo
echo "=== strings: affpred / NetMHCpan usage ==="
strings -a "$STAB/Linux_x86_64/bin/netMHCstabpan" | grep -iE 'affpred|netmhcpan|NMHOME|env' | head -20
