#!/usr/bin/env bash
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
export TMPDIR=$PAN/tmp
printf 'SLYNTVATL AAAASLYNTVATLGGG HLA-A02:01\nGILGFVFTL AAAAGILGFVFTLGGG HLA-A02:01\n' > /tmp/smoke_ctx.txt

echo "############ trace netMHCpan_ctx ############"
bash -x /usr/local/bin/netMHCpan_ctx -f /tmp/smoke_ctx.txt 2>&1 | tail -40
echo
echo "############ manual equivalent ############"
W=/tmp/man_ctx; rm -rf "$W"; mkdir -p "$W"
awk '{print $3}' /tmp/smoke_ctx.txt | sort -u
a=HLA-A02:01
awk -v al="$a" '$3==al {print $1, $2}' /tmp/smoke_ctx.txt > "$W/in.txt"
echo "--- input to subprocess ---"; cat "$W/in.txt" | sed 's/^/    /'
"$PAN/netMHCpan" -p -context -a "$a" -f "$W/in.txt" > "$W/out.txt" 2>&1
echo "subprocess exit=$?"
grep -E '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/out.txt" | sed 's/^/    /' || echo "    (no data rows)"
echo "--- tail of subprocess output ---"
tail -6 "$W/out.txt" | sed 's/^/    /'
