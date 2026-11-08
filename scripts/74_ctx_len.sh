#!/usr/bin/env bash
# Determine the accepted context length for -p -context mode.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
export TMPDIR=$PAN/tmp
W=/tmp/ctx_len; rm -rf "$W"; mkdir -p "$W"

echo "############ context length scan (peptide SLYNTVATL, 9 aa) ############"
printf '  %-8s %-30s %s\n' "ctxlen" "context" "result"
for n in 9 10 11 12 13 14 15 16 18 20; do
    # build a context of exactly n residues centred on the peptide
    pad=$(( (n - 9) / 2 )); [ $pad -lt 0 ] && pad=0
    left=$(printf 'A%.0s' $(seq 1 $pad))
    right=$(printf 'A%.0s' $(seq 1 $((n - 9 - pad))))
    ctx="${left}SLYNTVATL${right}"
    printf 'SLYNTVATL %s\n' "$ctx" > "$W/in.txt"
    "$PAN/netMHCpan" -p -context -a HLA-A02:01 -f "$W/in.txt" > "$W/o.txt" 2>&1
    rc=$?
    rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/o.txt")
    err=$(grep -m1 -iE 'Error|Wrong|expected' "$W/o.txt" | cut -c1-60)
    printf '  %-8s %-30s rc=%s rows=%s %s\n' "$n" "$ctx" "$rc" "$rows" "$err"
done
echo

echo "############ vendor context lengths ############"
awk '{print length($2)}' "$PAN/test/test.pep_context" | sort -u | sed 's/^/  ctx len = /'
awk '{print length($1)}' "$PAN/test/test.pep_context" | sort -u | sed 's/^/  pep len = /'
