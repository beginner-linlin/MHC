#!/bin/bash
# 端到端功能测试：直接调用 Flask test_client，逐个接口跑真实工具
set -u
cd /opt/bio/app || exit 1
export MHC_APP_ROOT=/opt/bio/app
PY=/opt/bio/app/venv/bin/python

$PY - <<'PY'
import sys, json, time
sys.path.insert(0, "/opt/bio/app")
from mhc.web import app, store

c = app.test_client()

def show(title):
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)

def wait(job_id, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/api/jobs/{job_id}")
        j = r.get_json()["job"]
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.4)
    raise TimeoutError(job_id)

def run(path, payload, label):
    print(f"\n--- {label} ---")
    r = c.post(path, json=payload)
    d = r.get_json()
    if not d.get("ok"):
        print("  SUBMIT FAILED:", d.get("error"))
        return None
    jid = d["job"]["id"]
    print(f"  提交: {jid}  {d['job']['title']}")
    j = wait(jid)
    print(f"  状态: {j['status']}  耗时: {j['seconds']:.2f}s  行数: {len((j.get('result') or {}).get('rows') or [])}")
    if j["status"] != "done":
        print("  错误:", (j.get("error") or "")[:500])
        return None
    rows = j["result"]["rows"]
    for row in rows[:3]:
        print("   ", {k: v for k, v in list(row.items())[:6]})
    return j

# ───────────────────────────── 健康 ─────────────────────────────
show("1. /api/health")
h = c.get("/api/health").get_json()
print(json.dumps(h, ensure_ascii=False, indent=2)[:700])

show("2. /api/alleles 去重检查")
a = c.get("/api/alleles").get_json()
al = a["alleles"]
print(f"  总数 {a['total']}，返回 {len(al)}")
colon = [x for x in al if ":" in x]
plain = [x for x in al if ":" not in x]
print(f"  带冒号 {len(colon)}，无冒号 {len(plain)}")
print("  样例:", al[:5])
dup_check = len(al) == len(set(al))
print("  无重复:", dup_check)
# 检查 A02:01 与 A0201 是否都还在
both = [x for x in al if x.replace("HLA-","").replace(":","") == "A0201"]
print("  A*02:01 变体数（应为1）:", len(both), both)

# ───────────────────────────── PAN ─────────────────────────────
show("3. POST /api/jobs/pan  (多肽列表)")
run("/api/jobs/pan", {
    "input": "SLYNTVATL\nGILGFVFTL\nMLLSVPLLL",
    "input_mode": "peptide",
    "alleles": ["HLA-A02:01"],
    "with_ba": True,
}, "3a. 3 条肽 × A02:01")

run("/api/jobs/pan", {
    "input": ">test_protein\nMLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV",
    "input_mode": "fasta",
    "alleles": ["HLA-A02:01", "HLA-A24:02"],
    "with_ba": True,
}, "3b. FASTA 27aa × 2 alleles")

run("/api/jobs/pan", {
    "input": "SLYNTVATL\nGILGFVFTL",
    "input_mode": "peptide",
    "alleles": ["HLA-A02:01"],
    "with_ba": True,
    "threshold": 0.5,
}, "3c. 带阈值过滤")

run("/api/jobs/pan", {
    "input": "AAAAAAAAA\nCCCCCCCCC",
    "input_mode": "peptide",
    "alleles": ["HLA-B07:02"],
    "with_ba": True,
    "sort": True,
}, "3d. 低亲和力肽 × B07:02 + 排序")

# ───────────────────────────── CHOP ─────────────────────────────
show("4. POST /api/jobs/chop")
run("/api/jobs/chop", {
    "input": ">test_protein\nMLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV",
    "input_mode": "fasta",
    "model": 0,
    "threshold": 0.5,
}, "4a. Cterm 模型 t=0.5")

run("/api/jobs/chop", {
    "input": ">test_protein\nMLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV",
    "input_mode": "fasta",
    "model": 1,
    "threshold": 0.5,
}, "4b. 20S 模型 t=0.5")

# ───────────────────────────── STAB ─────────────────────────────
show("5. POST /api/jobs/stab")
run("/api/jobs/stab", {
    "input": "SLYNTVATL\nGILGFVFTL\nMLLSVPLLL",
    "input_mode": "peptide",
    "alleles": ["HLA-A02:01"],
    "with_ia": True,
}, "5a. 同长度肽 + ia")

run("/api/jobs/stab", {
    "input": "SLYNTVATL\nGILGFVFTLV\nMLLSVPLLLG",
    "input_mode": "peptide",
    "alleles": ["HLA-A02:01"],
    "with_ia": True,
}, "5b. 混合长度肽（应自动分组）")

