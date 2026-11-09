#!/usr/bin/env bash
# 80_extract_mutations.sh — 设计书第⑥步入口：从注释 VCF 提取错义突变 + 构造 21-mer 肽段区
# 用法: bash 80_extract_mutations.sh ANNOTATED_VCF OUT_DIR
# 输出: OUT_DIR/mutations.tsv      — 基因/位置/WT/突变AA 汇总表
#       OUT_DIR/neoantigen.json    — 直接提交工作台用的 JSON（蛋白质+突变列表）
#       OUT_DIR/proteins.fasta     — 涉及蛋白的 UniProt 序列（工作台「突变筛选」模式的粘贴输入）
# 说明: 自动从 UniProt 取野生型序列（gene_exact+reviewed:true+人），突变位点±10aa 构造 21-mer
set -euo pipefail
source "$(dirname "$0")/_common.sh"

VCF="${1:-}"; OUT="${2:-}"
[ -n "$VCF" ] && [ -n "$OUT" ] || die "用法: bash 80_extract_mutations.sh ANNOTATED_VCF OUT_DIR"
must_file "$VCF"
command -v bcftools >/dev/null 2>&1 || die "缺少 bcftools: sudo apt-get install -y bcftools"
command -v python3  >/dev/null 2>&1 || die "缺少 python3"
mkdir -p "$OUT"

log "提取错义突变（识别 snpEff ANN 与 VEP CSQ 两种注释格式）…"
if head -c 4096 "$VCF" | grep -qE "Hugo_Symbol|Tumor_Seq_Allele2|Variant_Classification"; then
  # ---- MAF 格式直读（TCGA/ICGC 现成注释 MAF，免 snpEff/VEP）----
  log "检测到 MAF 格式（Hugo_Symbol/Tumor_Seq_Allele2 表头），直接解析，免注释…"
  python3 - "$VCF" "$OUT/all_variants.tsv" <<'PYEOF'
import sys, gzip
src, dst = sys.argv[1], sys.argv[2]
op = gzip.open if src.endswith(".gz") else open
n = 0
with op(src, "rt", encoding="utf-8", errors="replace") as fh, open(dst, "w") as out:
    header = None
    for line in fh:
        line = line.rstrip("\n")
        if not line or line.startswith("##"):
            continue
        if line.startswith("#"):
            header = line.lstrip("#").split("\t"); continue
        if header is None:
            if "Hugo_Symbol" in line or "Tumor_Seq_Allele2" in line:
                header = line.split("\t"); continue
            continue
        f = line.split("\t")
        if len(f) < len(header):
            f += [""] * (len(header) - len(f))
        d = dict(zip(header, f))
        if "Missense" not in d.get("Variant_Classification", ""):
            continue
        gene = d.get("Hugo_Symbol") or d.get("Gene") or ""
        hgvsp = (d.get("HGVSp") or "").strip()
        if ":p." in hgvsp:
            hgvsp = hgvsp.split(":p.")[-1]
            hgvsp = "p." + hgvsp
        if not hgvsp.startswith("p."):
            aac = (d.get("Amino_Acid_Change") or "").strip()
            if aac:
                aac = aac.split("/")[0] if "/" in aac and not aac.startswith("p.") else aac
                hgvsp = aac if aac.startswith("p.") else "p." + aac
        if not hgvsp.startswith("p.") or not gene:
            continue
        info = "ANN=M|missense_variant||%s||||||%s|" % (gene, hgvsp)
        out.write("\t".join([d.get("Chromosome", "0"), d.get("Start_Position", "0"),
                             d.get("Reference_Allele", ""), d.get("Tumor_Seq_Allele2", ""), info]) + "\n")
        n += 1
print(f"[80] MAF 解析完成: {n} 行错义 → {dst}")
PYEOF
else
  bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\t%INFO\n' "$VCF" > "$OUT/all_variants.tsv"
fi

python3 - "$OUT/all_variants.tsv" "$OUT" <<'PYEOF'
import re, sys, json, urllib.request, time

src, outdir = sys.argv[1], sys.argv[2]
AA3TO1 = {"Ala":"A","Arg":"R","Asn":"N","Asp":"D","Cys":"C","Gln":"Q","Glu":"E","Gly":"G",
          "His":"H","Ile":"I","Leu":"L","Lys":"K","Met":"M","Phe":"F","Pro":"P","Ser":"S",
          "Thr":"T","Trp":"W","Tyr":"Y","Val":"V","Ter":"*"}

def to1(code):
    code = code.strip()
    if len(code) == 1: return code.upper()
    return AA3TO1.get(code.capitalize(), None)

def hgvs_p_to_change(h):
    # p.G12D / p.Gly12Asp / p.G12Vfs*3
    m = re.match(r"p\.([A-Za-z]{1,3})(\d+)([A-Za-z]{1,3})", h)
    if not m: return None
    wt, pos, mu = to1(m.group(1)), int(m.group(2)), to1(m.group(3))
    if wt is None or mu is None: return None
    return (wt, pos, mu)

