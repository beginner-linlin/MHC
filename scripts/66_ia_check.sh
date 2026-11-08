#!/usr/bin/env bash
# Correct check for stabpan -ia: its base columns must equal test.pep.out,
# and the 5 affinity columns must be present with numeric values.
set -uo pipefail
STAB=/opt/bio/netMHCstabpan-1.0
W=/tmp/ia_check; rm -rf "$W"; mkdir -p "$W"
export TMPDIR="$STAB/tmp"
cd "$STAB/test" || exit 1

"$STAB/netMHCstabpan" -ia -p test.pep > "$W/ia.out" 2>&1
echo "exit=$?"
echo

echo "############ -ia output (data rows) ############"
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/ia.out" | head -12
echo

echo "############ header of the -ia table ############"
grep -m1 -E 'pos|Pos' "$W/ia.out"
echo

echo "############ column-count check ############"
awk '/^[[:space:]]*[0-9]+[[:space:]]+HLA/{print NF}' "$W/ia.out" | sort -u | sed 's/^/  NF = /'
echo

echo "############ base columns vs test.pep.out (first 10 fields) ############"
base() { grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$1" | awk '{for(i=1;i<=10;i++) printf "%s%s", $i, (i<10?" ":"\n")}'; }
base "$W/ia.out"   | sort > "$W/ia_base.txt"
base test.pep.out  | sort > "$W/exp_base.txt"
if diff -q "$W/exp_base.txt" "$W/ia_base.txt" >/dev/null 2>&1; then
    echo "  PASS  base prediction columns identical to test.pep.out"
else
    echo "  diff:"; diff "$W/exp_base.txt" "$W/ia_base.txt" | head -8 | sed 's/^/    /'
fi
echo

echo "############ affinity columns (1-log50k / Aff / %Rank_aff / Combined / Combined_%rank) ############"
awk '/^[[:space:]]*[0-9]+[[:space:]]+HLA/{
    n=NF;
    printf "  %-12s %-10s  1-log50k=%-8s Aff(nM)=%-10s %%Rank_aff=%-8s Combined=%-8s Cmb_%%rank=%-8s %s\n",
        $2,$3,$(n-5),$(n-4),$(n-3),$(n-2),$(n-1),$n
}' "$W/ia.out"
echo

echo "############ error scan ############"
if grep -qiE 'not found|Error\.|cannot' "$W/ia.out"; then
    grep -inE 'not found|Error\.|cannot' "$W/ia.out" | head | sed 's/^/  /'
else
    echo "  no errors"
fi
echo

echo "############ affpred line actually used ############"
grep -m1 -E '^-affpred|affpred' "$W/ia.out" | sed 's/^/  /'
