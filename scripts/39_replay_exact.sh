#!/usr/bin/env bash
# Replay the EXACT captured shell command for -p and -pmhc, then inspect the
# tmpdirs they leave behind (-dirty keeps them).
set -uo pipefail
W=/tmp/argv_exp
BIN=/opt/bio/netMHCpan-4.2/Linux_x86_64/bin

# Extract the sh -c payload from the captured execve line, then strip the
# trailing "| grep -v #" so we can inspect raw output ourselves.
extract_cmd() {
    python3 - "$1" <<'PY'
import sys, re, ast
raw = open(sys.argv[1]).read()
m = re.search(r'execve\("([^"]+)", (\[.*?\]), ', raw, re.S)
argv = ast.literal_eval(m.group(2))
# argv = ['/bin/sh', '-c', '<command line>', ...]
cmd = argv[2]
# drop the shell pipe suffix so we get the raw nnalign invocation
cmd = re.sub(r'\s*\|\s*grep\s+-v\s+"#"\s*$', '', cmd)
print(cmd)
PY
}

P_CMD=$(extract_cmd "$W/p.raw")
M_CMD=$(extract_cmd "$W/pmhc.raw")

echo "################ the -pmhc command the wrapper actually runs ################"
echo "$M_CMD"
echo
echo "################ differences vs the working -p command ################"
diff <(echo "$P_CMD" | tr ' ' '\n') <(echo "$M_CMD" | tr ' ' '\n')
echo

echo "################ tmpdirs left behind (-dirty) ################"
for d in "$W"/p_* "$W"/m_*; do
    [ -d "$d" ] || continue
    echo "--- $d"
    ls -la "$d" | head -20
    echo "    allelelist: $(cat "$d/allelelist" 2>/dev/null | tr '\n' ' ')"
    echo "    0.dat:      $(cat "$d/0.dat" 2>/dev/null | tr '\n' ' ')"
done
