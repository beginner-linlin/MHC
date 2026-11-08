#!/usr/bin/env bash
# Clean numeric verification of the -pmhc -context workaround:
#   -p -context -a <allele>  per allele  ==  expected -pmhc -context output
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/ctx_verify
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp
cd "$T" || exit 1

# Extract (mhc, peptide, Score_EL, %Rank_EL) from a results table.
# Data rows start with a number in column 1 and contain 'PEPLIST'.
extract() {
    awk '$1 ~ /^[0-9]+$/ && /PEPLIST/ {
        mhc=""; score=""; rank="";
        for (i=1;i<=NF;i++) {
            if ($i ~ /^HLA-/) { mhc=$i; peptide=$(i+1) }
            if ($i=="PEPLIST") { score=$(i+1); rank=$(i+2) }
        }
        gsub(/\*/,"",mhc);
        printf "%s %s %s %s\n", mhc, peptide, score, rank
    }' "$1"
}

extract test.pep_context_mhc.out | sort > "$W/expected.txt"

: > "$W/raw.txt"
for a in $(awk '{print $3}' test.pep_context_mhc | sort -u); do
    awk -v al="$a" '$3==al {print $1, $2}' test.pep_context_mhc > "$W/in_$a.txt"
    "$PAN/netMHCpan" -p -context -a "$a" -f "$W/in_$a.txt" > "$W/out_$a.txt" 2>&1
    extract "$W/out_$a.txt" >> "$W/raw.txt"
done
sort "$W/raw.txt" > "$W/got.txt"

echo "expected rows: $(wc -l < "$W/expected.txt")    produced rows: $(wc -l < "$W/got.txt")"
echo
echo "############ exact comparison ############"
if diff -u "$W/expected.txt" "$W/got.txt" > "$W/diff.txt"; then
    echo "PASS  workaround reproduces the expected -pmhc -context results exactly"
    echo
    column -t "$W/got.txt" | sed 's/^/  /'
else
    echo "differences:"
    cat "$W/diff.txt"
fi
