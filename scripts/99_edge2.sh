#!/usr/bin/env bash
# Critical facts for the app backend: exit codes, stabpan length rules, letter whitelist.
set -uo pipefail
W=/tmp/edge2; rm -rf $W; mkdir -p $W; cd $W

echo "############ A. exit codes on error (app must not trust rc) ############"
printf 'GILGFVFTL\n' > one.pep
netMHCpan -p one.pep -a HLA-Q99:99 >o1.txt 2>e1.txt; echo "  bad allele      rc=$?  stderr=$(wc -c <e1.txt)B"
netMHCpan -p empty.txt -a HLA-A02:01 >o2.txt 2>e2.txt; echo "  missing file    rc=$?  stderr=$(wc -c <e2.txt)B"
: > empty.pep
netMHCpan -p empty.pep -a HLA-A02:01 >o3.txt 2>e3.txt; echo "  empty file      rc=$?  stderr=$(wc -c <e3.txt)B"
echo "  -> where do errors go?"
echo "     stdout o1: $(grep -c 'Error' o1.txt) error lines"
echo "     stderr e1: $(grep -c 'Error' e1.txt) error lines"

echo
echo "############ B. stabpan: which lengths are accepted, and must they be uniform? ############"
for L in 8 9 10 11 12 13; do
  python3 -c "print('A'*$L)" > s$L.pep
  r=$(netMHCstabpan -p s$L.pep -a HLA-A02:01 2>/dev/null | grep -v '^#' | grep -E 'HLA-A|Error' | head -1)
  printf '  len=%-2s  %s\n' "$L" "$(echo "$r" | cut -c1-90)"
done

echo
echo "############ C. stabpan: all same length, len 12, 3 peptides ############"
python3 -c "print('GILGFVFTLTVP'); print('MLLSVPLLLGLL'); print('KLVALGINAVMY')" > s12x3.pep
netMHCstabpan -p s12x3.pep -a HLA-A02:01 2>/dev/null | grep -v '^#' | grep -E 'HLA-A|Error' | sed 's/^/  /'

echo
echo "############ D. stabpan: mixed 9 and 10 ############"
printf 'GILGFVFTL\nGILGFVFTLT\n' > s910.pep
netMHCstabpan -p s910.pep -a HLA-A02:01 2>/dev/null | grep -v '^#' | grep -E 'HLA-A|Error' | sed 's/^/  /'

echo
echo "############ E. netMHCpan: which lengths accepted in -p mode ############"
for L in 4 7 8 9 10 11 12 15 20 25 30; do
  python3 -c "print(''.join(['A','C','D','E','F','G','H','I','K','L','M','N','P','Q','R','S','T','V','W','Y']*3)[:$L])" > p$L.pep
  r=$(netMHCpan -p p$L.pep -a HLA-A02:01 2>/dev/null | grep -v '^#' | grep -E 'HLA-A|Error|must be' | head -1)
  printf '  len=%-2s  %s\n' "$L" "$(echo "$r" | cut -c1-95)"
done

echo
echo "############ F. letter whitelist: what does netMHCpan do per letter ############"
base="GILGFVFT"
for ch in A C D E F G H I K L M N P Q R S T V W Y X B Z U J O '-'; do
  seq="${base}${ch}"
  printf '%s\n' "$seq" > lt.pep
  r=$(netMHCpan -p lt.pep -a HLA-A02:01 2>/dev/null | grep -v '^#' | grep -E 'PEPLIST' | head -1 | awk '{print $4}')
  printf '  %-2s -> %s\n' "$ch" "$r"
done

echo
echo "############ G. netchop letters ############"
printf '>t1\nGILGFVFTX\n' > nx.fsa
netchop nx.fsa 2>&1 | grep -v '^#' | head -5 | sed 's/^/  /'
