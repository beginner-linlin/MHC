#!/usr/bin/env bash
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
export TMPDIR=$PAN/tmp
printf 'SLYNTVATL SLLQHLIGL HLA-A02:01\nGILGFVFTL SLLQHLIGL HLA-A02:01\n' > /tmp/smoke_ctx.txt
echo "############ input file ############"
cat -A /tmp/smoke_ctx.txt
echo
echo "############ netMHCpan_ctx raw run (stderr+stdout) ############"
netMHCpan_ctx -f /tmp/smoke_ctx.txt; echo "exit=$?"
echo
echo "############ same content via the real vendor file (known-good) ############"
netMHCpan_ctx -f "$PAN/test/test.pep_context_mhc" 2>&1 | head -8
echo "exit=$?"
