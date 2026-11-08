#!/usr/bin/env bash
# DECISIVE EXPERIMENT: the -p path uses the allmhc nnalign variant and works;
# the -pmhc path uses the plain variant and fails. Swap the binaries at the
# filename level (the compiled parent picks by name) and see if -pmhc works.
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/pmhc_swap
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp

ALLMHC=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3
PLAIN=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3

payload() { grep -v '^#' "$1" | grep -v '^[[:space:]]*$'; }

echo "############ why did my manual replay fail? (log from script 43) ############"
head -6 /tmp/pmhc_fix/log_plain_NO_mhc.txt 2>/dev/null || echo "(no log)"
echo

echo "############ BASELINE: -pmhc with the shipped plain variant ############"
"$PAN/netMHCpan" -pmhc "$T/test.pep_mhc" > "$W/base.out" 2>&1
tail -2 "$W/base.out"
echo

echo "############ SWAP: install the allmhc variant under the plain filename ############"
cp -p "$PLAIN" "$W/plain.orig"
cp -f "$ALLMHC" "$PLAIN"
ls -la "$PLAIN"
echo

"$PAN/netMHCpan" -pmhc "$T/test.pep_mhc" > "$W/swapped.out" 2>&1
echo "after swap, tail of output:"
tail -2 "$W/swapped.out"
echo
echo "--- payload diff vs vendor expected ---"
if diff <(payload "$W/swapped.out") <(payload "$T/test.pep_mhc.out") > "$W/d.txt" 2>&1; then
    echo "PASS  -pmhc now matches test.pep_mhc.out exactly"
else
    echo "still differs ($(grep -c '^[<>]' "$W/d.txt") lines):"
    head -12 "$W/d.txt"
fi
echo

echo "############ RESTORE the original binary ############"
cp -f "$W/plain.orig" "$PLAIN"
md5sum "$PLAIN" "$W/plain.orig" "$ALLMHC"
