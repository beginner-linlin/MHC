#!/bin/bash
for d in /opt/bio/netchop-3.1 /opt/bio/netMHCpan-4.2 /opt/bio/netMHCstabpan-1.0; do
  echo "--- $d"
  find "$d" -maxdepth 3 -iname '*version*' 2>/dev/null
  echo "  data/ 前 8 项:"
  ls "$d/data" 2>/dev/null | head -8 | sed 's/^/    /'
done
