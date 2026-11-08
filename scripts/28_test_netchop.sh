#!/usr/bin/env bash
# netchop vendor self-test: ../netchop test.fsa must equal test.out
set -uo pipefail
cd /opt/bio/netchop-3.1/test || exit 1

echo "=== input ==="
ls -la
echo
echo "=== run ==="
../netchop test.fsa > test.myout 2> test.myout.err
echo "exit=$?"
echo "--- stderr ---"
head -10 test.myout.err
echo "--- output head ---"
head -12 test.myout
echo
echo "=== diff vs test.out ==="
if diff -q test.myout test.out >/dev/null 2>&1; then
    echo "PASS  byte-identical"
else
    echo "DIFF:"
    diff test.myout test.out | head -20
fi
