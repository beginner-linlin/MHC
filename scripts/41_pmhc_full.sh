#!/usr/bin/env bash
# Full, unfiltered output of a -pmhc run, plus which child processes run and
# what files they touch. Goal: find who prints "Cannot allocate fmatrix".
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/pmhc_full
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp

echo "############ expected output shipped by the vendor ############"
cat "$T/test.pep_mhc.out" 2>/dev/null | head -20 || echo "(no .out shipped)"
echo

echo "############ FULL stdout of -pmhc test.pep_mhc ############"
"$PAN/netMHCpan" -pmhc "$T/test.pep_mhc" > "$W/out.txt" 2> "$W/err.txt"
echo "exit=$?"
echo "--- stdout (all) ---"
cat "$W/out.txt"
echo "--- stderr (all) ---"
cat "$W/err.txt"
echo

echo "############ which binaries are exec'd during -pmhc ############"
strace -f -e trace=execve -s 200 "$PAN/netMHCpan" -pmhc "$T/test.pep_mhc" 2>&1 \
  | grep 'execve(' | grep -v ENOENT | sed 's/, \[.*//' | sed 's/^[0-9]* *//' | sort -u
