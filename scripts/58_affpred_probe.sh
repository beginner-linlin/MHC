#!/usr/bin/env bash
# What exact command does netMHCstabpan run against the -affpred binary?
# If it is a simple CLI translation, a shim can map it onto netMHCpan-4.2.
set -uo pipefail
STAB=/opt/bio/netMHCstabpan-1.0
W=/tmp/affpred_probe
rm -rf "$W"; mkdir -p "$W"

echo "############ strings around -ic50 in the stabpan binary ############"
strings -a "$STAB/Linux_x86_64/bin/netMHCstabpan" | grep -nE '\-ic50|\-affpred|\-a |%s .*%s' | head -20
echo

echo "############ build a logging shim and point -affpred at it ############"
cat > "$W/fakepan" <<'EOF'
#!/usr/bin/env bash
{ echo "=== INVOKED ==="; echo "argv:"; for a in "$@"; do echo "  [$a]"; done; } >> /tmp/affpred_probe/calls.log
# feed back a plausible response so stabpan continues
exit 0
EOF
chmod +x "$W/fakepan"
: > "$W/calls.log"

cd "$STAB/test" || exit 1
export NETMHCstabpan="$STAB/Linux_x86_64"
export TMPDIR="$STAB/tmp"
"$STAB/Linux_x86_64/bin/netMHCstabpan" -ia -p test.pep -affpred "$W/fakepan" > "$W/run.out" 2>&1
echo "exit=$?"
echo
echo "############ captured invocation(s) ############"
cat "$W/calls.log"
echo
echo "############ first 8 lines of stabpan output ############"
head -8 "$W/run.out"
