#!/bin/bash
# 针对首轮 4 个问题的定向复测
set -u
cd /opt/bio/app || exit 1
export MHC_APP_ROOT=/opt/bio/app
PY=/opt/bio/app/venv/bin/python

$PY - <<'PY'
import sys, time, json
sys.path.insert(0, "/opt/bio/app")
from mhc.web import app, store
c = app.test_client()

def wait(jid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{jid}").get_json()["job"]
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.4)
    raise TimeoutError(jid)

print("=" * 70)
print("修复 1：流水线 cut_pos / cut_score")
print("=" * 70)
r = c.post("/api/jobs/pipeline", json={
    "input": ">test_protein\nMLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV",
    "input_mode": "fasta",
    "alleles": ["HLA-A02:01"],
    "cleavage_threshold": 0.5,
    "cleavage_model": 0,
    "peptide_lengths": [9],
    "use_cleavage_filter": True,
    "max_rank_el": 2.0,
    "min_thalf": 0,
})
jid = r.get_json()["job"]["id"]
j = wait(jid)
print("状态:", j["status"], " 标题:", j["title"])
rows = j["result"]["rows"]
print(f"共 {len(rows)} 行；cut_pos / cut_score：")
ok = True
for row in rows:
    print(f"  {row['protein']:14s} cut_pos={row['cut_pos']:<4} cut_score={row['cut_score']}  "
          f"{row['peptide']} {row['mhc']} rank_el={row['rank_el']}")
    if not row["cut_pos"]:
        ok = False
print("  >> 全部有 cut_pos:", ok)

# 校验 cut_pos 语义：肽的 C 端是否正好是该切割位点
seq = "MLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV"
# 从 netchop 结果独立核对
chop = c.post("/api/jobs/chop", json={
    "input": ">test_protein\n" + seq, "input_mode": "fasta", "model": 0, "threshold": 0.5
}).get_json()["job"]["id"]
cj = wait(chop)
sites = {x["pos"] for x in cj["result"]["rows"] if x["cleavage"] == "S"}
print(f"  netchop 报的 S 位点: {sorted(sites)}")
for row in rows:
    pep, cp = row["peptide"], row["cut_pos"]
    idx = seq.find(pep)
    end1 = idx + len(pep)  # 1-based 末位
    print(f"    {pep} 起点={idx+1} 末位={end1} cut_pos={cp} 末位是S位点={end1 in sites}")

print()
print("=" * 70)
print("修复 2：突变任务标题与导出")
print("=" * 70)
ref = seq
alt = ref[:10] + "W" + ref[11:]
r = c.post("/api/jobs/mutant", json={
    "ref_seq": ref, "alt_seq": alt,
    "alleles": ["HLA-A02:01"], "peptide_lengths": [9],
})
d = r.get_json()
jid2 = d["job"]["id"]
print("标题:", d["job"]["title"])
j2 = wait(jid2)
print("状态:", j2["status"], " 行数:", len(j2["result"]["rows"]))
print("  首行:", json.dumps(j2["result"]["rows"][0], ensure_ascii=False))
for fmt in ("csv", "xlsx"):
    rr = c.get(f"/api/jobs/{jid2}/export?format={fmt}")
    print(f"  {fmt}: {rr.status_code} {len(rr.get_data())} bytes magic={rr.get_data()[:4]!r}")

# 完全相同序列应立即 400
r = c.post("/api/jobs/mutant", json={
    "ref_seq": ref, "alt_seq": ref, "alleles": ["HLA-A02:01"], "peptide_lengths": [9],
})
print("  相同序列:", r.status_code, r.get_json().get("error"))

print()
print("=" * 70)
print("修复 3：空输入应同步 400")
print("=" * 70)
for path, payload, label in [
    ("/api/jobs/pan", {"input": "", "input_mode": "peptide", "alleles": ["HLA-A02:01"]}, "pan 空输入"),
    ("/api/jobs/stab", {"input": "   \n\n  ", "alleles": ["HLA-A02:01"]}, "stab 空白输入"),
    ("/api/jobs/pan", {"alleles": ["HLA-A02:01"]}, "pan 无 input 字段"),
    ("/api/jobs/pipeline", {"input": "", "alleles": ["HLA-A02:01"]}, "pipeline 空输入"),
]:
    rr = c.post(path, json=payload)
    print(f"  {label}: {rr.status_code} ok={rr.get_json().get('ok')} {str(rr.get_json().get('error'))[:60]}")

print()
print("=" * 70)
print("修复 4：netchop 版本")
print("=" * 70)
h = c.get("/api/health").get_json()
print(json.dumps(h["tools"], ensure_ascii=False, indent=2))

print()
print("=" * 70)
print("回归：5 个模式各跑一次确认没弄坏")
print("=" * 70)
cases = [
    ("pan", {"input": "SLYNTVATL\nGILGFVFTL", "alleles": ["HLA-A02:01"], "with_ba": True}),
    ("chop", {"input": ">p\n" + seq, "input_mode": "fasta", "model": 0, "threshold": 0.5}),
    ("stab", {"input": "SLYNTVATL\nGILGFVFTL", "alleles": ["HLA-A02:01"], "with_ia": True}),
    ("pipeline", {"input": ">p\n" + seq, "input_mode": "fasta", "alleles": ["HLA-A02:01"],
                  "peptide_lengths": [9, 10], "use_cleavage_filter": False, "max_rank_el": 5.0}),
    ("mutant", {"ref_seq": ref, "alt_seq": alt, "alleles": ["HLA-A02:01"], "peptide_lengths": [9, 10]}),
]
allok = True
for kind, payload in cases:
    rr = c.post(f"/api/jobs/{kind}", json=payload)
    if not rr.get_json().get("ok"):
        print(f"  {kind}: 提交失败 {rr.get_json().get('error')}")
        allok = False
        continue
    jj = wait(rr.get_json()["job"]["id"])
    n = len((jj.get("result") or {}).get("rows") or [])
    flag = "OK " if jj["status"] == "done" and n > 0 else "BAD"
    if flag == "BAD":
        allok = False
    print(f"  {flag} {kind:9s} {jj['status']:9s} {n:3d} 行  {jj['seconds']:.2f}s  {jj['title']}")
print("\n全部通过:", allok)
print("历史总数:", store.count())
PY
