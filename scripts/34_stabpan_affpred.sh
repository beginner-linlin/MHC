#!/usr/bin/env bash
# netMHCstabpan -ia needs an affinity predictor. Test whether netMHCpan-4.2
# can substitute for the missing NetMHCpan-2.8.
set -uo pipefail
STAB=/opt/bio/netMHCstabpan-1.0
cd "$STAB/test" || exit 1

echo "=== current launcher affpred wiring ==="
grep -n 'NetMHCpan' "$STAB/netMHCstabpan"

echo
echo "=== try: point -affpred at netMHCpan-4.2 ==="
"$STAB/Linux_x86_64/bin/netMHCstabpan" -ia -p test.pep \
  -affpred /opt/bio/netMHCpan-4.2/netMHCpan 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -12
echo "exit=$?"