rows = []
seen = set()
for line in open(src):
    f = line.rstrip("\n").split("\t")
    if len(f) < 5: continue
    info = f[4]
    # --- snpEff ANN（字段序随版本变化，后果/基因/ HGVS.p 按模式识别，不硬编码下标）---
    for ann in re.findall(r"(?:^|;)ANN=([^;]+)", info):
        for a in ann.split(","):
            p = a.split("|")
            if len(p) < 11: continue
            cons = " ".join(p[1:3])
            if "missense_variant" not in cons: continue
            gene = p[3]
            hgvsp = ""
            for v in p:
                if re.match(r"^p\.[A-Za-z]{1,3}\d+", v):
                    hgvsp = v; break
            ch = hgvs_p_to_change(hgvsp)
            if ch:
                key = (gene, ch[1])
                if key not in seen:
                    seen.add(key); rows.append((gene,) + ch)
    # --- VEP CSQ ---
    for csq in re.findall(r"(?:^|;)CSQ=([^;]+)", info):
        for c in csq.split(","):
            p = c.split("|")
            if len(p) < 5: continue
            if "missense_variant" not in p[0]: continue
            gene = ""
            aa = ""
            pos = ""
            # VEP --vcf 默认字段序: Allele|Consequence|IMPACT|SYMBOL|Gene|Feature_type|...（--symbol 后）
            # 常见布局里 SYMBOL 在 3，Amino_acids 在 2/--amino；用正则兜底
            for i, v in enumerate(p):
                if re.fullmatch(r"[A-Z*-]{1,3}/[A-Z*-]{1,3}", v):
                    aa = v
                if re.fullmatch(r"\d+(/\d+)?", v) and not pos:
                    pos = v.split("/")[0]
                if re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", v) and i <= 4 and not gene:
                    gene = v
            if aa and pos:
                wt, mu = (to1(x) for x in aa.split("/"))
                if wt and mu:
                    key = (gene, int(pos))
                    if key not in seen:
                        seen.add(key); rows.append((gene, wt, int(pos), mu))

# 去重并排序
rows = sorted(set(rows), key=lambda r: (r[0], r[1]))
with open(f"{outdir}/mutations.tsv", "w") as fh:
    fh.write("gene\twt_aa\tpos\tmut_aa\tctx21\tprotein_len\n")
    for r in rows:
        fh.write("\t".join(str(x) for x in r) + "\t\n")

# --- UniProt 取序列 + 构造 21-mer ---
def uniprot_seq(gene):
    q = f"gene_exact:{gene} AND organism_id:9606 AND reviewed:true"
    url = "https://rest.uniprot.org/uniprotkb/search?query=" + urllib.parse.quote(q) + "&format=fasta&size=1"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            txt = r.read().decode()
    except Exception as e:
        return None, str(e)
    seq = "".join(l.strip() for l in txt.splitlines() if not l.startswith(">"))
    header = txt.splitlines()[0] if txt else ""
    return seq, header

proteins = {}
final_rows = []
for gene, wt, pos, mu in rows:
    seq, header = uniprot_seq(gene)
    if not seq:
        print(f"[警告] {gene} 未在 UniProt reviewed 人类蛋白中找到（{header or '请求失败'}），跳过", file=sys.stderr)
        continue
    if pos - 1 >= len(seq) or seq[pos-1] != wt:
        print(f"[警告] {gene} 位置 {pos} 序列不一致（UniProt 该位为 {seq[pos-1] if pos-1 < len(seq) else '?'}，VCF 称 {wt}），保留但标注", file=sys.stderr)
    ctx = seq[max(0, pos-11): pos+10]
    final_rows.append((gene, wt, pos, mu, ctx, len(seq)))
    proteins[gene] = seq
    time.sleep(0.4)  # UniProt 礼貌限速

with open(f"{outdir}/mutations.tsv", "w") as fh:
    fh.write("gene\twt_aa\tpos\tmut_aa\tctx21\tprotein_len\n")
    for r in final_rows:
        fh.write("\t".join(str(x) for x in r) + "\n")

with open(f"{outdir}/proteins.fasta", "w") as fh:
    for g, s in proteins.items():
        fh.write(f">{g}\n")
        for i in range(0, len(s), 60):
            fh.write(s[i:i+60] + "\n")

with open(f"{outdir}/neoantigen.json", "w") as fh:
    json.dump({
        "mutations": [
            {"protein": g, "pos": int(p), "ref": w, "alt": m}
            for g, w, p, m, _c, _l in final_rows
        ],
        "note": f"{len(final_rows)} 个错义突变（来自 80_extract_mutations.sh）",
    }, fh, ensure_ascii=False, indent=2)

print(f"[80] 完成: {len(final_rows)} 个错义突变 / {len(proteins)} 个蛋白，输出在 {outdir}/")
PYEOF

must_file "$OUT/mutations.tsv"
log "下一步: bash 90_neoantigen.sh $OUT/neoantigen.json $OUT/proteins.fasta HLA-A*02:01 HLA-A*11:01 …"