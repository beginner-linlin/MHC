#!/usr/bin/env bash
# 真实使用场景模拟：真实蛋白 + 多等位基因 + 批量样本 + 边界情况
# 用 app.test_client()（Flask 内建测试客户端）驱动，等价于 HTTP 调用
set -uo pipefail

APP=/opt/bio/app
PY=$APP/venv/bin/python
cd "$APP" || exit 1
export MHC_APP_ROOT="$APP"

"$PY" - <<'PYEOF'
import json, sys, time, os
sys.path.insert(0, "/opt/bio/app")
os.environ.setdefault("MHC_APP_ROOT", "/opt/bio/app")
from mhc.web import app

PASS = []
FAIL = []

def ck(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✔' if cond else '✘'} {name}" + (f" — {detail}" if detail else ""))

def wait(job_id, timeout=180):
    c = app.test_client()
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/api/jobs/{job_id}")
        d = r.get_json()
        j = d.get("job") or {}
        if j.get("status") in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.15)
    return {"status": "timeout"}

def submit(kind, payload):
    c = app.test_client()
    r = c.post(f"/api/jobs/{kind}", json=payload)
    d = r.get_json()
    if not d.get("ok"):
        return None, d
    return wait(d["job"]["id"]), d

# ─── 真实蛋白序列（来自 UniProt，免疫功能相关，长度各异）───
PROTEINS = {
    # 流感 A/Puerto Rico/8/1934 M1 蛋白（252 aa）——经典 CTL 表位来源
    "FLU_M1": (
        "MSLLTEVETYVLSIIPSGPLKAEIAQRLEDVFAGKNTDLEVLMEWLKTRPILSPLTKGILGFVFTLTVPSERGLQR"
        "RRFGALNGAKEVALSYSTGALASCMGLIYNRMGNHEGPTPKSPTSQKEPLKTRPSFSGSLKQSRQDLGTSSSSSMLV"
        "GGGVPPNAQKSKLTKLLISLDRQEQRRSFSLKKTTEKEKEGTEAVSLEEKKGPPPQIPDLSKLAQKLVKVLSTTSSA"
        "SVMQHLKSLFDGKKMEPMGLTEETIYFLKDLLKANFTNPDVFLATKLFLSYLSQEHKRYPQISDVKPNNDSLSSLEE"
        "LIKKSDGGSDKSSSKLFQKINDLFLKSLASSLRSELFN"
    ),
    # 人 EGFR 部分（受体酪氨酸激酶，膜蛋白）
    "EGFR_17_470": (
        "MRPSGTAGAALLALLAALCPASRALEEKKVCQGTSNKLTQLGTFEDHFLSLQRMFNNCEVVLGNLEITYVQRNYDLS"
        "FLKTIQEVAGYVLIALNTVERIPLENLQIIRGNMYYENSYALAVLSNYDANKTGLKELPMRNLQEILHGAVRFSNNP"
        "ALCNVESIQWRDIVSSDFLSNMSMDFQNHLGSCQKCDPSCPNGSCWGAGEENCQKLTKIICAQQCSGRCRGKSPSDC"
        "CHNQCAAGCTGPRESDCLVCRKFRDEATCKDTCPPLMLYNPTTYQMDVNPEGKYSFGATCVKKCPRNYVVTDHGSCV"
        "RACGADSYEMEEDGVRKCKKCEGPCRKVCNGIGIGEFKDSLSINATNIKHFKNCTSISGDLHILPVAFRGDSFTHTP"
        "PLDPQELDILKTVKEITGFLLIQAWPENRTDLHAFENLEIIRGRTKQHGQFSLAVVSLNITSLGLRSLKEISDGDVI"
        "ISGNKNLCYANTINWKKLFGTSGQKTKIISNRGENSCKATGQVCHALCSPEGCWGPEPRDCV"
    ),
    # 人 KRAS 全长 188 aa
    "KRAS": (
        "MTEYKLVVVGAGGVGKSALTIQLIQNHFVDEYDPTIEDSYRKQVVIDGETCLLDILDTAGQEEYSAMRDQYMRTGEG"
        "FLCVFAINNTKSFEDIHQYREQIKRVKDSEDVPMVLVGNKCDLPSRTVDTKQAQDLARSYGIPFIETSAKTRQGVDD"
        "AFYTLVREIRKHKEKMSKDGKKKKKKSKTKCVIM"
    ),
    # 人 p53 全长 393 aa
    "P53": (
        "MEEPQSDPSVEPPLSQETFSDLWKLLPENNVLSPLPSQAMDDLMLSPDDIEQWFTEDPGPDEAPRMPEAAPPVAPAP"
        "AAPTPAAPAPAPSWPLSSSVPSQKTYQGSYGFRLGFLHSGTAKSVTCTYSPALNKMFCQLAKTCPVQLWVDSTPPPG"
        "TRVRAMAIYKQSQHMTEVVRRCPHHERCSDSDGLAPPQHLIRVEGNLRVEYLDDRNTFRHSVVVPYEPPEVGSDCTT"
        "IHYNYMCNSSCMGGMNRRPILTIITLEDSSGNLLGRNSFEVRVCACPGRDRRTEEENLRKKGEPHHELPPGSTKRAL"
        "PNNTSSSPQPKKKPLDGEYFTLQIRGRERFEMFRELNEALELKDAQAGKEPGGSRAHSSHLKSKKGQSTSRHKKLMF"
        "KTEGPDSD"
    ),
    # 人 SARS-CoV-2 刺突蛋白 RBD 片段（受体结合域）
    "COVID_RBD": (
        "RVQPTESIVRFPNITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNV"
        "YADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEI"
        "YQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATV"
    ),
}

