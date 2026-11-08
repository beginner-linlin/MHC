#!/usr/bin/env bash
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
export TMPDIR=$PAN/tmp
W=/tmp/ctx_dbg2; rm -rf "$W"; mkdir -p "$W"

echo "############ direct -p -context on synthetic input (tail of output) ############"
printf 'SLYNTVATL SQKRPSGSKYLA\n' > "$W/one.txt"
"$PAN/netMHCpan" -p -context -a HLA-A02:01 -f "$W/one.txt" > "$W/o.txt" 2>&1
echo "exit=$?"
tail -12 "$W/o.txt" | sed 's/^/  /'
echo

echo "############ direct -p -context on vendor first line ############"
head -1 "$PAN/test/test.pep_context" > "$W/vend1.txt"
cat "$W/vend1.txt" | sed 's/^/  /'
awk '{print $1, $2}' "$W/vend1.txt" > "$W/vend1b.txt"
"$PAN/netMHCpan" -p -context -a HLA-B07:09 -f "$W/vend1b.txt" > "$W/v.txt" 2>&1
echo "exit=$?"
tail -6 "$W/v.txt" | sed 's/^/  /'
echo

echo "############ direct -p -context on synthetic, WITHOUT measurement col ############"
printf 'SLYNTVATL SQKRPSGSKYLA\n' > "$W/one2.txt"
"$PAN/netMHCpan" -p -context -a HLA-A02:01 -f "$W/one2.txt" -t -1 > "$W/o2.txt" 2>&1
echo "exit=$?"
tail -6 "$W/o2.txt" | sed 's/^/  /'
