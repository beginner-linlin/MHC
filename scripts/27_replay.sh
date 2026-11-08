#!/usr/bin/env bash
# The -pmhc path uses the non-allmhc nnalign variant and passes a two-column
# allelelist. Check what that variant expects by inspecting its strings and by
# feeding it the ALL_MHC-style allelelist.
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
DATA=/opt/bio/netMHCpan-4.2/Linux_x86_64/data

echo "=== strings: allmhc marker in the two variants ==="
echo "--- allmhc_v3 ---"
strings -a "$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3" | grep -iE 'ALL_MHC|allelelist' | head -10
echo "--- both_inv_v3 ---"
strings -a "$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3" | grep -iE 'ALL_MHC|allelelist' | head -10

echo
echo "=== md5 of the two binaries ==="
md5sum "$BIN"/nnalign*_v3

echo
echo "=== retry both_inv_v3 with ALL_MHC allelelist on the kept inputs ==="
rm -rf /tmp/replay && mkdir -p /tmp/replay
cp /tmp/keep/tm_NcX9jr/pseudo_tmp_file /tmp/replay/
printf 'ALL_MHC HLA-A02:01\n' > /tmp/replay/allelelist
"$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3" \
  -ishort "" -aX -blf "$DATA/matrices/blosum62.freq_rownorm" -mpat "$DATA/matrices/BLOSUM50" \
  -sbin -afs -encmhc -mhc /tmp/replay/pseudo_tmp_file -nout 1 \
  -allelelist /tmp/replay/allelelist -complo \
  -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
  "$DATA/synlist_nocontext.bin" /tmp/replay/0.dat 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -5
echo "  outsize=$(stat -c%s /tmp/replay/0.dat 2>/dev/null || echo none)"
