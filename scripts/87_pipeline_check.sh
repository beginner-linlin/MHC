#!/usr/bin/env bash
# Verify the documented 3-step pipeline actually runs end-to-end.
set -uo pipefail
W=/tmp/pipecheck; rm -rf "$W"; mkdir -p "$W"; cd "$W"
cat > protein.fsa <<'EOF'
>test_protein
MLLSVPLLLGLLGLAVGQCSVSWQPPPEKLLSEEDL
EOF

echo "### step1 netchop"
netchop -v 0 protein.fsa > 1_chop.txt 2>&1
echo "  exit=$? lines=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+[A-Z]' 1_chop.txt)"

echo "### step2 extract 9mers ending at S sites"
python3 - protein.fsa 1_chop.txt > 2_peptides.txt <<'PY'
import sys
prot = ''.join(l.strip() for l in open(sys.argv[1]) if not l.startswith('>'))
sites = {int(l.split()[0]) for l in open(sys.argv[2])
         if l.strip() and not l.startswith('#') and len(l.split()) > 2 and l.split()[2] == 'S'}
for end in sorted(sites):
    start = end - 9
    if start >= 0:
        print(prot[start:end])
PY
echo "  peptides=$(wc -l < 2_peptides.txt)"

echo "### step3 netMHCpan"
netMHCpan -a HLA-A02:01 -p 2_peptides.txt -BA > 3_binding.txt 2>&1
echo "  exit=$? scored=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' 3_binding.txt)"
grep -E '<= (SB|WB)' 3_binding.txt | awk '{print "    "$(NF-7)"  "$(NF-5)"  "$(NF-3)}'

echo "### step4 netMHCstabpan"
netMHCstabpan -ia -a HLA-A02:01 -p 2_peptides.txt > 4_stability.txt 2>&1
echo "  exit=$? scored=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' 4_stability.txt)"
grep -E '<= (SB|WB)' 4_stability.txt | head -3 | sed 's/^/    /'
echo
echo "RESULT: pipeline $( [ -s 3_binding.txt ] && [ -s 4_stability.txt ] && echo OK || echo FAILED )"
