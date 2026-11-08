#!/usr/bin/env bash
# Determine which package data.tar.gz belongs to.
set -uo pipefail
cd /opt/bio/src
mkdir -p /opt/bio/src/data_x
tar -xzf data.tar.gz -C /opt/bio/src/data_x
echo "=== data.tar.gz top structure ==="
find /opt/bio/src/data_x -maxdepth 2 | head -20
echo
echo "=== total files ==="
find /opt/bio/src/data_x -type f | wc -l
echo
echo "=== size ==="
du -sh /opt/bio/src/data_x
echo
echo "=== file listing (non-threshold) ==="
find /opt/bio/src/data_x -type f ! -path '*/threshold/*' -printf '%s\t%p\n' | sort -rn | head -20
echo
echo "=== threshold count ==="
find /opt/bio/src/data_x -path '*/threshold/*' -type f | wc -l
echo
echo "=== compare with netMHCpan-4.2/data/threshold ==="
ls /opt/bio/netMHCpan-4.2/data/threshold | head -5
ls /opt/bio/netMHCpan-4.2/data/threshold | wc -l
echo
echo "=== netMHCstabpan expected data files (from binary strings) ==="
strings /opt/bio/netMHCstabpan-1.0/Linux_x86_64/bin/netMHCstabpan 2>/dev/null | grep -iE 'threshold|matrices|\.bin|\.dat|synlist' | head -20
