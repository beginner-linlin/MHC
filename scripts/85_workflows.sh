#!/usr/bin/env bash
# Practical workflow tests: protein FASTA direct, multi-allele, sorting, xls.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
STAB=/opt/bio/netMHCstabpan-1.0
W=/tmp/workflow; rm -rf "$W"; mkdir -p "$W"
cat > "$W/prot.fsa" <<'EOF'
>sp|P01730|example_protein
MLLSVPLLLGLLGLAVGQCSVSWQPPPEKLLSEEDLLVHCSGKV
EOF

echo "################ 1. protein FASTA -> netMHCpan (auto 9mers) ################"
"$PAN/netMHCpan" -a HLA-A02:01 -f "$W/prot.fsa" > "$W/pan_fsa.out" 2>&1
echo "  exit=$?  peptides scored=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan_fsa.out")"
echo "  protein id column:"; grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan_fsa.out" | awk '{print "    "$(NF-2)}' | sort -u
echo
echo "################ 2. multi-allele in one run ################"
"$PAN/netMHCpan" -a HLA-A02:01,HLA-A24:02,HLA-B07:02 -p /tmp/usage/x.pep > "$W/multi.out" 2>&1
echo "  distinct alleles scored:"
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/multi.out" | awk '{print $2}' | sort -u | sed 's/^/    /'
echo
echo "################ 3. sort by affinity (-s) ################"
"$PAN/netMHCpan" -a HLA-A02:01 -p /tmp/usage/x.pep -s > "$W/sorted.out" 2>&1
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/sorted.out" | sed 's/^/    /'
echo
echo "################ 4. filter to binders only (-t 2) ################"
"$PAN/netMHCpan" -a HLA-A02:01 -p /tmp/usage/x.pep -t 2 > "$W/t2.out" 2>&1
echo "  rows with -t 2  : $(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/t2.out")"
"$PAN/netMHCpan" -a HLA-A02:01 -p /tmp/usage/x.pep > "$W/tall.out" 2>&1
echo "  rows default    : $(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/tall.out")"
echo
echo "################ 5. xls export opens as a real spreadsheet ################"
"$PAN/netMHCpan" -a HLA-A02:01 -p /tmp/usage/x.pep -BA -xls -xlsfile "$W/out.xls" > /dev/null 2>&1
echo "  size=$(stat -c %s "$W/out.xls") B  type=$(file -b "$W/out.xls")"
head -3 "$W/out.xls" | cut -c1-160 | sed 's/^/    /'
echo
echo "################ 6. stabpan sorting -s 0/1/2 ################"
for s in 0 1 2; do
    "$STAB/netMHCstabpan" -ia -a HLA-A02:01 -p /tmp/usage/x.pep -s $s > "$W/s$s.out" 2>&1
    echo "  -s $s -> $(grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/s$s.out" | awk '{printf "%s(%s) ", $3, $(NF-6)}')"
done
