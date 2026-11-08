#!/usr/bin/env bash
# Who prints "Cannot allocate fmatrix"? And what does the real -pmhc tmpdir
# contain at the moment of failure?
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/pmhc_who
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp

echo "############ which binary contains the error strings ############"
for b in "$PAN/Linux_x86_64/bin/"*; do
    [ -f "$b" ] || continue
    hits=$(grep -aoE 'Cannot allocate fmatrix|Wrong line format|PRDLIST_READ' "$b" 2>/dev/null | sort -u | tr '\n' ' ')
    [ -n "$hits" ] && echo "  $(basename "$b"): $hits"
done
echo

echo "############ real -dirty -pmhc run, then inspect the tmpdir ############"
"$PAN/netMHCpan" -pmhc "$T/test.pep_mhc" -dirty -tdir "$W/d_XXXXXX" > "$W/out.txt" 2>&1
echo "exit=$?"
tail -3 "$W/out.txt"
D=$(grep -oE 'Tmpdir made [^ ]+' "$W/out.txt" | awk '{print $3}')
echo "tmpdir = $D"
echo
echo "--- contents ---"
ls -la "$D" 2>/dev/null
for f in "$D"/*; do
    [ -f "$f" ] || continue
    echo "=== $(basename "$f")  ($(wc -c < "$f") bytes, $(wc -l < "$f") lines)"
    head -3 "$f"
    echo "  ..."
done
