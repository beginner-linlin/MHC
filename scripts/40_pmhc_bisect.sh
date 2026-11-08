#!/usr/bin/env bash
# Bisect the real test.pep_mhc to find which line(s) break -pmhc, and check
# every allele it names against the 4.2e pseudo-MHC table.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
DATA=$PAN/Linux_x86_64/data
T=$PAN/test
W=/tmp/pmhc_bisect
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp

echo "############ synlist / pseudo-MHC inventory ############"
ls -la "$DATA" | grep -iE 'synlist|MHC_pseudo|hla_pseudo' || echo "(none matched)"
echo
echo "MHC_pseudo.dat line count: $(wc -l < "$DATA/MHC_pseudo.dat" 2>/dev/null || echo MISSING)"
echo

echo "############ alleles named by test.pep_mhc, checked against MHC_pseudo.dat ############"
if [ -f "$DATA/MHC_pseudo.dat" ]; then
    awk '{print $2}' "$T/test.pep_mhc" | sort -u | while read -r a; do
        if grep -qE "(^|[[:space:]])$a([[:space:]]|$)" "$DATA/MHC_pseudo.dat"; then
            echo "  PRESENT  $a"
        else
            echo "  MISSING  $a   <-- not in MHC_pseudo.dat"
        fi
    done
else
    echo "MHC_pseudo.dat not found; skipping allele check"
fi
echo

echo "############ bisect: run -pmhc on each single line ############"
n=0
while IFS= read -r line; do
    [ -z "$line" ] && continue
    n=$((n+1))
    printf '%s\n' "$line" > "$W/one.pmhc"
    out=$("$PAN/netMHCpan" -pmhc "$W/one.pmhc" -dirty -tdir "$W/d_${n}_XXXXXX" 2>&1)
    rc=$?
    payload=$(echo "$out" | grep -v '^#' | grep -v '^[[:space:]]*$' | tail -1)
    err=$(echo "$out" | grep -iE 'error|wrong line|cannot' | head -1)
    if [ $rc -eq 0 ]; then
        echo "  line $n  OK    | $line"
        echo "                -> $payload"
    else
        echo "  line $n  FAIL  | $line"
        echo "                -> $err"
    fi
done < "$T/test.pep_mhc"
