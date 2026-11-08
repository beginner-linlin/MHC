#!/usr/bin/env bash
# Read the recorded command line from each expected .out, and the readme.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
echo "############ command line recorded in each expected .out ############"
for f in "$PAN"/test/*.out; do
    printf '%-32s %s\n' "$(basename "$f")" "$(head -1 "$f" | cut -c1-130)"
done
echo
echo "############ readme ############"
cat "$PAN/netMHCpan-4.2.readme"
