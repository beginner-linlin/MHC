#!/usr/bin/env bash
# Compare the resolved parameter headers of all four input modes, looking for a
# parameter that differs between the working -p -context run and the failing
# -pmhc -context run (e.g. which synlist is used).
set -uo pipefail
PAN=/opt/bio/netMHCpan-4.2
T=$PAN/test
W=/tmp/hdr
rm -rf "$W"; mkdir -p "$W"
export TMPDIR=$PAN/tmp
cd "$T" || exit 1

hdr() {
    local tag="$1"; shift
    "$PAN/netMHCpan" "$@" 2>&1 | grep -E '^\#\s+\[-' | sed -E 's/^\#\s+//' > "$W/$tag.hdr"
    echo "$tag: $(wc -l < "$W/$tag.hdr") params"
}

hdr p           -p test.pep
hdr p_ctx       -p -context test.pep_context
hdr pmhc        -pmhc test.pep_mhc
hdr pmhc_ctx    -pmhc -context test.pep_context_mhc

echo
echo "############ params that DIFFER between -p -context (works) and -pmhc -context (fails) ############"
diff "$W/p_ctx.hdr" "$W/pmhc_ctx.hdr" || true
echo
echo "############ params that DIFFER between -p (works) and -pmhc (works after fix) ############"
diff "$W/p.hdr" "$W/pmhc.hdr" || true
echo
echo "############ full -pmhc -context header ############"
cat "$W/pmhc_ctx.hdr"
