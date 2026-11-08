#!/usr/bin/env bash
# Narrow down the -pmhc line grammar by varying field counts and allele spelling.
set -uo pipefail
cd /tmp/pmhc_probe || exit 1

echo "=== hla_pseudo list sample (what names are accepted) ==="
head -5 /opt/bio/netMHCpan-4.2/data/MHC_pseudo.dat | cut -c1-80
echo "--- alleles containing A*02:01 ---"
grep -m5 'A\*02:01' /opt/bio/netMHCpan-4.2/data/MHC_pseudo.dat | cut -c1-60
echo

try() {
    local label="$1" file="$2"
    echo "########## $label ##########"
    cat -A "$file" | head -3
    echo "---- run ----"
    /opt/bio/netMHCpan-4.2/netMHCpan -pmhc "$file" 2>&1 | grep -v '^#' | grep -v '^[[:space:]]*$' | head -6
    echo
}

printf 'SLYNTVATL HLA-A*02:01\n' > f1.txt;            try "1: pep HLA-A*02:01" f1.txt
printf 'SLYNTVATL HLA-A*02:01 0.5\n' > f2.txt;       try "2: pep HLA-A*02:01 score" f2.txt
printf 'SLYNTVATL\tHLA-A*02:01\n' > f3.txt;          try "3: tab pep HLA-A*02:01" f3.txt
printf 'SLYNTVATL HLA-A*02:01 0 0 0 0\n' > f4.txt;   try "4: pep allele +4 nums" f4.txt
printf '1 SLYNTVATL HLA-A*02:01\n' > f5.txt;         try "5: idx pep allele" f5.txt
