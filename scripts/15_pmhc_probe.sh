#!/usr/bin/env bash
# Probe the -pmhc input format accepted by this 4.2e build.
set -uo pipefail
cd /tmp || exit 1
mkdir -p pmhc_probe && cd pmhc_probe

try() {
    local label="$1" file="$2"
    echo "########## $label ##########"
    cat "$file"
    echo "---- run ----"
    /opt/bio/netMHCpan-4.2/netMHCpan -pmhc "$file" 2>&1 | grep -v '^#' | head -8
    echo
}

# A: 2 columns (peptide allele)
printf 'SLYNTVATL HLA-A02:01\n' > a.txt
try "A: pep allele" a.txt

# B: 3 columns (peptide allele score) -- as shipped
printf 'SLYNTVATL HLA-A02:01 0.5\n' > b.txt
try "B: pep allele score" b.txt

# C: 3 columns with HLA-A*02:01 style
printf 'SLYNTVATL HLA-A*02:01\n' > c.txt
try "C: pep HLA-A*02:01" c.txt

# D: tab separated
printf 'SLYNTVATL\tHLA-A02:01\n' > d.txt
try "D: tab separated" d.txt

# E: original test file verbatim
try "E: shipped test.pep_mhc" /opt/bio/netMHCpan-4.2/test/test.pep_mhc
