#!/usr/bin/env bash
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
export TMPDIR=$PAN/tmp
echo "############ vendor test.pep_context_mhc ############"
cat -A "$PAN/test/test.pep_context_mhc"
echo
echo "############ vendor test.pep_context ############"
cat -A "$PAN/test/test.pep_context"
