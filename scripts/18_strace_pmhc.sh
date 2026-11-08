#!/usr/bin/env bash
# Trace what -pmhc actually does: which files it opens and where it fails.
set -uo pipefail
cd /tmp/pmhc_probe || exit 1
which strace || { echo "installing strace"; DEBIAN_FRONTEND=noninteractive apt-get install -y strace >/dev/null 2>&1; }
printf 'SLYNTVATL HLA-A02:01\n' > t.txt
echo "=== run under strace: file opens ==="
strace -f -e trace=openat,read,write -s 200 /opt/bio/netMHCpan-4.2/netMHCpan -pmhc t.txt 2>&1 | grep -vE 'ld.so|libc|locale|/proc/|/sys/' | tail -60
