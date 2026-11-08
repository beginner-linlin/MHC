#!/usr/bin/env bash
# Benchmark the three tools to size the app's job model.
set -uo pipefail
W=/tmp/bench; rm -rf $W; mkdir -p $W; cd $W

cat > pep.txt <<'EOF'
SLYNTVATL
MLLSVPLLL
RPSQRHGSK
GILGFVFTL
KLVALGINAV
EOF

python3 - <<'PY'
import random
random.seed(1)
aa="ACDEFGHIKLMNPQRSTVWY"
seq="".join(random.choice(aa) for _ in range(300))
open("prot.fsa","w").write(">prot300\n"+seq+"\n")
print("  made 300aa protein")
PY

echo "############ netMHCpan: 5 peptides, 1 allele ############"
/usr/bin/time -f "  wall=%es" netMHCpan -p pep.txt -a HLA-A02:01 -BA > pan5.out 2>pan5.err
tail -1 pan5.err
wc -l < pan5.out | sed 's/^/  lines: /'

echo
echo "############ netMHCpan: 300aa protein (292 9mers), 1 allele ############"
/usr/bin/time -f "  wall=%es" netMHCpan -f prot.fsa -a HLA-A02:01 -BA > pan300.out 2>pan300.err
tail -1 pan300.err
wc -l < pan300.out | sed 's/^/  lines: /'

echo
echo "############ netMHCpan: 292 peptides x 4 alleles ############"
/usr/bin/time -f "  wall=%es" netMHCpan -f prot.fsa -a HLA-A02:01,HLA-A01:01,HLA-B07:02,HLA-A24:02 -BA > pan4.out 2>pan4.err
tail -1 pan4.err
wc -l < pan4.out | sed 's/^/  lines: /'

echo
echo "############ netchop: 300aa protein ############"
/usr/bin/time -f "  wall=%es" netchop prot.fsa > chop.out 2>chop.err
tail -1 chop.err
wc -l < chop.out | sed 's/^/  lines: /'

echo
echo "############ netMHCstabpan: 292 peptides x 1 allele, with -ia ############"
/usr/bin/time -f "  wall=%es" netMHCstabpan -f prot.fsa -a HLA-A02:01 -ia > stab.out 2>stab.err
tail -1 stab.err
wc -l < stab.out | sed 's/^/  lines: /'
