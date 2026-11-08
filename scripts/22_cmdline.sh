#!/usr/bin/env bash
# Capture the FULL nnalign command line for both -p (ok) and -pmhc (fail).
set -uo pipefail
cd /tmp/pmhc_probe || exit 1

echo "################ -p (works) ################"
printf 'SLYNTVATL 0.5\n' > good.pep
strace -f -e trace=execve -s 2000 /opt/bio/netMHCpan-4.2/netMHCpan -p good.pep 2>&1 \
  | grep 'nnalign' | grep -v ENOENT | head -3 > /tmp/cmd_p.txt
sed 's/\[.*nnalign/nnalign/' /tmp/cmd_p.txt | tr ',' '\n' | sed 's/^ *//' | head -40

echo
echo "################ -pmhc (fails) ################"
printf 'SLYNTVATL HLA-A02:01 0.5\n' > bad.pmhc
strace -f -e trace=execve -s 2000 /opt/bio/netMHCpan-4.2/netMHCpan -pmhc bad.pmhc 2>&1 \
  | grep 'nnalign' | grep -v ENOENT | head -3 > /tmp/cmd_pmhc.txt
sed 's/\[.*nnalign/nnalign/' /tmp/cmd_pmhc.txt | tr ',' '\n' | sed 's/^ *//' | head -40
