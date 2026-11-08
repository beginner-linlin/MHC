#!/usr/bin/env bash
# Compare only the prediction payload (strip '#' header lines and blank lines).
set -uo pipefail
cd /opt/bio/netMHCpan-4.2/test || exit 1

payload() { grep -v '^#' "$1" | grep -v '^[[:space:]]*$'; }

for pair in "test.pep.myout:test.pep.out" \
            "test.pep_context.myout:test.pep_context.out" \
            "test.pep_mhc.myout:test.pep_mhc.out" \
            "test.pep_context_mhc.myout:test.pep_context_mhc.out" \
            "test.pep_wBA.myout:test.pep_wBA.out" \
            "test.fsa.myout:test.fsa.out" \
            "test.pep_userMHC.myout:test.pep_userMHC.out"; do
    mine=${pair%%:*}; ref=${pair##*:}
    if [ ! -f "$ref" ]; then echo "SKIP  $mine"; continue; fi
    if diff <(payload "$mine") <(payload "$ref") >/dev/null 2>&1; then
        echo "PASS  payload identical: $mine"
    else
        n=$(diff <(payload "$mine") <(payload "$ref") | grep -c '^[<>]')
        echo "FAIL  $mine ($n differing payload lines)"
        diff <(payload "$mine") <(payload "$ref") | head -10
    fi
done
