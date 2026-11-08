#!/usr/bin/env bash
# Check network / apt availability for installing tcsh.
set -uo pipefail
echo "=== apt policy tcsh ==="
apt-get -s install tcsh 2>&1 | tail -20
echo
echo "=== network test ==="
timeout 10 curl -sS -o /dev/null -w '%{http_code}\n' http://archive.ubuntu.com/ubuntu/ 2>&1 || echo "curl failed"
