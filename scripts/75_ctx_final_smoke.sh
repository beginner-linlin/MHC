#!/usr/bin/env bash
# Final smoke: correct 12-residue context (peptide + flanks).
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
export TMPDIR=$PAN/tmp

echo "############ rule: context must be exactly 12 residues for a 9mer peptide ############"
echo
echo "############ netMHCpan_ctx, single allele ############"
printf 'SLYNTVATL AASLYNTVATLA HLA-A02:01\nGILGFVFTL AAGILGFVFTLA HLA-A02:01\n' > /tmp/ctx_ok.txt
cat /tmp/ctx_ok.txt | sed 's/^/  IN: /'
netMHCpan_ctx -f /tmp/ctx_ok.txt 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA|=====' | sed 's/^/  /'
echo
echo "############ netMHCpan_ctx, two alleles in one file ############"
printf 'SLYNTVATL AASLYNTVATLA HLA-A02:01\nSLYNTVATL AASLYNTVATLA HLA-A01:01\n' > /tmp/ctx_ok2.txt
cat /tmp/ctx_ok2.txt | sed 's/^/  IN: /'
netMHCpan_ctx -f /tmp/ctx_ok2.txt 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA|=====' | sed 's/^/  /'
echo
echo "############ regression: vendor file still reproduces expected 10/10 ############"
netMHCpan_ctx -f "$PAN/test/test.pep_context_mhc" > /tmp/ctx_vend.out 2>&1
got=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' /tmp/ctx_vend.out)
exp=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$PAN/test/test.pep_context_mhc.out")
echo "  rows produced=$got  expected=$exp  $([ "$got" -eq "$exp" ] && echo PASS || echo FAIL)"