# ───────────────────────────── PIPELINE ─────────────────────────────
show("6. POST /api/jobs/pipeline")
j = run("/api/jobs/pipeline", {
    "input": ">test_protein\nMLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV",
    "input_mode": "fasta",
    "alleles": ["HLA-A02:01"],
    "cleavage_threshold": 0.5,
    "cleavage_model": 0,
    "peptide_lengths": [9],
    "use_cleavage_filter": True,
    "max_rank_el": 2.0,
    "min_thalf": 0,
}, "6a. 三步串联（切割位点筛肽）")
if j:
    r = j["result"]
    print("  步骤:")
    for s in r["steps"]:
        print(f"    {s['label']}: {s['rows_in']} -> {s['rows_out']}  {s['seconds']}s  {s['note']}")
    print("  汇总:", r["summary"])

run("/api/jobs/pipeline", {
    "input": ">test_protein\nMLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV",
    "input_mode": "fasta",
    "alleles": ["HLA-A02:01", "HLA-A24:02"],
    "cleavage_threshold": 0.5,
    "peptide_lengths": [9, 10],
    "use_cleavage_filter": False,
    "max_rank_el": 5.0,
    "min_thalf": 0,
}, "6b. 全滑窗 + 双肽长 + 2 alleles")

# ───────────────────────────── MUTANT ─────────────────────────────
show("7. POST /api/jobs/mutant")
ref = "MLLSVPLLLGLLGAAACSSNCGSSKLVALGINAV"
alt = ref[:10] + "W" + ref[11:]   # 第 11 位 L -> W
j = run("/api/jobs/mutant", {
    "ref_seq": ref,
    "alt_seq": alt,
    "alleles": ["HLA-A02:01"],
    "peptide_lengths": [9],
}, "7a. 单点突变 L11W")
if j:
    print("  突变:", j["result"]["mutations"])
    print("  候选肽:", j["result"]["candidate_peptides"])

# ───────────────────────────── 导出 ─────────────────────────────
show("8. 导出 CSV / xlsx")
# 取最近一个 done 任务
jobs = c.get("/api/history?limit=20").get_json()["jobs"]
done = [x for x in jobs if x["status"] == "done"]
print(f"  历史记录 {len(jobs)} 条，其中完成 {len(done)} 条")
for kind in ("pan", "chop", "stab", "pipeline", "mutant"):
    target = next((x for x in done if x["kind"] == kind), None)
    if not target:
        print(f"  {kind}: 无完成任务，跳过")
        continue
    for fmt in ("csv", "xlsx"):
        r = c.get(f"/api/jobs/{target['id']}/export?format={fmt}")
        body = r.get_data()
        magic = body[:4]
        print(f"  {kind}/{fmt}: {r.status_code}  {len(body)} bytes  magic={magic!r}")
        if r.status_code != 200:
            print("     ", r.get_data(as_text=True)[:200])

# ───────────────────────────── 输入校验 ─────────────────────────────
show("9. /api/validate/input")
cases = [
    ("短肽", {"input": "GILG\nSLYNTVATL", "input_mode": "peptide"}),
    ("非标准残基", {"input": "GILGFVFTB\nSLYNTVATL", "input_mode": "peptide"}),
    ("混合长度", {"input": "SLYNTVATL\nGILGFVFTLV", "input_mode": "peptide"}),
    ("空输入", {"input": "", "input_mode": "peptide"}),
    ("正常 FASTA", {"input": ">p1\nMLLSVPLLLGLLGAAACSSNCGSS", "input_mode": "fasta"}),
    ("长名字", {"input": ">AVERYLONGPROTEINNAME_XYZ\nMLLSVPLLLGLLGAAACSSNCGSS", "input_mode": "fasta"}),
]
for name, payload in cases:
    r = c.post("/api/validate/input", json=payload)
    d = r.get_json()
    if not d.get("ok"):
        print(f"  {name}: ERROR {d.get('error')}")
        continue
    print(f"  {name}: valid={d['valid']} stats={ {k:v for k,v in d['stats'].items() if k in ('kind','count','lengths')} }")
    for w in d["warnings"]:
        print(f"     [{w['level']}] {w['message'][:90]}")

# ───────────────────────────── 错误处理 ─────────────────────────────
show("10. 错误处理")
for path, payload, label in [
    ("/api/jobs/pan", {"input": "SLYNTVATL", "alleles": []}, "无等位基因"),
    ("/api/jobs/pan", {"input": "", "alleles": ["HLA-A02:01"]}, "空输入"),
    ("/api/jobs/chop", {"input": "SLYNTVATL", "input_mode": "peptide"}, "chop 传肽列表"),
    ("/api/jobs/mutant", {"ref_seq": "AAA", "alt_seq": "AA", "alleles": ["HLA-A02:01"]}, "突变长度不等"),
]:
    r = c.post(path, json=payload)
    d = r.get_json()
    print(f"  {label}: {r.status_code} ok={d.get('ok')} {str(d.get('error'))[:80]}")

# 不存在的任务
r = c.get("/api/jobs/nonexistent")
print(f"  查不存在任务: {r.status_code} {r.get_json().get('error')}")
r = c.get("/api/jobs/nonexistent/export?format=csv")
print(f"  导出不存在任务: {r.status_code}")

show("测试完毕")
print(f"数据库: {store.db_path}")
print(f"历史任务总数: {store.count()}")
PY
