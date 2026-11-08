#!/usr/bin/env bash
# Compare what each nnalign variant writes for the SAME context+pmhc run, and
# read the parent's own format strings to see what it expects.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
BIN=$PAN/Linux_x86_64/bin
T=$PAN/test
W=/tmp/ctx_cmp
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp

ALLMHC=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3
PLAIN=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3
BACKUP=$PLAIN.orig

show_0dat() {
    local tag="$1"
    "$PAN/netMHCpan" -pmhc -context "$T/test.pep_context_mhc" -dirty -tdir "$W/${tag}_XXXXXX" > "$W/$tag.out" 2>&1
    echo "### $tag"
    tail -1 "$W/$tag.out" | cut -c1-120
    local d
    d=$(grep -oE 'Tmpdir made [^ ]+' "$W/$tag.out" | awk '{print $3}')
    if [ -n "$d" ] && [ -f "$d/0.dat" ]; then
        echo "    0.dat ($(wc -l < "$d/0.dat") lines, $(awk '{print NF}' "$d/0.dat" | sort -u | tr '\n' ' ')fields):"
        head -2 "$d/0.dat" | sed 's/^/      /'
    else
        echo "    (no 0.dat)"
    fi
    echo
}

echo "############ current state: plain slot = allmhc ############"
md5sum "$PLAIN" | sed 's/^/  /'
show_0dat cur_allmhc

echo "############ restore ORIGINAL plain variant ############"
cp -f "$BACKUP" "$PLAIN"
md5sum "$PLAIN" | sed 's/^/  /'
show_0dat orig_plain

echo "############ parent's PRDLIST_READ format strings ############"
strings -a "$BIN/netMHCpan-4.2" | grep -iE 'PRDLIST|Wrong line format' | head -20

echo
echo "############ restore the allmhc fix (leave system working) ############"
cp -f "$ALLMHC" "$PLAIN"
md5sum "$PLAIN" | sed 's/^/  /'
