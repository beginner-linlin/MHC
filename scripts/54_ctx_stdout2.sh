#!/usr/bin/env bash
# The child needs the output file to already exist (it opens for update, not
# create). Create it first, then replay and capture stdout.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
BIN=$PAN/Linux_x86_64/bin
DATA=$PAN/Linux_x86_64/data
T=$PAN/test
W=/tmp/ctx_stdout2
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp
cd "$T" || exit 1

ALLMHC=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3
PLAIN=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3

mkdirty() {
    local tag=$1; shift
    "$PAN/netMHCpan" "$@" -dirty -tdir "$W/${tag}_XXXXXX" > "$W/$tag.out" 2>&1
    grep -oE 'Tmpdir made [^ ]+' "$W/$tag.out" | awk '{print $3}'
}
D_P=$(mkdirty pctx -p -context test.pep_context)
D_M=$(mkdirty mctx -pmhc -context test.pep_context_mhc)
echo "working tmpdir: $D_P"
echo "failing tmpdir: $D_M"
echo "  working allelelist head: $(head -1 "$D_P/allelelist")"
echo "  failing allelelist head: $(head -1 "$D_M/allelelist")"
echo

replay() {
    local tag=$1 bin=$2 dir=$3
    : > "$W/$tag.dat"          # child opens existing file for update
    "$bin" -ishort -aX \
        -blf "$DATA/matrices/blosum62.freq_rownorm" -mpat "$DATA/matrices/BLOSUM50" \
        -sbin -afs -encmhc -mhc "$dir/pseudo_tmp_file" -nout 1 \
        -allelelist "$dir/allelelist" -context -complo \
        -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
        "$DATA/synlist_context.bin" "$W/$tag.dat" > "$W/$tag.stdout" 2> "$W/$tag.stderr"
    echo "### $tag  rc=$?"
    local n
    n=$(grep -v '^#' "$W/$tag.stdout" | grep -vc '^[[:space:]]*$')
    echo "  stdout data lines=$n  fields=$(grep -v '^#' "$W/$tag.stdout" | grep -v '^[[:space:]]*$' | awk '{print NF}' | sort -u | tr '\n' ',')"
    grep -v '^#' "$W/$tag.stdout" | grep -v '^[[:space:]]*$' | head -1 | cut -c1-200 | sed 's/^/    /'
    echo "  0.dat: $(head -1 "$W/$tag.dat" 2>/dev/null | cut -c1-80)"
    echo "  stderr: $(head -1 "$W/$tag.stderr")"
    echo
}

echo "############ replay WORKING (-p -context tmpdir + allmhc) ############"
replay work "$ALLMHC" "$D_P"
echo "############ replay FAILING (-pmhc -context tmpdir + plain) ############"
replay fail "$PLAIN" "$D_M"
echo "############ replay FAILING tmpdir + allmhc ############"
replay fail_allmhc "$ALLMHC" "$D_M"
