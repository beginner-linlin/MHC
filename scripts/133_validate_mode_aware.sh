#!/usr/bin/env bash
set -uo pipefail
APP=/opt/bio/app
PY=$APP/venv/bin/python
cd "$APP" || exit 1
export MHC_APP_ROOT="$APP"
"$PY" - <<'PYEOF'
import sys, os
sys.path.insert(0, "/opt/bio/app")
os.environ.setdefault("MHC_APP_ROOT", "/opt/bio/app")
from mhc.web import app
c = app.test_client()

probes = [
    # (label, payload, 期望 error 级别出现的 code)
    ("pan 短肽 GILGF",        {"input": "GILGF",   "input_mode": "peptide", "mode": "pan",  "alleles": ["HLA-A02:01"]}, "too_short"),
    ("stab 短肽 GILGF",       {"input": "GILGF",   "input_mode": "peptide", "mode": "stab", "alleles": ["HLA-A02:01"]}, "stab_short"),
    ("stab 长肽 25aa",        {"input": "GILGFVFTLTVPSERGLQVQRNY", "input_mode": "peptide", "mode": "stab", "alleles": ["HLA-A02:01"]}, "stab_long"),
    ("chop 1 残基蛋白",        {"input": ">x\nM",   "input_mode": "fasta",   "mode": "chop"}, None),
    ("chop 3 残基蛋白",        {"input": ">x\nMKT", "input_mode": "fasta",   "mode": "chop"}, None),
    ("pan 蛋白 5aa",          {"input": ">x\nGILGF", "input_mode": "fasta", "mode": "pan",  "alleles": ["HLA-A02:01"]}, "protein_too_short"),
    ("pipeline 肽长10 需10aa", {"input": ">x\nGILGFVFTL", "input_mode": "fasta", "mode": "pipeline", "alleles": ["HLA-A02:01"], "min_peptide_len": 10}, "protein_too_short"),
    ("pan 正常 9mer",         {"input": "SLYNTVATL", "input_mode": "peptide", "mode": "pan", "alleles": ["HLA-A02:01"]}, None),
    ("无 mode 的旧调用兼容",    {"input": "GILGF",   "input_mode": "peptide", "alleles": ["HLA-A02:01"]}, "too_short"),
]
ok = 0; bad = 0
for label, payload, want_code in probes:
    r = c.post("/api/validate/input", json=payload)
    d = r.get_json() or {}
    codes = [w.get("code") for w in (d.get("warnings") or [])]
    levels = {w.get("code"): w.get("level") for w in (d.get("warnings") or [])}
    if want_code is None:
        has_err = any(w.get("level") == "error" for w in (d.get("warnings") or []))
        good = not has_err
        detail = f"warnings={codes}" if codes else "无警告"
    else:
        good = want_code in codes
        detail = f"got={codes} levels={levels}"
    print(f"  {'✔' if good else '✘'} {label:26} {detail}")
    ok += good; bad += (not good)
print(f"\n通过 {ok} / {ok+bad}")
sys.exit(1 if bad else 0)
PYEOF
