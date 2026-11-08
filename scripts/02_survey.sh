#!/usr/bin/env bash
# Survey the extracted packages: layout, launcher scripts, binaries, readme hints.
set -uo pipefail

for pkg in /opt/bio/netMHCpan-4.2 /opt/bio/netMHCstabpan-1.0 /opt/bio/netchop-3.1; do
    echo "############################################################"
    echo "## $pkg"
    echo "############################################################"
    echo "--- top level ---"
    ls -la "$pkg"
    echo
    echo "--- Linux_x86_64 tree (depth 2) ---"
    find "$pkg/Linux_x86_64" -maxdepth 2 | head -40
    echo
    echo "--- file types of executables ---"
    for f in $(find "$pkg/Linux_x86_64/bin" -maxdepth 1 -type f 2>/dev/null); do
        printf '%-60s %s\n' "$f" "$(file -b "$f")"
    done
    echo
done
