#!/usr/bin/env bash
# Clean up diagnostic scratch dirs, then produce the final installation report.
set -uo pipefail
BASE=/opt/bio
PAN=$BASE/netMHCpan-4.2
CHOP=$BASE/netchop-3.1
STAB=$BASE/netMHCstabpan-1.0

echo "############ removing diagnostic scratch directories ############"
for d in ctx_fields ctx_fmt ctx_probe fix stabpan_colprobe stabpan_compat stabpan_compat2 \
         stabpan_layout stabpan_layout2 stabpan_layout3 stabpan_layout4 stabpan_layout5 \
         stabpan_probe verify verify_final; do
    if [ -d "$BASE/$d" ]; then rm -rf "$BASE/$d"; echo "  removed $BASE/$d"; fi
done
# keep only the shim that is actually wired up
for f in netMHCpan-4.2-ic50shim netMHCpan_colshim netMHCpan_layoutshim netMHCpan_layoutshim2 \
         netMHCpan_layoutshim3 netMHCpan_layoutshim4 netMHCpan_layoutshim5 netMHCpan_shim; do
    [ -f "$BASE/compat/$f" ] && rm -f "$BASE/compat/$f" && echo "  removed compat/$f"
done
echo "  kept: compat/netMHCpan-compat, compat/compat.log, compat/netMHCstabpan.launcher.orig"
echo

echo "############ final layout ############"
echo "  /opt/bio/src        : $(ls -1 "$BASE/src" 2>/dev/null | tr '\n' ' ')"
for d in "$PAN" "$CHOP" "$STAB"; do
    printf '  %-30s %6s  %5s files\n' "$d" "$(du -sh "$d" | cut -f1)" "$(find "$d" -type f | wc -l)"
done
echo

echo "############ PATH symlinks ############"
ls -la /usr/local/bin | grep -E 'netMHCpan|netchop|netMHCstabpan' | sed 's/^/  /'
echo

echo "############ one-shot smoke test of each tool from PATH ############"
export TMPDIR=$PAN/tmp
printf 'SLYNTVATL\nGILGFVFTL\n' > /tmp/smoke.pep
echo "  --- netMHCpan -p (HLA-A*02:01, 9mer) ---"
netMHCpan -a HLA-A02:01 -p /tmp/smoke.pep 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' | sed 's/^/    /'
echo
echo "  --- netchop (cleavage, 9mer peptide) ---"
printf '>smoke\nSLYNTVATLGILGFVFTL\n' > /tmp/smoke.fsa
TMPDIR=$CHOP/tmp netchop /tmp/smoke.fsa 2>&1 | grep -E '^[[:space:]]*[0-9]+' | head -6 | sed 's/^/    /'
echo
echo "  --- netMHCstabpan -ia (half-life + affinity) ---"
netMHCstabpan -ia -a HLA-A02:01 -p /tmp/smoke.pep 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' | sed 's/^/    /'
echo
echo "  --- netMHCpan_ctx (-pmhc -context equivalent) ---"
printf 'SLYNTVATL SLLQHLIGL HLA-A02:01\nGILGFVFTL SLLQHLIGL HLA-A02:01\n' > /tmp/smoke_ctx.txt
netMHCpan_ctx -f /tmp/smoke_ctx.txt 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' | sed 's/^/    /'
