#!/usr/bin/env bash
# Run the netMHCstabpan vendor test commands listed in test/comm.
set -uo pipefail
cd /opt/bio/netMHCstabpan-1.0/test || exit 1

run() {
    local out="$1"; shift
    echo ">>> $out : netMHCstabpan $*"
    ../netMHCstabpan "$@" > "$out" 2> "$out.err"
    local rc=$?
    echo "    exit=$rc"
    if [ -s "$out.err" ]; then head -3 "$out.err" | sed 's/^/    stderr: /'; fi
}

run MY_test.pep.out            -p test.pep
run MY_test.pep_ia.out         -ia -p test.pep
run MY_test.fsa.out            test.fsa
run MY_test.fsa_ia.out         -ia test.fsa
run MY_test.pep_userMHC.out    -hlaseq B0702.fsa -p test.pep
run MY_test.pep_userMHC_ia.out -hlaseq B0702.fsa -ia -p test.pep

echo
echo "==================== payload diff vs expected ===================="
payload() { grep -v '^#' "$1" 2>/dev/null | grep -v '^[[:space:]]*$'; }
for pair in "MY_test.pep.out:test.pep.out" \
            "MY_test.pep_ia.out:test.pep_ia.out" \
            "MY_test.fsa.out:test.fsa.out" \
            "MY_test.fsa_ia.out:test.fsa_ia.out" \
            "MY_test.pep_userMHC.out:test.pep_userMHC.out" \
            "MY_test.pep_userMHC_ia.out:test.pep_userMHC_ia.out"; do
    mine=${pair%%:*}; ref=${pair##*:}
    if [ ! -f "$ref" ]; then echo "SKIP  $mine (no $ref)"; continue; fi
    if diff <(payload "$mine") <(payload "$ref") >/dev/null 2>&1; then
        echo "PASS  $mine"
    else
        n=$(diff <(payload "$mine") <(payload "$ref") | grep -c '^[<>]')
        echo "FAIL  $mine ($n differing lines)"
        diff <(payload "$mine") <(payload "$ref") | head -8
    fi
done
