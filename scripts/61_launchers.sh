#!/usr/bin/env bash
# Verify launcher names + config, then run the complete vendor regression suite.
set -uo pipefail
BASE=/opt/bio
PAN=$BASE/netMHCpan-4.2
CHOP=$BASE/netchop-3.1
STAB=$BASE/netMHCstabpan-1.0
hr() { printf '%s\n' "============================================================"; }

hr; echo "LAUNCHER FILES"; hr
for d in "$PAN" "$CHOP" "$STAB"; do
    echo "  --- $d ---"
    find "$d" -maxdepth 1 -type f -name 'net*' -printf '    %f  %s B  %m\n' 2>/dev/null
done
echo
hr; echo "CONFIG (NMHOME / TMPDIR)"; hr
for f in "$PAN/netMHCpan" "$CHOP/netchop" "$STAB/netMHCstabpan"; do
    echo "  --- $(basename "$f") ---"
    grep -nE 'set[[:space:]]+(NMHOME|TMPDIR|NetMHCpan)' "$f" 2>/dev/null | sed 's/^/    /'
done
echo
hr; echo "SHEBANG"; hr
for f in "$PAN/netMHCpan" "$CHOP/netchop" "$STAB/netMHCstabpan"; do
    printf '  %-14s %s\n' "$(basename "$f")" "$(head -1 "$f")"
done