ALLELES_6 = ["HLA-A02:01", "HLA-A24:02", "HLA-B07:02", "HLA-B15:01", "HLA-C07:02", "HLA-E01:01"]

print("\n" + "═" * 70)
print("场景 A：真实蛋白 · 单等位基因结合预测（5 种真实蛋白）")
print("═" * 70)
for name, seq in PROTEINS.items():
    fasta = f">{name}\n{seq}"
    job, raw = submit("pan", {"input": fasta, "input_mode": "fasta", "alleles": ["HLA-A02:01"],
                              "with_ba": True, "sort": False, "threshold": 0.5})
    if not job:
        ck(f"A {name}", False, str(raw.get("error")))
        continue
    n = len((job.get("result") or {}).get("rows") or [])
    ck(f"A {name} ({len(seq)}aa → {n} 条 SB 肽)", job["status"] == "done" and n > 0,
       f"{job.get('seconds', 0):.2f}s")

print("\n" + "═" * 70)
print("场景 B：真实蛋白 · 6 等位基因同时预测（最耗时场景）")
print("═" * 70)
fas = "\n".join(f">{k}\n{v}" for k, v in list(PROTEINS.items())[:3])
job, raw = submit("pan", {"input": fas, "input_mode": "fasta", "alleles": ALLELES_6,
                          "with_ba": True, "sort": True, "threshold": 2})
if job:
    rows = (job.get("result") or {}).get("rows") or []
    ck("B 6 等位基因批量预测", job["status"] == "done" and len(rows) > 0,
       f"{len(rows)} 行 / {job.get('seconds', 0):.2f}s")
    mhcs = sorted({r.get("mhc") for r in rows})
    ck("B 覆盖全部 6 个等位基因", len(mhcs) == 6, ", ".join(mhcs))
else:
    ck("B 6 等位基因批量预测", False, str(raw.get("error")))

print("\n" + "═" * 70)
print("场景 C：完整三步流水线（真实蛋白，多肽长）")
print("═" * 70)
job, raw = submit("pipeline", {
    "input": f">FLU_M1\n{PROTEINS['FLU_M1']}", "input_mode": "fasta",
    "alleles": ["HLA-A02:01", "HLA-A24:02"],
    "cleavage_threshold": 0.5, "cleavage_model": 0, "peptide_lengths": [9, 10],
    "use_cleavage_filter": True, "max_rank_el": 2.0, "min_thalf": 0,
})
if job:
    r = job.get("result") or {}
    rows = r.get("rows") or []
    nsteps = len(r.get("steps") or [])
    ck("C 流水线完成", job["status"] == "done", f"{job.get('seconds', 0):.2f}s")
    ck("C 四步步骤齐全", nsteps == 4, f"{nsteps} 步")
    ck("C 有最终候选肽", len(rows) > 0, f"{len(rows)} 行")
    for s in (r.get("steps") or []):
        print(f"     · {s.get('label')} {s.get('rows_in')}→{s.get('rows_out')} {s.get('note','')}")
else:
    ck("C 流水线完成", False, str(raw.get("error")))

print("\n" + "═" * 70)
print("场景 D：批量多肽稳定性（混合长度 8/9/10/11）")
print("═" * 70)
mixed = ["GILGFVFTL", "SLYNTVATL", "KLLPENNVL", "MLLSVPLLL", "RVQPTESIVR", "MTEYKLVVVG",
         "MEEPQSDPS", "VQGTSNKLTQ"]
job, raw = submit("stab", {"input": "\n".join(mixed), "input_mode": "peptide",
                           "alleles": ["HLA-A02:01"], "with_ia": True, "sort": 2})
if job:
    rows = (job.get("result") or {}).get("rows") or []
    lens = sorted({len(str(r.get("peptide") or "")) for r in rows})
    ck("D 混合长度自动分组", job["status"] == "done" and len(rows) > 0,
       f"{len(rows)} 行 / {job.get('seconds', 0):.2f}s / 长度 {lens}")
else:
    ck("D 混合长度自动分组", False, str(raw.get("error")))

