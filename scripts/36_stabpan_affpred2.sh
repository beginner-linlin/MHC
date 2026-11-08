#!/usr/bin/env bash
# netMHCstabpan -ia with env vars set as the launcher would set them.
set -uo pipefail
STAB=/opt/bio/netMHCstabpan-1.0
cd "$STAB/test" || exit 1

export NETMHCstabpan="$STAB/Linux_x86_64"
export TMPDIR="$STAB/tmp"

echo "=== baseline: -ia WITHOUT -affpred (what the launcher currently produces) ==="
"$STAB/Linux_x86_64/bin/netMHCstabpan" -ia -p test.pep 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -4
echo

echo "=== -ia -affpred -> netMHCpan-4.2 ==="
"$STAB/Linux_x86_64/bin/netMHCstabpan" -ia -p test.pep -affpred /opt/bio/netMHCpan-4.2/netMHCpan 2>&1 \
  | grep -v '^#' | grep -v '^[[:space:]]*$' | head -8
