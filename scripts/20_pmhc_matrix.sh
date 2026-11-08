#!/usr/bin/env bash
# Systematically test -pmhc field layouts with a KNOWN-GOOD allele name.
set -uo pipefail
cd /tmp/pmhc_probe || exit 1

run() {
    local label="$1"; shift
    echo "########## $label ##########"
    cat -A "$1" | head -2
    echo "  ---- output ----"
    /opt/bio/netMHCpan-4.2/netMHCpan -pmhc "$1" 2>&1 \
      | grep -v '^#' | grep -v '^[[:space:]]*$' | grep -v '^-*$' | head -4
    echo
}

# The -p mode accepted: "SLYNTVATL 0.083"? No: test.pep is "pep measurement"
# and -p worked. So PEPTIDEMHC should be "pep mhc [measurement]".
printf 'SLYNTVATL HLA-A02:01\n'        > x1.txt
printf 'SLYNTVATL HLA-A02:01 0.5\n'    > x2.txt
printf 'SLYNTVATL HLA-A*02:01\n'       > x3.txt
printf 'SLYNTVATL HLA-A*02:01 0.5\n'   > x4.txt

run "x1: pep mhc"            x1.txt
run "x2: pep mhc meas"       x2.txt
run "x3: pep mhc(star)"      x3.txt
run "x4: pep mhc(star) meas" x4.txt

echo "=== inptype 3 explicit ==="
/opt/bio/netMHCpan-4.2/netMHCpan -inptype 3 x1.txt 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -6
