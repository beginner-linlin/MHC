#!/usr/bin/env bash
# KEY INSIGHT from script 39: the parent reads the child's STDOUT (piped through
# `grep -v "#"`), not just 0.dat. So capture the child's stdout for the working
# and failing context runs, and compare field counts.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
BIN=$PAN/Linux_x86_64/bin
DATA=$PAN/Linux_x86_64/data
T=$PAN/test
W=/tmp/ctx_stdout
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
echo

replay() {
    local tag=$1 bin=$2 dir=$3 syn=$4
    "$bin" -ishort -aX \
        -blf "$DATA/matrices/blosum62.freq_rownorm" -mpat "$DATA/matrices/BLOSUM50" \
        -sbin -afs -encmhc -mhc "$dir/pseudo_tmp_file" -nout 1 \
        -allelelist "$dir/allelelist" -context -complo \
        -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
        "$DATA/$syn" "$W/$tag.dat" > "$W/$tag.stdout" 2> "$W/$tag.stderr"
    echo "### $tag  rc=$?"
    echo "  stdout (non-#) lines=$(grep -vc '^#' "$W/$tag.stdout" || true)  fields=$(grep -v '^#' "$W/$tag.stdout" | grep -v '^[[:space:]]*$' | awk '{print NF}' | sort -u | tr '\n' ',')"
    grep -v '^#' "$W/$tag.stdout" | grep -v '^[[:space:]]*$' | head -2 | cut -c1-170 | sed 's/^/    /'
    echo "  0.dat fields=$(awk '{print NF}' "$W/$tag.dat" 2>/dev/null | sort -u | tr '\n' ',')"
    echo "  stderr: $(head -2 "$W/$tag.stderr" | tr '\n' ' ')"
    echo
}

echo "############ replay: WORKING config (-p -context tmpdir, allmhc variant) ############"
replay work "$ALLMHC" "$D_P" synlist_context.bin
echo "############ replay: FAILING config (-pmhc -context tmpdir, plain variant) ############"
replay fail "$PLAIN" "$D_M" synlist_context.bin
echo "############ replay: FAILING tmpdir but allmhc variant ############"
replay fail_allmhc "$ALLMHC" "$D_M" synlist_context.bin
