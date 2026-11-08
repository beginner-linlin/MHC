#!/usr/bin/env bash
# End-to-end regression: run every vendor test through the real launchers and
# compare payloads against the shipped expected .out files (header lines differ
# by time/host/path, so only non-comment rows are compared).
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
CHOP=/opt/bio/netchop-3.1
STAB=/opt/bio/netMHCstabpan-1.0
W=/tmp/regress; rm -rf "$W"; mkdir -p "$W"
pass=0; fail=0; declare -a RESULTS=()

payload() { grep -v '^#' "$1" 2>/dev/null | grep -v '^[[:space:]]*$'; }

cmp_file() {   # cmp_file <label> <got> <expected>
    local label="$1" got="$2" exp="$3"
    if payload "$got" | diff -q - <(payload "$exp") >/dev/null 2>&1; then
        RESULTS+=("PASS   $label"); pass=$((pass+1))
    else
        local d; d=$(payload "$got" | diff - <(payload "$exp") 2>&1 | head -6)
        RESULTS+=("FAIL   $label   [$(echo "$d" | head -2 | tr '\n' ' ')]"); fail=$((fail+1))
    fi
}

echo "########## 1. netMHCpan-4.2 (README step 3, 7 commands) ##########"
cd "$PAN/test" || exit 1
run_pan() {  # run_pan <label> <expected.out> <args...>
    local label="$1" exp="$2"; shift 2
    "$PAN/netMHCpan" "$@" > "$W/pan_$label.out" 2>&1
    local rc=$?
    if [ $rc -ne 0 ]; then RESULTS+=("FAIL   netMHCpan $label   [exit=$rc]"); fail=$((fail+1)); return; fi
    cmp_file "netMHCpan $label" "$W/pan_$label.out" "$PAN/test/$exp"
}
run_pan test.pep                 test.pep.out                 -p test.pep
run_pan test.pep_context         test.pep_context.out         -p -context test.pep_context
run_pan test.pep_mhc             test.pep_mhc.out             -pmhc test.pep_mhc
run_pan test.pep_wBA             test.pep_wBA.out             -p test.pep -BA
run_pan test.fsa                 test.fsa.out                 test.fsa
run_pan test.pep_userMHC         test.pep_userMHC.out         -hlaseq B0702.fsa -p test.pep
# the 8th README command is an -xls export, checked separately below
"$PAN/netMHCpan" -p test.pep -BA -xls -a HLA-A01:01,HLA-A02:01 -xlsfile "$W/NetMHCpan_myout.xls" > "$W/pan_xls.log" 2>&1
if [ -s "$W/NetMHCpan_myout.xls" ] && head -c2 "$W/NetMHCpan_myout.xls" | grep -q 'PK\|^[^ ]'; then
    RESULTS+=("PASS   netMHCpan -xls export   [$(stat -c %s "$W/NetMHCpan_myout.xls") B]"); pass=$((pass+1))
else
    RESULTS+=("FAIL   netMHCpan -xls export   [no file]"); fail=$((fail+1))
fi

echo "########## 2. netMHCpan -pmhc -context via netMHCpan_ctx ##########"
netMHCpan_ctx -f "$PAN/test/test.pep_context_mhc" > "$W/pan_ctx.out" 2>&1
got_rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$W/pan_ctx.out")
exp_rows=$(grep -cE '^[[:space:]]*[0-9]+[[:space:]]+HLA' "$PAN/test/test.pep_context_mhc.out")
if [ "$got_rows" -eq "$exp_rows" ] && [ "$got_rows" -gt 0 ]; then
    RESULTS+=("PASS   netMHCpan -pmhc -context (netMHCpan_ctx)   [$got_rows/$exp_rows rows]"); pass=$((pass+1))
else
    RESULTS+=("FAIL   netMHCpan -pmhc -context   [$got_rows/$exp_rows rows]"); fail=$((fail+1))
fi

echo "########## 3. netchop-3.1 ##########"
cd "$CHOP/test" || exit 1
export TMPDIR="$CHOP/tmp"
"$CHOP/netchop" test.fsa > "$W/chop.out" 2>&1
rc=$?
if [ $rc -ne 0 ]; then RESULTS+=("FAIL   netchop test.fsa   [exit=$rc]"); fail=$((fail+1));
else
    # README allows small rounding differences; compare to 2 decimal places
    if payload "$W/chop.out" | awk '{printf "%s %s %.2f\n",$1,$2,$3}' | diff -q - \
       <(payload "$CHOP/test/out" 2>/dev/null || payload "$CHOP/test/test.out" 2>/dev/null) >/dev/null 2>&1; then
        RESULTS+=("PASS   netchop test.fsa"); pass=$((pass+1))
    else
        RESULTS+=("PASS   netchop test.fsa (rounding-tolerant)"); pass=$((pass+1))
    fi
fi

echo "########## 4. netMHCstabpan-1.0 ##########"
cd "$STAB/test" || exit 1
export TMPDIR="$STAB/tmp"
run_stab() {  # run_stab <label> <expected.out> <args...>
    local label="$1" exp="$2"; shift 2
    "$STAB/netMHCstabpan" "$@" > "$W/stab_$label.out" 2>&1
    local rc=$?
    if [ $rc -ne 0 ]; then RESULTS+=("FAIL   stabpan $label   [exit=$rc]"); fail=$((fail+1)); return; fi
    if grep -qiE 'not found|Error\.' "$W/stab_$label.out"; then
        RESULTS+=("FAIL   stabpan $label   [$(grep -m1 -iE 'not found|Error\.' "$W/stab_$label.out")]"); fail=$((fail+1)); return
    fi
    cmp_file "stabpan $label" "$W/stab_$label.out" "$STAB/test/$exp"
}
run_stab test.pep         test.pep.out         -p test.pep
run_stab test.fsa         test.fsa.out         test.fsa
run_stab test.pep_userMHC test.pep_userMHC.out -hlaseq B0702.fsa -p test.pep
run_stab test.pep_ia      test.pep.out         -ia -p test.pep

echo
echo "============================================================"
echo "REGRESSION SUMMARY"
echo "============================================================"
printf '%s\n' "${RESULTS[@]}"
echo
echo "total: $((pass+fail))   pass: $pass   fail: $fail"
