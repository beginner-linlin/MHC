#!/usr/bin/env bash
# Full installation status check for the three DTU tools.
set -uo pipefail
BASE=/opt/bio
PAN=$BASE/netMHCpan-4.2
CHOP=$BASE/netchop-3.1
STAB=$BASE/netMHCstabpan-1.0

hr() { printf '%s\n' "============================================================"; }

hr; echo "PLATFORM"; hr
. /etc/os-release 2>/dev/null
echo "  distro      : ${PRETTY_NAME:-unknown}"
echo "  kernel      : $(uname -r)"
echo "  arch        : $(uname -m)"
echo "  tcsh        : $(command -v tcsh || echo MISSING)  $(tcsh --version 2>/dev/null | head -1)"
echo

for pair in "netMHCpan-4.2:$PAN" "netchop-3.1:$CHOP" "netMHCstabpan-1.0:$STAB"; do
    name=${pair%%:*}; dir=${pair##*:}
    hr; echo "PACKAGE: $name"; hr
    if [ ! -d "$dir" ]; then echo "  MISSING DIRECTORY: $dir"; echo; continue; fi
    echo "  path        : $dir"
    echo "  size        : $(du -sh "$dir" 2>/dev/null | cut -f1)"
    echo "  files       : $(find "$dir" -type f | wc -l)"
    echo "  version     : $(cat "$dir/data/version" 2>/dev/null || echo 'n/a')"
    echo "  launcher    : $dir/$name  $([ -x "$dir/$name" ] && echo '(executable)' || echo '(MISSING/not exec)')"
    echo "  NMHOME line : $(grep -m1 -n 'set *NMHOME' "$dir/$name" 2>/dev/null | sed 's/^ *//')"
    echo "  TMPDIR line : $(grep -m1 -n 'TMPDIR' "$dir/$name" 2>/dev/null | sed 's/^ *//')"
    echo "  tmp dir     : $([ -d "$dir/tmp" ] && echo "exists $(stat -c '%a' "$dir/tmp")" || echo MISSING)"
    echo "  binaries    :"
    ls -1 "$dir/Linux_x86_64/bin" 2>/dev/null | sed 's/^/      /'
done
echo

hr; echo "nnalign variant state (netMHCpan-4.2)"; hr
B=$PAN/Linux_x86_64/bin
for f in "$B"/nnalign*v3 "$B"/nnalign*v3.orig; do
    [ -e "$f" ] || continue
    printf '  %-95s %8s B  md5=%s\n' "$(basename "$f")" "$(stat -c %s "$f")" "$(md5sum "$f" | cut -c1-32)"
done
