#!/usr/bin/env bash
# Survey the stabpan test dir and the expected -ia outputs.
set -uo pipefail
STAB=/opt/bio/netMHCstabpan-1.0
echo "############ stabpan test dir ############"
ls -la "$STAB/test" | sed 's/^/  /'
echo
echo "############ readme test section ############"
grep -n -A 25 -i 'test the software' "$STAB/netMHCstabpan.readme" 2>/dev/null | sed 's/^/  /' \
  || grep -n -i -A 20 'test' "$STAB"/*.readme | head -60
echo
echo "############ any expected -ia output? ############"
for f in "$STAB"/test/*.out; do
    echo "--- $(basename "$f") ---"
    head -1 "$f"
    grep -m1 -E '^ *Pos|Peptide' "$f"
    grep -m1 'PEPLIST' "$f"
    echo
done
