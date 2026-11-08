#!/usr/bin/env bash
# Correct, name-aligned verification of stabpan -ia.
set -uo pipefail
STAB=/opt/bio/netMHCstabpan-1.0
W=/tmp/ia_final; rm -rf "$W"; mkdir -p "$W"
export TMPDIR="$STAB/tmp"
cd "$STAB/test" || exit 1

"$STAB/netMHCstabpan" -ia -p test.pep > "$W/ia.out" 2>&1

echo "############ name-aligned column map ############"
hdr=$(grep -m1 -E '^ pos|^pos' "$W/ia.out")
echo "  HEADER: $hdr"
echo
python3 - "$W/ia.out" <<'PY'
import sys, re
lines = open(sys.argv[1]).read().splitlines()
hdr = next(l for l in lines if l.strip().startswith('pos') or l.strip().startswith('Pos'))
cols = hdr.split()
rows = [l.split() for l in lines if re.match(r'^\s*\d+\s+HLA', l)]
print("  columns:", len(cols))
print("  data rows:", len(rows))
print()
# BindLevel is the trailing column only when present
want = ['peptide','Pred','Thalf(h)','%Rank_Stab','1-log50k','Aff(nM)','%Rank_aff','Combined','Combined_%rank']
idx = {c: i for i, c in enumerate(cols)}
print("  " + "".join(f"{c:>13}" for c in want))
for r in rows[:5]:
    print("  " + "".join(f"{r[idx[c]]:>13}" for c in want))
print()
missing = [c for c in want if c not in idx]
print("  missing columns:", missing or "none")
empty = [c for c in want if any(len(r) <= idx[c] for r in rows)]
print("  truncated rows:", empty or "none")
PY
echo

echo "############ base columns vs test.pep.out (pos..Exp_stab = 8 fields) ############"
base8() { grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$1" | awk '{for(i=1;i<=8;i++) printf "%s%s", $i, (i<8?" ":"\n")}' | sort; }
base8 "$W/ia.out" | md5sum | sed 's/^/  ia  first8 md5: /'
base8 test.pep.out | md5sum | sed 's/^/  ref first8 md5: /'
if diff -q <(base8 "$W/ia.out") <(base8 test.pep.out) >/dev/null; then
    echo "  PASS  base stability columns identical to test.pep.out"
else
    echo "  differences:"; diff <(base8 test.pep.out) <(base8 "$W/ia.out") | head -6 | sed 's/^/    /'
fi
