#!/usr/bin/env bash
# Apply the nnalign fix permanently (with backup) and re-run ALL 8 vendor tests
# to confirm -pmhc now passes and nothing else regressed.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
BIN=$PAN/Linux_x86_64/bin
T=$PAN/test
W=/tmp/pan_all
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp

ALLMHC=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_allmhc_v3
PLAIN=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3
BACKUP=$BIN/nnalign_gaps_pan_play_MA_wgt_MN_v2_two_outputs_context_allelelist_pboth_inv_v3.orig

echo "############ apply fix (idempotent) ############"
if [ ! -f "$BACKUP" ]; then
    cp -p "$PLAIN" "$BACKUP"
    echo "  backed up plain variant -> $(basename "$BACKUP")"
fi
cp -f "$ALLMHC" "$PLAIN"
echo "  plain slot now holds the allmhc binary:"
md5sum "$PLAIN" "$BACKUP" | sed 's/^/    /'
echo

payload() { grep -v '^#' "$1" | grep -v '^[[:space:]]*$'; }

run_test() {
    local tag="$1" expected="$2"; shift 2
    local out="$W/$tag.out"
    "$PAN/netMHCpan" "$@" > "$out" 2>&1
    local rc=$?
    local status
    if [ ! -f "$T/$expected" ]; then
        status="NO-EXPECTED"
    elif diff -q <(payload "$out") <(payload "$T/$expected") >/dev/null 2>&1; then
        status="PASS"
    else
        status="FAIL"
    fi
    printf '%-34s rc=%-2s %s\n' "$tag" "$rc" "$status"
    if [ "$status" = "FAIL" ]; then
        diff <(payload "$out") <(payload "$T/$expected") | head -6 | sed 's/^/     /'
    fi
}

cd "$T" || exit 1
echo "############ all 8 vendor test commands ############"
run_test test.pep                 test.pep.out                 -p test.pep
run_test test.pep_context         test.pep_context.out         -p -context test.pep_context
run_test test.pep_wBA             test.pep_wBA.out             -p -BA test.pep
run_test test.fsa                 test.fsa.out                 test.fsa
run_test test.pep_userMHC         test.pep_userMHC.out         -hlaseq B0702.fsa -p test.pep
run_test test.pep_mhc             test.pep_mhc.out             -pmhc test.pep_mhc
run_test test.pep_context_mhc     test.pep_context_mhc.out     -pmhc -context test.pep_context_mhc
echo

echo "############ also re-check a plain single-peptide prediction ############"
printf 'SLYNTVATL\n' > "$W/one.pep"
"$PAN/netMHCpan" -p "$W/one.pep" 2>&1 | grep -E 'HLA-A\*02:01|Number of' | head -3
