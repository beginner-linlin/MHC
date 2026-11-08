#!/usr/bin/env bash
# Same as 49 but match the execve whose PATH is the nnalign binary (the previous
# attempt matched /bin/sh because the command string also mentions nnalign).
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/ctx_argv
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp
cd "$T" || exit 1

cap() {
    local tag=$1; shift
    strace -f -e trace=execve -s 8000 "$PAN/netMHCpan" "$@" -dirty -tdir "$W/${tag}_XXXXXX" 2>&1 \
      | grep -E 'execve\("[^"]*nnalign' | grep -v ENOENT | grep -v resumed | head -1 > "$W/$tag.raw"
    if [ ! -s "$W/$tag.raw" ]; then echo "  !! no nnalign execve captured"; return 1; fi
    python3 - "$W/$tag.raw" "$W/$tag.cmd" <<'PY'
import sys, re, ast
raw = open(sys.argv[1]).read()
m = re.search(r'execve\("([^"]+)", (\[.*?\]), ', raw, re.S)
argv = ast.literal_eval(m.group(2))
cmd = argv[2] if len(argv) > 2 else ""
cmd = re.sub(r'\s*\|\s*grep\s+-v\s+"#"\s*$', '', cmd)
open(sys.argv[2], 'w').write(cmd)
print("  nnalign binary: %s" % argv[0].rsplit('/',1)[-1])
PY
}

echo "############ -p -context (WORKS) ############"
cap pctx -p -context test.pep_context
echo "############ -pmhc -context (FAILS) ############"
cap mctx -pmhc -context test.pep_context_mhc
echo
echo "############ diff (tmpdir normalized), one token per line ############"
sed -E 's#/tmp/ctx_argv/[pm]ctx_[A-Za-z0-9]+#<TMP>#g' "$W/pctx.cmd" | tr ' ' '\n' > "$W/a.n"
sed -E 's#/tmp/ctx_argv/[pm]ctx_[A-Za-z0-9]+#<TMP>#g' "$W/mctx.cmd" | tr ' ' '\n' > "$W/b.n"
diff "$W/a.n" "$W/b.n" || true
echo
echo "############ full failing command ############"
cat "$W/mctx.cmd"
