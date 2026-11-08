#!/usr/bin/env bash
set -uo pipefail
APP=/opt/bio/app
PY=$APP/venv/bin/python
cd "$APP" || exit 1
export MHC_APP_ROOT="$APP"
"$PY" - <<'PYEOF'
import sys, time, os, json
sys.path.insert(0, "/opt/bio/app")
os.environ.setdefault("MHC_APP_ROOT", "/opt/bio/app")
from mhc.web import app
c = app.test_client()
def wait(jid, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = (c.get(f"/api/jobs/{jid}").get_json() or {}).get("job") or {}
        if j.get("status") in ("done","failed","cancelled"): return j
        time.sleep(0.15)
    return {"status":"timeout"}

for pep in ["GILGF", "GILGFVF", "GILGFVFT", "GILGFVFTL", "GILGFVFTLTVPSERGLQ"]:
    r = c.post("/api/jobs/stab", json={"input": pep, "input_mode":"peptide",
                                        "alleles":["HLA-A02:01"], "with_ia": True})
    d = r.get_json() or {}
    if not d.get("ok"):
        print(f"stab len={len(pep):2} {pep:22} → 同步拒绝 {d.get('error')}")
        continue
    j = wait(d["job"]["id"]); rows = ((j.get("result") or {}).get("rows") or [])
    print(f"stab len={len(pep):2} {pep:22} → {j.get('status'):7} rows={len(rows)} "
          + (json.dumps(rows[0], ensure_ascii=False)[:150] if rows else "err=" + str(j.get('error'))[:90]))

print()
for pep in ["GILGF", "GILGFVF", "GILGFVFT"]:
    r = c.post("/api/jobs/pan", json={"input": pep, "input_mode":"peptide",
                                       "alleles":["HLA-A02:01"], "with_ba": True})
    d = r.get_json() or {}
    if not d.get("ok"):
        print(f"pan  len={len(pep):2} {pep:22} → 同步拒绝 {d.get('error')}"); continue
    j = wait(d["job"]["id"]); rows = ((j.get("result") or {}).get("rows") or [])
    print(f"pan  len={len(pep):2} {pep:22} → {j.get('status'):7} rows={len(rows)} err={str(j.get('error'))[:90]}")

print("\n--- netchop 1 残基 / 2 残基的真实输出 ---")
for seq in ["M", "MK", "MKT"]:
    r = c.post("/api/jobs/chop", json={"input": f">x\n{seq}", "input_mode":"fasta", "model":0, "threshold":0.5})
    d = r.get_json() or {}
    j = wait(d["job"]["id"]); rows = ((j.get("result") or {}).get("rows") or [])
    print(f"chop len={len(seq)} {seq:4} → {j.get('status'):7} rows={len(rows)} {json.dumps(rows[:2], ensure_ascii=False)[:150]}")
PYEOF
