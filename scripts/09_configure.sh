#!/usr/bin/env bash
# Install layout: set NMHOME in each launcher, place stabpan data, create tmp dirs.
set -euo pipefail

# --- 1. netMHCpan-4.2 ------------------------------------------------------
PAN=/opt/bio/netMHCpan-4.2
sed -i 's|^setenv[ \t]*NMHOME.*|setenv\tNMHOME\t'"$PAN"'|' "$PAN/netMHCpan"
mkdir -p "$PAN/tmp"
chmod 1777 "$PAN/tmp"

# --- 2. netchop-3.1 -------------------------------------------------------
CHOP=/opt/bio/netchop-3.1
sed -i 's|^setenv[ \t]*NMHOME.*|setenv\tNMHOME\t'"$CHOP"'|' "$CHOP/netchop"
mkdir -p "$CHOP/tmp"
chmod 1777 "$CHOP/tmp"

# --- 3. netMHCstabpan-1.0 -------------------------------------------------
STAB=/opt/bio/netMHCstabpan-1.0
sed -i 's|^setenv[ \t]*NMHOME.*|setenv\tNMHOME\t'"$STAB"'|' "$STAB/netMHCstabpan"
# data.tar.gz payload is this package's missing data directory
cp -a /opt/bio/src/data_x/data "$STAB/data"
mkdir -p "$STAB/tmp"
chmod 1777 "$STAB/tmp"

echo "=== resulting NMHOME lines ==="
grep -n 'NMHOME' "$PAN/netMHCpan" "$CHOP/netchop" "$STAB/netMHCstabpan"
echo
echo "=== stabpan data ==="
ls "$STAB/data" | head
echo
echo "=== launchers executable? ==="
ls -l "$PAN/netMHCpan" "$CHOP/netchop" "$STAB/netMHCstabpan"
