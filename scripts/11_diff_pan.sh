#!/usr/bin/env bash
set -uo pipefail
cd /opt/bio/netMHCpan-4.2/test || exit 1
echo "########## test.pep.myout vs test.pep.out ##########"
diff test.pep.myout test.pep.out | head -60
echo
echo "########## test.fsa.myout vs test.fsa.out ##########"
diff test.fsa.myout test.fsa.out | head -40
echo
echo "########## reference header ##########"
head -12 test.pep.out
echo "---------- mine header ----------"
head -12 test.pep.myout
