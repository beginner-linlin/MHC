#!/usr/bin/env bash
# Compare bundled data dirs against data.tar.gz payload; inspect dynamic deps.
set -uo pipefail

echo "############ sizes ############"
du -sh /opt/bio/netMHCpan-4.2/data /opt/bio/netMHCpan-4.2/Linux_x86_64/data \
       /opt/bio/netMHCstabpan-1.0/data /opt/bio/netchop-3.1/data \
       /opt/bio/netchop-3.1/etc /opt/bio/src/data 2>&1

echo
echo "############ netMHCpan-4.2/data top ############"
ls -la /opt/bio/netMHCpan-4.2/data
echo "--- counts ---"
find /opt/bio/netMHCpan-4.2/data -type f | wc -l
find /opt/bio/netMHCpan-4.2/data -type f -size +1M -printf '%s\t%p\n' | sort -rn | head

echo
echo "############ data.tar.gz payload ############"
ls -la /opt/bio/src/data
find /opt/bio/src/data -type f | wc -l
du -sh /opt/bio/src/data/*

echo
echo "############ netchop etc tree ############"
find /opt/bio/netchop-3.1/etc -maxdepth 2 -type d

echo
echo "############ ldd netchop binaries ############"
for f in /opt/bio/netchop-3.1/Linux_x86_64/bin/*; do
  echo "--- $f"
  ldd "$f" 2>&1 | head -20
done