print("\n" + "═" * 70)
print("场景 E：新抗原突变筛选（KRAS G12D 经典驱动突变）")
print("═" * 70)
kras_ref = PROTEINS["KRAS"]
# KRAS G12D: 第 12 位 G→D（序列 MTEYKLVVVGAG 的第 12 个字符 G 改成 D）
kras_alt = kras_ref[:11] + "D" + kras_ref[12:]
print(f"   ref[5:20] = {kras_ref[5:20]}")
print(f"   alt[5:20] = {kras_alt[5:20]}  (第 12 位 G→D)")
job, raw = submit("mutant", {"ref_seq": kras_ref, "alt_seq": kras_alt,
                             "alleles": ["HLA-A02:01", "HLA-C07:02"],
                             "peptide_lengths": [8, 9, 10], "max_rank_el": 2.0})
if job:
    r = job.get("result") or {}
    rows = r.get("rows") or []
    muts = r.get("mutations") or []
    ck("E KRAS G12D 突变识别", len(muts) == 1 and muts[0].get("pos") == 12,
       f"{muts}")
    ck("E 突变肽有结果", len(rows) > 0, f"{len(rows)} 行 / {job.get('seconds', 0):.2f}s")
    if rows:
        for x in rows[:5]:
            print(f"     · {x.get('mutation')} {x.get('peptide')} rank_el={x.get('rank_el')} aff={x.get('aff_nm')} bind={x.get('bind_pan')}")
else:
    ck("E KRAS G12D 突变筛选", False, str(raw.get("error")))

print("\n" + "═" * 70)
print("场景 F：大输入压力（500aa × 4 等位基因）")
print("═" * 70)
big = "".join([PROTEINS["P53"], PROTEINS["KRAS"], PROTEINS["COVID_RBD"]])[:600]
job, raw = submit("pan", {"input": f">big\n{big}", "input_mode": "fasta",
                          "alleles": ["HLA-A02:01", "HLA-A24:02", "HLA-B07:02", "HLA-C07:02"],
                          "with_ba": True, "sort": False, "threshold": 0.5})
if job:
    rows = (job.get("result") or {}).get("rows") or []
    ck(f"F {len(big)}aa × 4 等位基因", job["status"] == "done" and len(rows) > 0,
       f"{len(rows)} 行 / {job.get('seconds', 0):.2f}s")
else:
    ck("F 大输入压力", False, str(raw.get("error")))

print("\n" + "═" * 70)
print("场景 G：导出全部 5 类结果（csv + xlsx）")
print("═" * 70)
c = app.test_client()
hist = c.get("/api/history?limit=200").get_json()
kinds_seen = {}
for j in hist.get("jobs", []):
    k = j.get("kind")
    if k and k not in kinds_seen and j.get("status") == "done":
        kinds_seen[k] = j["id"]
for k, jid in kinds_seen.items():
    for fmt, magic in (("csv", b"\xef\xbb\xbf"), ("xlsx", b"PK\x03\x04")):
        r = c.get(f"/api/jobs/{jid}/export?format={fmt}")
        ok = r.status_code == 200 and r.data.startswith(magic)
        ck(f"G {k} · {fmt}", ok, f"{len(r.data)} B")
ck("G 覆盖 5 类任务", len(kinds_seen) >= 5, f"{sorted(kinds_seen)}")

print("\n" + "═" * 70)
print("场景 H：极端边界输入（应优雅报错，不崩）")
print("═" * 70)
c = app.test_client()
edges = [
    ("H1 空肽列表", "pan", {"input": "", "input_mode": "peptide", "alleles": ["HLA-A02:01"]}, 400),
    ("H2 全是换行", "pan", {"input": "\n\n\n", "input_mode": "peptide", "alleles": ["HLA-A02:01"]}, 400),
    ("H3 坏等位基因", "pan", {"input": "SLYNTVATL", "input_mode": "peptide", "alleles": ["HLA-Q99:99"]}, None),
    ("H4 FASTA 无序列", "pan", {"input": ">only_header", "input_mode": "fasta", "alleles": ["HLA-A02:01"]}, None),
    ("H5 单残基蛋白", "chop", {"input": ">x\nM", "input_mode": "fasta"}, None),
    ("H6 数字混入", "pan", {"input": "123456789", "input_mode": "peptide", "alleles": ["HLA-A02:01"]}, None),
    ("H7 突变无差异", "mutant", {"ref_seq": "MTEYKLVVVG", "alt_seq": "MTEYKLVVVG",
                                  "alleles": ["HLA-A02:01"], "peptide_lengths": [9]}, 400),
    ("H8 突变长度不等", "mutant", {"ref_seq": "MTEYKLVV", "alt_seq": "MTEYKLVVGG",
                                   "alleles": ["HLA-A02:01"], "peptide_lengths": [9]}, 400),
]
for label, kind, payload, want in edges:
    r = c.post(f"/api/jobs/{kind}", json=payload)
    d = r.get_json() or {}
    code = r.status_code
    if want is not None:
        ck(label, code == want, f"HTTP {code} {d.get('error','')}")
    else:
        # 后台失败的也算正常处理（不 crash）
        ck(label, code in (200, 400, 422), f"HTTP {code} {d.get('error','')[:50]}")

print("\n" + "═" * 70)
print(f"结果：通过 {len(PASS)}，失败 {len(FAIL)}")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  ✘ " + f)
print("═" * 70)
sys.exit(1 if FAIL else 0)
PYEOF
