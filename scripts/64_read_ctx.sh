#!/usr/bin/env bash
set -uo pipefail
echo "############ /usr/local/bin/netMHCpan_ctx ############"
cat /usr/local/bin/netMHCpan_ctx 2>/dev/null || echo "  NOT PRESENT"
echo
echo "############ /usr/local/bin listing (net* tools) ############"
ls -la /usr/local/bin 2>/dev/null | grep -iE 'net|mhc|chop' || echo "  none"
echo
echo "############ PATH entry check ############"
for t in netMHCpan netchop netMHCstabpan netMHCpan_ctx; do
    printf '  %-16s -> %s\n' "$t" "$(command -v "$t" 2>/dev/null || echo 'not in PATH')"
done
