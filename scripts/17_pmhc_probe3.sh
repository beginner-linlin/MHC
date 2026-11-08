#!/usr/bin/env bash
# The -pmhc reader expects a different line grammar. Derive it from the binary
# and from the peptide+MHC reader error paths.
set -uo pipefail

BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin/netMHCpan-4.2
echo "=== strings near PRDLIST_READ / Wrong line format ==="
strings -a "$BIN" | grep -n -iE 'Wrong line format|PRDLIST|peptide input|cannot be found in hla_pseudo' | head -20

echo
echo "=== MHC_pseudo.dat: is HLA-A02:01 present? ==="
grep -m3 '^HLA-A02:01' /opt/bio/netMHCpan-4.2/data/MHC_pseudo.dat | cut -c1-40
echo "count HLA-A02:01:"; grep -c '^HLA-A02:01' /opt/bio/netMHCpan-4.2/data/MHC_pseudo.dat

echo
echo "=== what does the -p (peptide only) mode print for alleles ==="
cd /tmp/pmhc_probe || exit 1
printf 'SLYNTVATL\n' > p.txt
/opt/bio/netMHCpan-4.2/netMHCpan -p p.txt 2>&1 | grep -v '^#' | head -5

echo
echo "=== try -pmhc with allele as in pseudo list ==="
printf 'SLYNTVATL HLA-A02:01\n' > g1.txt
/opt/bio/netMHCpan-4.2/netMHCpan -pmhc g1.txt 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -6
