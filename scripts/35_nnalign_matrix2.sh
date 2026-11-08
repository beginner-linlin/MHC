#!/usr/bin/env bash
# Controlled experiment, corrected: -ishort takes an (empty) argument.
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
DATA=/opt/bio/netMHCpan-4.2/Linux_x86_64/data
W=/tmp/nn_exp
rm -rf "$W"; mkdir -p "$W"
printf 'HLA-A02:01 YFAMYGEKVAHTHVDTLYVRYHYYTWAVLAYTWY\n' > "$W/pseudo_tmp_file"

ALLMHC=nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3
PLAIN=nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3

run_variant() {
    local variant="$1" allelelist_content="$2" tag="$3"
    printf '%s\n' "$allelelist_content" > "$W/allelelist"
    rm -f "$W/0.dat"
    echo "########## $tag"
    echo "  allelelist: $allelelist_content"
    "$BIN/$variant" \
      -ishort "" -aX -blf "$DATA/matrices/blosum62.freq_rownorm" -mpat "$DATA/matrices/BLOSUM50" \
      -sbin -afs -encmhc -mhc "$W/pseudo_tmp_file" -nout 1 \
      -allelelist "$W/allelelist" -complo \
      -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
      "$DATA/synlist_nocontext.bin" "$W/0.dat" 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -4
    echo "  rc=$?  0.dat => $(cat "$W/0.dat" 2>/dev/null | head -2 || echo MISSING)"
    echo
}

run_variant "$ALLMHC" "ALL_MHC HLA-A02:01"    "allmhc_v3 + ALL_MHC list"
run_variant "$ALLMHC" "HLA-A02:01 HLA-A02:01" "allmhc_v3 + plain list"
run_variant "$PLAIN"  "ALL_MHC HLA-A02:01"    "plain_v3  + ALL_MHC list"
run_variant "$PLAIN"  "HLA-A02:01 HLA-A02:01" "plain_v3  + plain list"
