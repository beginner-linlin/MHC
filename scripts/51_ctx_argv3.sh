#!/usr/bin/env bash
# Dump the FULL argv of the nnalign child for both context modes.
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/ctx_argv
export TMPDIR=$PAN/tmp
cd "$T" || exit 1

cap() {
    local tag=$1; shift
    strace -f -e trace=execve -s 8000 "$PAN/netMHCpan" "$@" -dirty -tdir "$W/${tag}_XXXXXX" 2>&1 \
      | grep -E 'execve\("[^"]*nnalign' | grep -v ENOENT | grep -v resumed | head -1 > "$W/$tag.raw"
    python3 - "$W/$tag.raw" "$W/$tag.argv" <<'PY'
import sys, re, ast
raw = open(sys.argv[1]).read()
m = re.search(r'execve\("([^"]+)", (\[.*?\]), ', raw, re.S)
argv = ast.literal_eval(m.group(2))
open(sys.argv[2], 'w').write("\n".join(argv))
print("  argv[0]: %s   (%d elements)" % (argv[0].rsplit('/',1)[-1], len(argv)))
PY
}

echo "############ -p -context (WORKS) ############"
cap pctx -p -context test.pep_context
echo "############ -pmhc -context (FAILS) ############"
cap mctx -pmhc -context test.pep_context_mhc
echo
echo "############ token-by-token diff (tmpdir normalized) ############"
sed -E 's#/tmp/ctx_argv/[pm]ctx_[A-Za-z0-9]+#<TMP>#g' "$W/pctx.argv" > "$W/a.n"
sed -E 's#/tmp/ctx_argv/[pm]ctx_[A-Za-z0-9]+#<TMP>#g' "$W/mctx.argv" > "$W/b.n"
diff "$W/a.n" "$W/b.n" && echo "  (identical apart from tmpdir)"
echo
echo "############ full argv, -pmhc -context ############"
cat -n "$W/mctx.argv"
echo
echo "############ full argv, -p -context ############"
cat -n "$W/pctx.argv"
