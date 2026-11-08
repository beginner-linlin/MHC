#!/usr/bin/env bash
# netChop option surface + a real multi-length demo; plus output-format samples
# for all three tools so the guide can annotate real columns.
set -uo pipefail
CHOP=/opt/bio/netchop-3.1
PAN=/opt/bio/netMHCpan-4.2
STAB=/opt/bio/netMHCstabpan-1.0
W=/tmp/usage; rm -rf "$W"; mkdir -p "$W"

echo "################ netChop binary strings: options ################"
strings -a "$CHOP/Linux_x86_64/bin/netChop" | grep -E '^-[a-zA-Z]+$|^-p[0-9]' | sort -u | head -30 | sed 's/^/  /'
echo
echo "################ netChop: three prediction methods ################"
cat > "$W/p.fsa" <<'EOF'
>test_protein
MLLSVPLLLGLLGLAVGQCSVSWQPPPEKLLSEEDL
EOF
for opt in "-method cterm" "-method 20s" "-method both" ""; do
    TMPDIR=$CHOP/tmp "$CHOP/netchop" $opt "$W/p.fsa" > "$W/o.txt" 2>&1
    rc=$?
    rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+[A-Z]' "$W/o.txt")
    echo "  netchop $opt -> exit=$rc rows=$rows"
done
echo
echo "################ netChop default output columns ################"
TMPDIR=$CHOP/tmp "$CHOP/netchop" "$W/p.fsa" > "$W/chop.out" 2>&1
grep -E '^#' "$W/chop.out" | tail -12 | sed 's/^/  /'
echo "  --- data rows ---"
grep -E '^[[:space:]]*[0-9]+[[:space:]]+[A-Z]' "$W/chop.out" | head -8 | sed 's/^/  /'
echo
echo "################ netMHCpan output header columns ################"
printf 'SLYNTVATL\nGILGFVFTL\n' > "$W/x.pep"
"$PAN/netMHCpan" -a HLA-A02:01 -p "$W/x.pep" -BA > "$W/pan.out" 2>&1
grep -E '^ *Pos|^#\s+Pos' "$W/pan.out" | sed 's/^/  /'
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan.out" | sed 's/^/  /'
echo
echo "################ netMHCstabpan output header ################"
"$STAB/netMHCstabpan" -ia -a HLA-A02:01 -p "$W/x.pep" > "$W/stab.out" 2>&1
grep -E '^ *pos|^ *Pos' "$W/stab.out" | sed 's/^/  /'
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/stab.out" | sed 's/^/  /'
