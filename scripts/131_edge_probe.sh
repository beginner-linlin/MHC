#!/usr/bin/env bash
set -uo pipefail
APP=/opt/bio/app
PY=$APP/venv/bin/python
cd "$APP" || exit 1
export MHC_APP_ROOT="$APP"

"$PY" - <<'PYEOF'
import sys, time, os
sys.path.insert(0, "/opt/bio/app")
os.environ.setdefault("MHC_APP_ROOT", "/opt/bio/app")
from mhc.web import app
c = app.test_client()

def wait(job_id, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = (c.get(f"/api/jobs/{job_id}").get_json() or {}).get("job") or {}
        if j.get("status") in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.15)
    return {"status": "timeout"}

probes = [
    ("坏等位基因 HLA-Q99:99", "pan", {"input": "SLYNTVATL", "input_mode": "peptide", "alleles": ["HLA-Q99:99"]}),
    ("单残基蛋白 >x\\nM", "chop", {"input": ">x\nM", "input_mode": "fasta"}),
    ("2 残基蛋白", "chop", {"input": ">x\nMK", "input_mode": "fasta"}),
    ("短肽 5 个残基给 pan", "pan", {"input": "GILGF", "input_mode": "peptide", "alleles": ["HLA-A02:01"]}),
    ("短肽 5 个残基给 stab", "stab", {"input": "GILGF", "input_mode": "peptide", "alleles": ["HLA-A02:01"]}),
    ("等位基因带星号", "pan", {"input": "SLYNTVATL", "input_mode": "peptide", "alleles": ["HLA-A*02:01"]}),
    ("等位基因无冒号", "pan", {"input": "SLYNTVATL", "input_mode": "peptide", "alleles": ["HLA-A0201"]}),
]
for label, kind, payload in probes:
    r = c.post(f"/api/jobs/{kind}", json=payload)
    d = r.get_json() or {}
    if not d.get("ok"):
        print(f"{label:32} → HTTP {r.status_code} 同步拒绝: {d.get('error')}")
        continue
    j = wait(d["job"]["id"])
    rows = ((j.get("result") or {}).get("rows") or [])
    err = j.get("error") or ""
    print(f"{label:32} → {j.get('status'):8} rows={len(rows):3} err={err[:110]}")
PYEOF
