#!/usr/bin/env bash
# Compare the 0.dat the child writes in the WORKING -p -context run vs the
# FAILING -pmhc -context run, then replay exact argv to probe -nout.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
BIN=$PAN/Linux_x86_64/bin
DATA=$PAN/Linux_x86_64/data
T=$PAN/test
W=/tmp/ctx_probe
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp
cd "$T" || exit 1

ALLMHC=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3
PLAIN=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3

run_dirty() {
    local tag=$1; shift
    "$PAN/netMHCpan" "$@" -dirty -tdir "$W/${tag}_XXXXXX" > "$W/$tag.out" 2>&1
    local d
    d=$(grep -oE 'Tmpdir made [^ ]+' "$W/$tag.out" | awk '{print $3}')
    echo "$d"
}

echo "############ 0.dat from -p -context (WORKS) ############"
D1=$(run_dirty pctx -p -context test.pep_context)
echo "tmpdir=$D1"
[ -f "$D1/0.dat" ] && { echo "  lines=$(wc -l < "$D1/0.dat") fields=$(awk '{print NF}' "$D1/0.dat" | sort -u | tr '\n' ',')"; head -2 "$D1/0.dat" | sed 's/^/    /'; }
echo

echo "############ 0.dat from -pmhc -context (FAILS) ############"
D2=$(run_dirty mctx -pmhc -context test.pep_context_mhc)
echo "tmpdir=$D2"
[ -f "$D2/0.dat" ] && { echo "  lines=$(wc -l < "$D2/0.dat") fields=$(awk '{print NF}' "$D2/0.dat" | sort -u | tr '\n' ',')"; head -2 "$D2/0.dat" | sed 's/^/    /'; }
echo

echo "############ input files side by side ############"
echo "  test.pep_context     : $(head -1 test.pep_context)"
echo "  test.pep_context_mhc : $(head -1 test.pep_context_mhc)"
echo

echo "############ replay EXACT argv on the failing tmpdir, varying -nout ############"
for nout in 1 2; do
    out="$W/replay_$nout.dat"
    "$ALLMHC" -ishort -aX \
        -blf "$DATA/matrices/blosum62.freq_rownorm" -mpat "$DATA/matrices/BLOSUM50" \
        -sbin -afs -encmhc -mhc "$D2/pseudo_tmp_file" -nout "$nout" \
        -allelelist "$D2/allelelist" -context -complo \
        -posvecfmt "$DATA/freq_vectors/freq_vector_%i" \
        "$DATA/synlist_context.bin" "$out" > "$W/replay_$nout.log" 2>&1
    echo "  -nout $nout  rc=$?  file=$([ -f "$out" ] && echo yes || echo no)"
    if [ -f "$out" ]; then
        echo "     fields: $(awk '{print NF}' "$out" | sort -u | tr '\n' ',')  lines=$(wc -l < "$out")"
        head -1 "$out" | cut -c1-150 | sed 's/^/     /'
    fi
    head -2 "$W/replay_$nout.log" | sed 's/^/     log: /'
done
