#!/usr/bin/env bash
# netchop: compare only the prediction payload.
set -uo pipefail
cd /opt/bio/netchop-3.1/test || exit 1
payload() { grep -v '^#' "$1" | grep -v '^[[:space:]]*$'; }
if diff <(payload test.myout) <(payload test.out) >/dev/null 2>&1; then
    echo "PASS  netchop payload identical to test.out"
    echo "--- payload preview ---"
    payload test.myout | head -8
else
    echo "FAIL  netchop payload differs"
    diff <(payload test.myout) <(payload test.out) | head -20
fi
