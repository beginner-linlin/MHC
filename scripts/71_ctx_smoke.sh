#!/usr/bin/env bash
# netMHCpan_ctx smoke with a VALID context: the context must contain the peptide.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
export TMPDIR=$PAN/tmp
printf 'SLYNTVATL AAAASLYNTVATLGGG HLA-A02:01\nGILGFVFTL AAAAGILGFVFTLGGG HLA-A02:01\n' > /tmp/smoke_ctx.txt

echo "############ input (peptide context mhc) ############"
cat /tmp/smoke_ctx.txt | sed 's/^/  /'
echo
echo "############ netMHCpan_ctx output ############"
netMHCpan_ctx -f /tmp/smoke_ctx.txt 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA|allele' | sed 's/^/  /'
echo "exit=${PIPESTATUS[0]}"
echo
echo "############ same input, two alleles ############"
printf 'SLYNTVATL AAAASLYNTVATLGGG HLA-A02:01\nSLYNTVATL AAAASLYNTVATLGGG HLA-A01:01\n' > /tmp/smoke_ctx2.txt
netMHCpan_ctx -f /tmp/smoke_ctx2.txt 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA|allele' | sed 's/^/  /'
