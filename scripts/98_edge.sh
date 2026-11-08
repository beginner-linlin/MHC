#!/usr/bin/env bash
# Edge cases that determine the app's input-validation rules.
set -uo pipefail
W=/tmp/edge; rm -rf $W; mkdir -p $W; cd $W

run() { # label, command...
  local label="$1"; shift
  echo "--- $label"
  out=$("$@" 2>&1)
  rc=$?
  data=$(printf '%s\n' "$out" | grep -v '^#' | grep -v '^-' | grep -v '^$' | grep -v '^Protein ' | grep -v '^NetChop' | grep -v '^HLA-' | head -3)
  echo "    rc=$rc"
  if [ -z "$data" ]; then
    echo "    (no data rows)"
    err=$(printf '%s\n' "$out" | grep -i -E 'error|wrong|cannot|not found|unable' | head -2)
    [ -n "$err" ] && echo "    ERR: $err"
  else
    printf '%s\n' "$data" | sed 's/^/    /'
  fi
}

echo "############ 1. mixed peptide lengths 8-14 in -p mode ############"
printf 'GILGFVFT\nGILGFVFTL\nGILGFVFTLT\nGILGFVFTLTV\nGILGFVFTLTVP\nGILGFVFTLTVPS\nGILGFVFTLTVPSE\n' > mix.pep
run "netMHCpan mixed 8-14" netMHCpan -p mix.pep -a HLA-A02:01 -BA
run "stabpan  mixed 8-14" netMHCstabpan -p mix.pep -a HLA-A02:01 -ia

echo
echo "############ 2. too-short / too-long peptides ############"
printf 'GILG\nGILGF\nGILGFVFTLTVPSERAAAAAAAAAAAA\n' > bad.pep
run "netMHCpan short4 /long26" netMHCpan -p bad.pep -a HLA-A02:01 -BA
run "stabpan  short4 /long26" netMHCstabpan -p bad.pep -a HLA-A02:01

echo
echo "############ 3. lowercase + non-standard letters ############"
printf 'gilgfvftl\nGILGFVFTX\nGILGBVFTL\nGILGFVFTU\n' > low.pep
run "netMHCpan lowercase+X/B/U" netMHCpan -p low.pep -a HLA-A02:01 -BA
printf '>low\nmllsvplllgllgaaacssncgss\n' > low.fsa
run "netMHCpan fasta lowercase" netMHCpan -f low.fsa -a HLA-A02:01 -BA
run "netchop  fasta lowercase" netchop low.fsa

echo
echo "############ 4. netchop multi-protein FASTA ############"
cat > multi.fsa <<'EOF'
>protA
MLLSVPLLLGLLGAAACSS
>protB
GILGFVFTLTVPSER
EOF
echo "--- netchop two proteins"
netchop multi.fsa 2>&1 | grep -E 'Protein name|^Number' | sed 's/^/    /'

echo
echo "############ 5. netMHCpan multi-protein fasta ############"
netMHCpan -f multi.fsa -a HLA-A02:01 2>&1 | grep -E '^Protein ' | sed 's/^/    /'

echo
echo "############ 6. empty input ############"
: > empty.pep
run "netMHCpan empty pep" netMHCpan -p empty.pep -a HLA-A02:01 -BA
run "stabpan  empty pep" netMHCstabpan -p empty.pep -a HLA-A02:01

echo
echo "############ 7. bad allele ############"
run "netMHCpan bogus allele" netMHCpan -p mix.pep -a HLA-Q99:99
run "stabpan  bogus allele" netMHCstabpan -p mix.pep -a HLA-Q99:99

echo
echo "############ 8. allele with asterisk vs without vs 4-digit ############"
printf 'GILGFVFTL\n' > one.pep
for al in "HLA-A02:01" "HLA-A*02:01" "HLA-A0201"; do
  echo "--- netMHCpan allele=$al"
  netMHCpan -p one.pep -a "$al" 2>&1 | grep -v '^#' | grep -E 'HLA-|Error' | head -2 | sed 's/^/    /'
done

echo
echo "############ 9. does -p mode reject length outside 8-11 for stabpan? ############"
printf 'GILGFVFTLTV\n' > len11.pep
run "stabpan len11" netMHCstabpan -p len11.pep -a HLA-A02:01

echo
echo "############ 10. netchop threshold effect ############"
for t in 0.3 0.5 0.9; do
  n=$(netchop -t $t multi.fsa 2>/dev/null | grep -c '  S ')
  echo "    -t $t -> $n cleavage sites"
done
