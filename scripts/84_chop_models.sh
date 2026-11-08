#!/usr/bin/env bash
set -uo pipefail
CHOP=/opt/bio/netchop-3.1
W=/tmp/usage3; rm -rf "$W"; mkdir -p "$W"
cat > "$W/p.fsa" <<'EOF'
>test_protein
MLLSVPLLLGLLGLAVGQCSVSWQPPPEKLLSEEDL
EOF
echo "################ do Cterm (v0) and 20S (v1) actually differ? ################"
TMPDIR=$CHOP/tmp "$CHOP/netchop" -v 0 "$W/p.fsa" 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+[A-Z]' > "$W/a.txt"
TMPDIR=$CHOP/tmp "$CHOP/netchop" -v 1 "$W/p.fsa" 2>&1 | grep -E '^[[:space:]]*[0-9]+[[:space:]]+[A-Z]' > "$W/b.txt"
echo "  v0 rows=$(wc -l < "$W/a.txt")  v1 rows=$(wc -l < "$W/b.txt")"
if diff -q "$W/a.txt" "$W/b.txt" >/dev/null; then echo "  IDENTICAL"; else
  echo "  DIFFERENT (first 4 diffs):"; diff "$W/a.txt" "$W/b.txt" | head -8 | sed 's/^/    /'
fi
echo
echo "  v0 first 5:"; head -5 "$W/a.txt" | sed 's/^/    /'
echo "  v1 first 5:"; head -5 "$W/b.txt" | sed 's/^/    /'
echo
echo "################ Cterm vs 20S: which residues get S? ################"
echo "  v0 S positions: $(awk '$3=="S"{printf "%s ",$1}' "$W/a.txt")"
echo "  v1 S positions: $(awk '$3=="S"{printf "%s ",$1}' "$W/b.txt")"
