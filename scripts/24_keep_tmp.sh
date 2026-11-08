#!/usr/bin/env bash
# Use -dirty to keep the REAL tmpdir from a working -p run, then replay the
# failing -pmhc helper variant against those exact inputs.
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
DATA=/opt/bio/netMHCpan-4.2/Linux_x86_64/data
cd /tmp || exit 1
rm -rf /tmp/keep && mkdir -p /tmp/keep && cd /tmp/keep || exit 1

echo "############ -p with -dirty, explicit tdir ############"
printf 'SLYNTVATL 0.5\n' > good.pep
mkdir -p /tmp/keep/tp
TMPDIR=/tmp/keep/tp /opt/bio/netMHCpan-4.2/netMHCpan -p good.pep -dirty -tdir /tmp/keep/tp 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -4
echo "--- tmpdir contents ---"
find /tmp/keep/tp -maxdepth 2 -type f -printf '%s\t%p\n' 2>/dev/null | sort -rn | head -20
