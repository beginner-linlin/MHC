#!/usr/bin/env bash
# Final validation rules before building the app.
set -uo pipefail
W=/tmp/edge3; rm -rf $W; mkdir -p $W; cd $W

echo "############ A. stabpan accepted length range ############"
for L in 7 8 9 10 11 12 13 14 15 20; do
  python3 -c "print(('ACDEFGHIKLMNPQRSTVWY'*3)[:$L])" > t.pep
  out=$(netMHCstabpan -p t.pep -a HLA-A02:01 2>&1)
  if echo "$out" | grep -q 'Error'; then
    msg=$(echo "$out" | grep 'Error' | head -1 | cut -c1-70)
    printf '  len=%-2s ERROR: %s\n' "$L" "$msg"
  else
    n=$(echo "$out" | grep -c 'HLA-A\*')
    printf '  len=%-2s OK  rows=%s\n' "$L" "$n"
  fi
done

echo
echo "############ B. netMHCpan upper length ############"
for L in 8 9 10 11 12 15 20 30 40 50 60; do
  python3 -c "print(('ACDEFGHIKLMNPQRSTVWY'*4)[:$L])" > t2.pep
  out=$(netMHCpan -p t2.pep -a HLA-A02:01 2>&1)
  if echo "$out" | grep -qE 'Error|must be'; then
    printf '  len=%-2s ERR: %s\n' "$L" "$(echo "$out" | grep -E 'Error|must be' | head -1 | cut -c1-60)"
  else
    printf '  len=%-2s OK\n' "$L"
  fi
done

echo
echo "############ C. netchop: does X kill output? ############"
for ch in X B Z U '*' '-' '.' '1'; do
  printf '>s\nGILGFVFT%s\n' "$ch" > c.fsa
  n=$(netchop c.fsa 2>&1 | grep -cE '^ *[0-9]+ +[A-Z] +[S.] ')
  printf '  char=%-2s rows=%s\n' "$ch" "$n"
done

echo
echo "############ D. netchop: minimum sequence length ############"
for L in 3 5 8 9 10 12; do
  python3 -c "print('>s'); print(('ACDEFGHIKLMNPQRSTVWY'*2)[:$L])" > c2.fsa
  n=$(netchop c2.fsa 2>&1 | grep -cE '^ *[0-9]+ +[A-Z] +[S.] ')
  printf '  len=%-2s rows=%s\n' "$L" "$n"
done

echo
echo "############ E. netMHCpan: FASTA with lowercase and '*' stops ############"
printf '>lc\nmllsvplllgllgaaacss\n' > lc.fsa
netMHCpan -f lc.fsa -a HLA-A02:01 2>&1 | grep -E '^Protein|Error' | sed 's/^/  /'
printf '>stop\nMLLSVPLLL*\n' > st.fsa
netMHCpan -f st.fsa -a HLA-A02:01 2>&1 | grep -E '^Protein|Error' | sed 's/^/  /'

echo
echo "############ F. netchop output: is Ident truncated to 10 chars? ############"
printf '>AVERYLONGPROTEINNAME_XYZ\nMLLSVPLLLGLLGAAACSSNCGSS\n' > ln.fsa
netchop ln.fsa 2>&1 | grep -E '^Number' | sed 's/^/  /'

echo
echo "############ G. multiple alleles: how does output distinguish? ############"
printf 'GILGFVFTL\n' > o.pep
netMHCpan -p o.pep -a HLA-A02:01,HLA-B07:02 -BA 2>&1 | grep -E 'HLA-A\*|HLA-B\*' | sed 's/^/  /'

echo
echo "############ H. -t threshold semantics on netMHCpan ############"
for t in 0.5 2 5; do
  n=$(netMHCpan -p o.pep -a HLA-A02:01 -t $t 2>&1 | grep -cE 'HLA-A\*')
  echo "  -t $t -> $n rows (GILGFVFTL rank 0.197)"
done
