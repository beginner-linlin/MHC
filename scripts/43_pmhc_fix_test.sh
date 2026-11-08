#!/usr/bin/env bash
# HYPOTHESIS: the -pmhc wrapper omits `-mhc <pseudo_tmp_file>` when invoking the
# plain nnalign child, so the child cannot resolve the MHC pseudo sequences and
# emits UNDEF. Test by replaying the captured args on a real -dirty tmpdir,
# with and without -mhc, for both nnalign variants.
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
DATA=/opt/bio/netMHCpan-4.2/Linux_x86_64/data
PAN=/opt/bio/netMHCpan-4.2

ALLMHC=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3
PLAIN=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3

# Produce a pristine tmpdir from a real -pmhc run
W=/tmp/pmhc_fix
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp
"$PAN/netMHCpan" -pmhc "$PAN/test/test.pep_mhc" -dirty -tdir "$W/src_XXXXXX" > "$W/run.txt" 2>&1
D=$(grep -oE 'Tmpdir made [^ ]+' "$W/run.txt" | awk '{print $3}')
echo "pristine tmpdir: $D"
echo "  allelelist:      $(tr '\n' ' ' < "$D/allelelist")"
echo "  pseudo_tmp_file: $(head -2 "$D/pseudo_tmp_file" | tr '\n' ' ')"
echo "  0.dat (before):  $(head -1 "$D/0.dat")"
echo

try() {
    local bin="$1" extra="$2" tag="$3"
    local out="$W/0_$tag.dat"
    # shellcheck disable=SC2086
    "$bin" -ishort -aX \
        -blf "$DATA/matrices/blosum62.freq_rownorm" \
        -mpat "$DATA/matrices/BLOSUM50" \
        -sbin -afs -encmhc -nout 1 $extra \
        -allelelist "$D/allelelist" -complo \
        -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
        "$DATA/synlist_nocontext.bin" "$out" > "$W/log_$tag.txt" 2>&1
    echo "### $tag   (rc=$?)"
    echo "    first 3 output lines:"
    head -3 "$out" 2>/dev/null | sed 's/^/      /' || echo "      (no output file)"
    local undef
    undef=$(grep -c UNDEF "$out" 2>/dev/null || echo 0)
    echo "    UNDEF count: $undef"
    grep -iE 'error|cannot|wrong' "$W/log_$tag.txt" | head -2 | sed 's/^/      ! /'
    echo
}

echo "============ does adding -mhc fix it? ============"
try "$PLAIN"  ""                                    "plain_NO_mhc   (what the wrapper does)"
try "$PLAIN"  "-mhc $D/pseudo_tmp_file"             "plain_WITH_mhc (hypothesis fix)"
try "$ALLMHC" ""                                    "allmhc_NO_mhc"
try "$ALLMHC" "-mhc $D/pseudo_tmp_file"             "allmhc_WITH_mhc"
