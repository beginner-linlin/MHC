#!/usr/bin/env bash
# Practical workflow tests (self-contained: builds its own inputs).
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
STAB=/opt/bio/netMHCstabpan-1.0
W=/tmp/workflow; rm -rf "$W"; mkdir -p "$W"

printf 'SLYNTVATL\nGILGFVFTL\nILKEPVHGV\n' > "$W/pep.txt"
cat > "$W/prot.fsa" <<'EOF'
>sp_P01730_example_protein
MLLSVPLLLGLLGLAVGQCSVSWQPPPEKLLSEEDLLVHCSGKV
EOF

echo "################ 1. peptide file -> netMHCpan ################"
"$PAN/netMHCpan" -a HLA-A02:01 -p "$W/pep.txt" > "$W/pan.out" 2>&1
echo "  exit=$?  rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan.out")"
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan.out" | sed 's/^/    /'
echo
echo "################ 2. protein FASTA -> netMHCpan (sliding 9mers) ################"
"$PAN/netMHCpan" -a HLA-A02:01 -f "$W/prot.fsa" > "$W/pan_fsa.out" 2>&1
echo "  exit=$?  rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan_fsa.out")"
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan_fsa.out" | head -3 | sed 's/^/    /'
echo
echo "################ 3. multi-allele ################"
"$PAN/netMHCpan" -a HLA-A02:01,HLA-A24:02,HLA-B07:02 -p "$W/pep.txt" > "$W/multi.out" 2>&1
echo "  exit=$?  rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/multi.out")"
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/multi.out" | awk '{print "    "$2}' | sort | uniq -c
echo
echo "################ 4. sort (-s) and filter (-t 2) ################"
"$PAN/netMHCpan" -a HLA-A02:01 -p "$W/pep.txt" -s > "$W/sorted.out" 2>&1
echo "  sorted output:"; grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/sorted.out" | sed 's/^/    /'
"$PAN/netMHCpan" -a HLA-A02:01 -p "$W/pep.txt" -t 2 > "$W/t2.out" 2>&1
echo "  -t 2 rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/t2.out")  (default rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan.out"))"
echo
echo "################ 5. xls export ################"
"$PAN/netMHCpan" -a HLA-A02:01 -p "$W/pep.txt" -BA -xls -xlsfile "$W/out.xls" > "$W/xls.log" 2>&1
if [ -f "$W/out.xls" ]; then
    echo "  size=$(stat -c %s "$W/out.xls") B"
    file -b "$W/out.xls" | sed 's/^/  type: /'
    head -2 "$W/out.xls" | cut -c1-150 | sed 's/^/    /'
else
    echo "  NOT CREATED"; tail -3 "$W/xls.log" | sed 's/^/    /'
fi
echo
echo "################ 6. stabpan sort -s 0/1/2 ################"
for s in 0 1 2; do
    "$STAB/netMHCstabpan" -ia -a HLA-A02:01 -p "$W/pep.txt" -s $s > "$W/s$s.out" 2>&1
    echo "  -s $s : $(grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/s$s.out" | awk '{printf "%s ", $3}')"
done
