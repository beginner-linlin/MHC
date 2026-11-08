#!/usr/bin/env bash
set -uo pipefail
CHOP=/opt/bio/netchop-3.1
PAN=/opt/bio/netMHCpan-4.2
W=/tmp/usage2; rm -rf "$W"; mkdir -p "$W"
cat > "$W/p.fsa" <<'EOF'
>test_protein
MLLSVPLLLGLLGLAVGQCSVSWQPPPEKLLSEEDL
EOF

echo "################ netChop: model switch -v 0 / -v 1 (NOT -method) ################"
for v in 0 1; do
    TMPDIR=$CHOP/tmp "$CHOP/netchop" -v $v "$W/p.fsa" > "$W/v$v.out" 2>&1
    echo "  -v $v -> exit=$? rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+[A-Z]' "$W/v$v.out")"
done
echo
echo "################ netChop: short format -s ################"
TMPDIR=$CHOP/tmp "$CHOP/netchop" -s "$W/p.fsa" > "$W/s.out" 2>&1
echo "  -s rows=$(grep -cE '^[[:space:]]*[0-9]+' "$W/s.out")"
grep -vE '^#' "$W/s.out" | grep -E '^[[:space:]]*[0-9]+' | head -6 | sed 's/^/    /'
echo
echo "################ netChop: threshold -t 0.9 ################"
TMPDIR=$CHOP/tmp "$CHOP/netchop" -t 0.9 "$W/p.fsa" > "$W/t.out" 2>&1
echo "  -t 0.9 -> cleavage sites (S): $(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+[A-Z][[:space:]]+S' "$W/t.out")"
echo
echo "################ pipeline demo: netChop 'S' sites -> netMHCpan ################"
echo "  (extract 9mers ending at strong cleavage sites, feed to netMHCpan)"
python3 - "$W/p.fsa" > "$W/pep.txt" <<'PY'
import sys
seq = ''.join(l.strip() for l in open(sys.argv[1]) if not l.startswith('>'))
for i in range(len(seq) - 8):
    print(seq[i:i+9])
PY
wc -l < "$W/pep.txt" | sed 's/^/  9mers generated: /'
"$PAN/netMHCpan" -a HLA-A02:01 -p "$W/pep.txt" > "$W/pipe.out" 2>&1
echo "  netMHCpan binders (<=WB): $(grep -cE '<= (SB|WB)' "$W/pipe.out")"
grep -E '<= (SB|WB)' "$W/pipe.out" | awk '{printf "    %-12s Score_EL=%-9s %%Rank=%-7s %s\n", $(NF-5), $(NF-4), $(NF-3), $(NF-1)" "$NF}' | head -5
