#!/usr/bin/env bash
# WORKAROUND TEST for the broken `-pmhc -context` mode.
# Split the peptide-context-MHC input by allele and run each group through the
# working `-p -context -a <allele>` path, then compare against the vendor .out.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/ctx_workaround
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp
cd "$T" || exit 1

echo "############ split test.pep_context_mhc by allele ############"
awk '{print $3}' test.pep_context_mhc | sort -u > "$W/alleles.txt"
cat "$W/alleles.txt" | sed 's/^/  /'
echo

: > "$W/combined.body"
for a in $(cat "$W/alleles.txt"); do
    # peptide context [mhc] -> peptide context
    awk -v al="$a" '$3==al {print $1, $2}' test.pep_context_mhc > "$W/in_$a.txt"
    n=$(wc -l < "$W/in_$a.txt")
    "$PAN/netMHCpan" -p -context -a "$a" -f "$W/in_$a.txt" > "$W/out_$a.txt" 2>&1
    echo "  $a : $n peptides -> $(grep -c 'PEPLIST' "$W/out_$a.txt" || echo 0) result rows"
    grep -v '^#' "$W/out_$a.txt" | grep -v '^[[:space:]]*$' | grep -vE '^-+$' | grep -v 'Number of' >> "$W/combined.body"
done
echo

echo "############ rows produced by the workaround ############"
head -12 "$W/combined.body"
echo

echo "############ compare against vendor expected (row set, sorted) ############"
norm() { grep -v '^#' "$1" | grep -v '^[[:space:]]*$' | grep -vE '^-+$' | grep -v 'Number of' \
        | awk '{print $1, $2, $3, $(NF-3), $(NF-2)}' | sed 's/HLA-\([ABC]\)\*\([0-9]*\):\([0-9]*\)/HLA-\1\2:\3/' | sort; }
norm test.pep_context_mhc.out > "$W/exp.norm"
norm "$W/combined.body" > "$W/got.norm"
echo "expected rows: $(wc -l < "$W/exp.norm")   produced rows: $(wc -l < "$W/got.norm")"
echo
echo "--- side-by-side (peptide/mhc/score/rank) ---"
paste -d'|' <(head -10 "$W/exp.norm") <(head -10 "$W/got.norm") | sed 's/^/  /'
