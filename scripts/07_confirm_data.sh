#!/usr/bin/env bash
# Confirm data.tar.gz ownership and inspect versions.
set -uo pipefail

echo "=== data_x/data/version ==="
cat /opt/bio/src/data_x/data/version; echo
echo "=== netMHCpan-4.2/data/version ==="
cat /opt/bio/netMHCpan-4.2/data/version; echo
echo
echo "=== data_x threshold sample names ==="
ls /opt/bio/src/data_x/data/threshold | head -5
echo
echo "=== data_x data tree ==="
ls -la /opt/bio/src/data_x/data
echo
echo "=== netMHCstabpan readme: INSTALLATION section ==="
sed -n '/INSTALLATION/,/Enjoy/p' /opt/bio/netMHCstabpan-1.0/netMHCstabpan-1.0.readme
