#!/usr/bin/env bash
# Reproduce the helper crash directly, then check whether the two nnalign
# variants differ in behaviour for the same inputs.
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
DATA=/opt/bio/netMHCpan-4.2/Linux_x86_64/data

# Rebuild the exact tmpdir contents the wrapper would have made.
mkcase() {
    local dir=$1 allele=$2
    rm -rf "$dir"; mkdir -p "$dir"
    printf '%s %s\n' "$allele" "$allele" > "$dir/allelelist"
    # pseudo_tmp_file: name + pseudo sequence, as generated from MHC_pseudo.dat
    grep -m1 "^${allele} " "$DATA/MHC_pseudo.dat" > "$dir/pseudo_tmp_file"
    echo "  pseudo_tmp_file: $(cat "$dir/pseudo_tmp_file" | cut -c1-50)"
    echo "  allelelist     : $(cat "$dir/allelelist")"
}

echo "############ allmhc_v3 (used by -p) ############"
mkcase /tmp/case_all HLA-A02:01
"$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3" \
  -ishort "" -aX -blf "$DATA/matrices/blosum62.freq_rownorm" -mpat "$DATA/matrices/BLOSUM50" \
  -sbin -afs -encmhc -mhc /tmp/case_all/pseudo_tmp_file -nout 1 \
  -allelelist /tmp/case_all/allelelist -complo \
  -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
  "$DATA/synlist_nocontext.bin" /tmp/case_all/0.dat 2>&1 | tail -5
echo "  exit=$? outsize=$(stat -c%s /tmp/case_all/0.dat 2>/dev/null || echo none)"

echo
echo "############ both_inv_v3 (used by -pmhc) ############"
mkcase /tmp/case_inv HLA-A02:01
"$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3" \
  -ishort "" -aX -blf "$DATA/matrices/blosum62.freq_rownorm" -mpat "$DATA/matrices/BLOSUM50" \
  -sbin -afs -encmhc -mhc /tmp/case_inv/pseudo_tmp_file -nout 1 \
  -allelelist /tmp/case_inv/allelelist -complo \
  -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
  "$DATA/synlist_nocontext.bin" /tmp/case_inv/0.dat 2>&1 | tail -5
echo "  exit=$? outsize=$(stat -c%s /tmp/case_inv/0.dat 2>/dev/null || echo none)"
