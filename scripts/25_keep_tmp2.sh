#!/usr/bin/env bash
# -tdir takes an mkdtemp TEMPLATE (path ending in XXXXXX).
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
DATA=/opt/bio/netMHCpan-4.2/Linux_x86_64/data
rm -rf /tmp/keep && mkdir -p /tmp/keep && cd /tmp/keep || exit 1

echo "############ -p with -dirty (template tdir) ############"
printf 'SLYNTVATL 0.5\n' > good.pep
/opt/bio/netMHCpan-4.2/netMHCpan -p good.pep -dirty -tdir '/tmp/keep/tp_XXXXXX' 2>&1 \
  | grep -v '^#' | grep -v '^[[:space:]]*$' | head -4
echo "--- tmpdir contents ---"
find /tmp/keep -maxdepth 2 -type f -printf '%s\t%p\n' 2>/dev/null | sort -rn | head -20

echo
echo "############ -pmhc with -dirty (template tdir) ############"
printf 'SLYNTVATL HLA-A02:01 0.5\n' > bad.pmhc
/opt/bio/netMHCpan-4.2/netMHCpan -pmhc bad.pmhc -dirty -tdir '/tmp/keep/tm_XXXXXX' 2>&1 \
  | grep -v '^#' | grep -v '^[[:space:]]*$' | head -4
echo "--- tmpdir contents ---"
find /tmp/keep -maxdepth 2 -type f -printf '%s\t%p\n' 2>/dev/null | sort -rn | head -20
