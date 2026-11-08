#!/usr/bin/env bash
# Extract the three NetMHC-family tool archives into /opt/bio
set -euo pipefail

SRC=/opt/bio/src
DEST=/opt/bio
mkdir -p "$DEST"

for f in netchop-3.1d.Linux.tar.gz netMHCstabpan-1.0cstatic.Linux.tar.gz netMHCpan-4.2estatic.Linux.tar.gz; do
    echo "=== extracting $f ==="
    tar -xzf "$SRC/$f" -C "$DEST"
done

echo
echo "=== top level ==="
ls -la "$DEST"

echo
echo "=== symlinks (relative targets matter) ==="
find "$DEST" -type l -printf '%p -> %l\n' 2>/dev/null || true
