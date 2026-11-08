#!/usr/bin/env bash
# netchop needs a writable TMPDIR (its default /scratch does not exist here).
set -uo pipefail
cd /opt/bio/netchop-3.1/test || exit 1

echo "=== with TMPDIR set ==="
TMPDIR=/opt/bio/netchop-3.1/tmp ../netchop test.fsa > test.myout 2> test.myout.err
echo "exit=$?"
head -5 test.myout.err

payload() { grep -v '^#' "$1" | grep -v '^[[:space:]]*$'; }
if diff <(payload test.myout) <(payload test.out) >/dev/null 2>&1; then
    echo "PASS  netchop payload identical to test.out"
else
    echo "DIFF:"
    diff <(payload test.myout) <(payload test.out) | head -15
fi
echo
echo "--- output head ---"
head -14 test.myout
