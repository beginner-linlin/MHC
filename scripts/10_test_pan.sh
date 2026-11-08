#!/usr/bin/env bash
# Run the vendor test suite for netMHCpan-4.2 and diff against the expected outputs.
set -uo pipefail
cd /opt/bio/netMHCpan-4.2/test || exit 1

run() {
    local out="$1"; shift
    echo ">>> $out : netMHCpan $*"
    ../netMHCpan "$@" > "$out" 2> "$out.err"
    local rc=$?
    if [ $rc -ne 0 ]; then echo "    EXIT=$rc"; fi
    head -3 "$out.err" 2>/dev/null | sed 's/^/    stderr: /'
    return 0
}

run test.pep.myout            -p test.pep
run test.pep_context.myout    -p -context test.pep_context
run test.pep_mhc.myout        -pmhc test.pep_mhc
run test.pep_context_mhc.myout -pmhc -context test.pep_context_mhc
run test.pep_wBA.myout        -p test.pep -BA
run test.fsa.myout            test.fsa
run test.pep_userMHC.myout    -hlaseq B0702.fsa -p test.pep
run test.pep_xls.myout        -p test.pep -BA -xls -a HLA-A01:01,HLA-A02:01 -xlsfile NetMHCpan_myout.xls

echo
echo "==================== diff vs expected ===================="
for pair in "test.pep.myout:test.pep.out" \
            "test.pep_context.myout:test.pep_context.out" \
            "test.pep_mhc.myout:test.pep_mhc.out" \
            "test.pep_context_mhc.myout:test.pep_context_mhc.out" \
            "test.pep_wBA.myout:test.pep_wBA.out" \
            "test.fsa.myout:test.fsa.out" \
            "test.pep_userMHC.myout:test.pep_userMHC.out"; do
    mine=${pair%%:*}; ref=${pair##*:}
    if [ ! -f "$ref" ]; then echo "SKIP  $mine (no reference $ref)"; continue; fi
    if diff -q "$mine" "$ref" >/dev/null 2>&1; then
        echo "PASS  $mine"
    else
        n=$(diff "$mine" "$ref" 2>/dev/null | grep -c '^[<>]')
        echo "DIFF  $mine  ($n differing lines)"
    fi
done
