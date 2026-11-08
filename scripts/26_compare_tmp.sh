#!/usr/bin/env bash
set -uo pipefail
for d in /tmp/keep/tp_DIDjfo /tmp/keep/tm_NcX9jr; do
    echo "########## $d"
    for f in pseudo_tmp_file allelelist 0.dat; do
        echo "--- $f"
        cat -A "$d/$f" 2>/dev/null | head -10
    done
    echo
done
