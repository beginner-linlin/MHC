#!/usr/bin/env bash
# Show launcher scripts and readme heads so we know the expected install layout.
set -uo pipefail

for f in /opt/bio/netMHCpan-4.2/netMHCpan \
         /opt/bio/netMHCstabpan-1.0/netMHCstabpan \
         /opt/bio/netchop-3.1/netchop; do
    echo "############################################################"
    echo "## LAUNCHER: $f"
    echo "############################################################"
    cat "$f"
    echo
done
