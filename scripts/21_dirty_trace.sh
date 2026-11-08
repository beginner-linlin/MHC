#!/usr/bin/env bash
# Keep the tmp dir (-dirty) to see the intermediate files the helper produced.
set -uo pipefail
rm -rf /tmp/pmhc_trace && mkdir -p /tmp/pmhc_trace && cd /tmp/pmhc_trace || exit 1

echo "################ -p (works) ################"
printf 'SLYNTVATL 0.5\n' > good.pep
/opt/bio/netMHCpan-4.2/netMHCpan -p good.pep -dirty -tdir /tmp/pmhc_trace/t1 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -5
echo "--- files ---"
find /tmp/pmhc_trace/t1 -type f -printf '%s\t%p\n' 2>/dev/null | sort -rn | head -20

echo
echo "################ -pmhc (fails) ################"
printf 'SLYNTVATL HLA-A02:01 0.5\n' > bad.pmhc
/opt/bio/netMHCpan-4.2/netMHCpan -pmhc bad.pmhc -dirty -tdir /tmp/pmhc_trace/t2 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -5
echo "--- files ---"
find /tmp/pmhc_trace/t2 -type f -printf '%s\t%p\n' 2>/dev/null | sort -rn | head -20

echo
echo "################ child processes spawned ################"
strace -f -e trace=execve -s 400 /opt/bio/netMHCpan-4.2/netMHCpan -pmhc bad.pmhc 2>&1 | grep execve | head -20
