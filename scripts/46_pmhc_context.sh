#!/usr/bin/env bash
# The context+pmhc path reports a DIFFERENT error: a PRDLIST_READ format
# mismatch on the raw 0.dat line. Find which nnalign variant it uses.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
BIN=$PAN/Linux_x86_64/bin
T=$PAN/test
W=/tmp/pmhc_ctx
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp

echo "############ binaries exec'd during -pmhc -context ############"
strace -f -e trace=execve -s 200 "$PAN/netMHCpan" -pmhc -context "$T/test.pep_context_mhc" 2>&1 \
  | grep 'execve(' | grep -v ENOENT | grep -E 'nnalign|netMHCpan-4.2"' \
  | sed -E 's/, \[.*//' | sed -E 's/^[0-9]* +//' | sort -u

echo
echo "############ the -p -context path, for comparison ############"
strace -f -e trace=execve -s 200 "$PAN/netMHCpan" -p -context "$T/test.pep_context" 2>&1 \
  | grep 'execve(' | grep -v ENOENT | grep -E 'nnalign' \
  | sed -E 's/, \[.*//' | sed -E 's/^[0-9]* +//' | sort -u

echo
echo "############ tmpdir of a -dirty -pmhc -context run ############"
"$PAN/netMHCpan" -pmhc -context "$T/test.pep_context_mhc" -dirty -tdir "$W/d_XXXXXX" > "$W/out.txt" 2>&1
tail -2 "$W/out.txt"
D=$(grep -oE 'Tmpdir made [^ ]+' "$W/out.txt" | awk '{print $3}')
echo "tmpdir = $D"
for f in "$D"/*; do
    [ -f "$f" ] || continue
    echo "=== $(basename "$f") ($(wc -l < "$f") lines)"
    head -2 "$f" | cut -c1-160 | sed 's/^/    /'
done
