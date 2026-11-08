#!/usr/bin/env bash
set -uo pipefail
echo "############ /opt/bio tree (depth 2) ############"
ls -la /opt/bio
echo
echo "############ /opt/bio/compat ############"
if [ -d /opt/bio/compat ]; then
    ls -la /opt/bio/compat
else
    echo "  NOT PRESENT"
fi
echo
for f in /opt/bio/netMHCpan-4.2/netMHCpan /opt/bio/netchop-3.1/netchop /opt/bio/netMHCstabpan-1.0/netMHCstabpan; do
    echo "############ $f ############"
    cat -A "$f" 2>/dev/null | sed 's/\$$//' | head -60
    echo
done
