#!/usr/bin/env bash
# Isolate whether -pmhc failure is caused by the synlist data or by the input grammar.
set -uo pipefail
cd /tmp/pmhc_probe || exit 1

echo "=== does -p (plain peptide) work at all? ==="
printf 'SLYNTVATL\n' > s.txt
/opt/bio/netMHCpan-4.2/netMHCpan -p s.txt 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -8

echo
echo "=== -a with explicit allele + -p ==="
/opt/bio/netMHCpan-4.2/netMHCpan -p s.txt -a HLA-A02:01 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -8

echo
echo "=== test.pep.out reference: does it list alleles? ==="
grep -v '^#' /opt/bio/netMHCpan-4.2/test/test.pep.out | head -8

echo
echo "=== input used by test.pep ==="
cat /opt/bio/netMHCpan-4.2/test/test.pep
