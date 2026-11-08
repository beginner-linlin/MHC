#!/usr/bin/env bash
set -uo pipefail
CHOP=/opt/bio/netchop-3.1
STAB=/opt/bio/netMHCstabpan-1.0

echo "################ netChop: real options ################"
cd /tmp
printf '>x\nSLYNTVATLGILGFVFTL\n' > /tmp/x.fsa
TMPDIR=$CHOP/tmp "$CHOP/netchop" 2>&1 | head -40 | sed 's/^/  /'
echo
echo "################ netChop: run with no args shows usage? ################"
TMPDIR=$CHOP/tmp "$CHOP/netchop" 2>&1 | wc -l | sed 's/^/  lines: /'
echo
echo "################ netMHCstabpan: real options ################"
cd /tmp
"$STAB/netMHCstabpan" 2>&1 | head -45 | sed 's/^/  /'
