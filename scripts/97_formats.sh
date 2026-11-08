#!/usr/bin/env bash
# Dump exact output formats for writing reliable parsers.
set -uo pipefail
W=/tmp/fmt; rm -rf $W; mkdir -p $W; cd $W

cat > pep.txt <<'EOF'
SLYNTVATL
MLLSVPLLL
RPSQRHGSK
EOF

cat > prot.fsa <<'EOF'
>test_protein
MLLSVPLLLGLLGAAACSSNCGSS
EOF

echo "=========== 1. netMHCpan -BA (cat -A style, show exact) ==========="
netMHCpan -p pep.txt -a HLA-A02:01 -BA > pan.out 2>/dev/null
cat -A pan.out | head -20

echo
echo "=========== 2. netMHCpan -BA numeric raw ==========="
cat pan.out

echo
echo "=========== 3. netchop raw ==========="
netchop prot.fsa > chop.out 2>/dev/null
cat chop.out

echo
echo "=========== 4. netMHCstabpan -ia raw ==========="
netMHCstabpan -p pep.txt -a HLA-A02:01 -ia > stab.out 2>/dev/null
cat stab.out

echo
echo "=========== 5. netMHCstabpan without -ia ==========="
netMHCstabpan -p pep.txt -a HLA-A02:01 > stab2.out 2>/dev/null
cat stab2.out

echo
echo "=========== 6. netMHCpan -f fasta (multiple alleles) ==========="
netMHCpan -f prot.fsa -a HLA-A02:01,HLA-B07:02 -BA > pan2.out 2>/dev/null
head -12 pan2.out
echo "  ... total lines: $(wc -l < pan2.out)"
