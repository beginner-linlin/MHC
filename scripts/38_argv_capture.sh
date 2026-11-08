#!/usr/bin/env bash
# Definitive controlled experiment: capture the EXACT argv of the nnalign child
# for -p (works) and -pmhc (fails), then replay each argv verbatim.
set -uo pipefail
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin
W=/tmp/argv_exp
rm -rf "$W"; mkdir -p "$W"

capture_argv() {
    local tag=$1; shift
    local out="$W/$tag.argv"
    # -dirty keeps the tmpdir so we can replay against the same inputs
    strace -f -e trace=execve -s 4000 /opt/bio/netMHCpan-4.2/netMHCpan "$@" 2>&1 \
      | grep 'execve' | grep 'nnalign' | grep -v ENOENT | grep -v 'resumed' \
      | head -1 > "$W/$tag.raw"
    python3 - "$W/$tag.raw" "$out" <<'PY'
import sys, re, ast
raw = open(sys.argv[1]).read()
m = re.search(r'execve\("([^"]+)", (\[.*?\]), ', raw, re.S)
if not m:
    print("NO MATCH"); sys.exit(1)
argv = ast.literal_eval(m.group(2))
with open(sys.argv[2], 'w') as f:
    for a in argv:
        f.write(a + "\n")
print("captured %d argv elements -> %s" % (len(argv), sys.argv[2]))
PY
}

cd /tmp || exit 1
printf 'SLYNTVATL 0.5\n' > "$W/good.pep"
printf 'SLYNTVATL HLA-A02:01 0.5\n' > "$W/bad.pmhc"

echo "############ capture -p argv ############"
capture_argv p -p "$W/good.pep" -dirty -tdir "/tmp/argv_exp/p_XXXXXX"

echo "############ capture -pmhc argv ############"
capture_argv pmhc -pmhc "$W/bad.pmhc" -dirty -tdir "/tmp/argv_exp/m_XXXXXX"

echo
echo "############ diff of the two argv (only expected to differ in tmpdir) ############"
sed -E 's#/tmp/argv_exp/[pm]_[A-Za-z0-9]+#<TMP>#g' "$W/p.argv" > "$W/p.norm"
sed -E 's#/tmp/argv_exp/[pm]_[A-Za-z0-9]+#<TMP>#g' "$W/pmhc.argv" > "$W/pmhc.norm"
diff "$W/p.norm" "$W/pmhc.norm" && echo "(argv identical apart from tmpdir)"
