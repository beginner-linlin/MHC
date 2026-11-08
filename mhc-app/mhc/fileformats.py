"""通用输入文件格式识别与解析。

支持的目标（持续扩展）：
  - FASTA（蛋白/多肽）
  - 纯多肽列表（每行一条）
  - IEDB 查询导出 CSV（带引号、字段内逗号）
  - IEDB API 预测输出（csv / tsv）
  - pVACtools / neoantigen 流程表格（MT Peptide / WT Peptide / HLA Allele 列）
  - 本应用自己的导出 CSV（往返）
  - 任意含 peptide/sequence/肽 列的 CSV / TSV / 分号表格
  - Excel xlsx（openpyxl）
  - VCF（含 snpEff ANN= / VEP CSQ=HGVS.p 注释）
  - TCGA MAF（Hugo_Symbol / Tumor_Seq_Allele2 / HGVSp_Short）
  - HGVS 蛋白突变列表（p.G12D 或 p.Gly12Asp，可带基因名前缀）

设计原则：
  - 解析全部在服务端做（csv 模块正确处理引号转义，浏览器端做不到）
  - 列识别用别名表 + 前 5 行内找表头
  - 能提取的额外信息（等位基因列、蛋白名列、突变注释）一并返回
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from .runner import FastaRecord, looks_like_fasta, parse_fasta, parse_peptide_list, resolve_alleles

MAX_PEPTIDES = 20000
MAX_ROWS_SCAN = 20000
PEP_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBXZUJO*-]+$")

AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}

# 列别名（全部小写、去空格后匹配；前缀匹配用 startswith）
PEP_COLS = [
    "peptide", "peptides", "peptide_seq", "peptide sequence", "peptide seq",
    "mt peptide", "mt_peptide", "mut peptide", "mut_peptide", "mutant peptide",
    "mutated peptide", "mutated_peptide", "alt peptide", "tumor peptide",
    "neoantigen", "epitope", "epitope seq", "sequence", "seq", "short sequence",
    "肽", "肽段", "序列", "突变肽", "抗原肽", "表位",
]
WT_PEP_COLS = ["wt peptide", "wt_peptide", "wildtype peptide", "wild type peptide",
               "ref peptide", "normal peptide", "野生型肽"]
ALLELE_COLS = ["allele", "alleles", "mhc", "hla", "mhc allele", "hla allele",
               "mhc_allele", "hla_allele", "allele name", "allele_name", "hla type",
               "hla_allele_1", "等位基因", "hla 分型"]
GENE_COLS = ["gene", "gene name", "gene_name", "hugo_symbol", "hugo symbol", "symbol",
             "protein", "protein name", "protein_name", "uniprot", "protein_id",
             "gene symbol", "基因", "蛋白", "蛋白名"]


@dataclass
class ParseResult:
    format: str = "unknown"
    kind: str = "empty"          # peptides | proteins | variants | mutations | empty
    peptides: list[str] = field(default_factory=list)
    proteins_text: str = ""      # 重建的 FASTA 文本（前端直接填输入框）
    alleles: list[str] = field(default_factory=list)
    variants: list[dict] = field(default_factory=list)
    mutations: list[dict] = field(default_factory=list)   # 可直接用于 mutant 模式
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": True,
            "format": self.format,
            "kind": self.kind,
            "peptides": self.peptides[:200],
            "peptide_count": len(self.peptides),
            "proteins_text": self.proteins_text[:50000],
            "alleles": self.alleles,
            "variants": self.variants[:100],
            "variant_count": len(self.variants),
            "mutations": self.mutations[:200],
            "mutation_count": len(self.mutations),
            "notes": self.notes,
        }


# ---------------------------------------------------------------- 低层工具


def _clean_cell(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip().strip('"').strip("'").strip()
    return s


def _is_peptide(s: str) -> bool:
    return bool(s) and len(s) <= 60 and bool(PEP_RE.match(s.upper()))


def _sniff_delimiter(sample: str) -> str:
    best, best_n = "\t", 0
    for d in (",", "\t", ";"):
        n = sample.count(d)
        if n > best_n:
            best, best_n = d, n
    return best


def _norm_key(s: str) -> str:
    return re.sub(r"[\s_\-（）()：:]+", "", _clean_cell(s)).lower()


def _match_col(header: str, aliases: list[str]) -> bool:
    k = _norm_key(header)
    if not k:
        return False
    for a in aliases:
        an = _norm_key(a)
        if k == an or k.startswith(an) or an.startswith(k):
            return True
    return False


def parse_hgvs_p(txt: str) -> tuple[int, str, str] | None:
    """p.G12D / p.Gly12Asp → (pos, ref, alt)；其余（del/ins/fs）不支持。"""
    s = _clean_cell(txt)
    m = re.match(r"^p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})$", s)
    if m:
        ref = AA3.get(m.group(1).upper())
        alt = AA3.get(m.group(3).upper())
        if ref and alt:
            return int(m.group(2)), ref, alt
        return None
    m = re.match(r"^p\.([ACDEFGHIKLMNPQRSTVWY])(\d+)([ACDEFGHIKLMNPQRSTVWY])$", s)
    if m:
        return int(m.group(2)), m.group(1), m.group(3)
    m = re.match(r"^([ACDEFGHIKLMNPQRSTVWY])(\d+)([ACDEFGHIKLMNPQRSTVWY])$", s)  # G12D 裸写法
    if m:
        return int(m.group(2)), m.group(1), m.group(3)
    return None


def build_pairs(records: list[FastaRecord], mutations: list[dict]) -> tuple[list[dict], list[str]]:
    """把蛋白突变匹配到参考蛋白 FASTA，生成 [{name, ref, alt}]。

    匹配规则：突变里的基因名与 FASTA 名互为大小写不敏感的包含关系。
    多个突变命中同一条蛋白时全部应用；ref 不匹配时照常替换但记 warning。
    """
    pairs: dict[str, dict] = {}
    notes: list[str] = []
    for mu in mutations:
        gene = (mu.get("protein") or "").strip()
        pos, ref, alt = mu.get("pos"), (mu.get("ref") or "").upper(), (mu.get("alt") or "").upper()
        if not gene or not pos:
            continue
        hit = None
        for r in records:
            rn = r.name.upper()
            g = gene.upper()
            if rn == g or rn.startswith(g + "|") or rn.startswith(g + " ") \
                    or (g and g in rn) or (rn and rn in g):
                hit = r
                break
        if hit is None:
            notes.append(f"突变 {gene} p.{ref}{pos}{alt} 没有在参考 FASTA 中找到对应蛋白，已跳过。")
            continue
        seq = hit.seq.upper()
        if not (1 <= pos <= len(seq)):
            notes.append(f"突变 {gene} p.{ref}{pos}{alt} 的位置超出蛋白 {hit.name} 长度 {len(seq)}，已跳过。")
            continue
        if seq[pos - 1] != ref:
            notes.append(
                f"突变 {gene} p.{ref}{pos}{alt} 与蛋白 {hit.name} 第 {pos} 位残基 "
                f"({seq[pos - 1]}) 不一致（常见于转录本异构体差异），已按给定替换强制应用。"
            )
        key = hit.name
        if key not in pairs:
            pairs[key] = {"name": hit.name, "ref": seq, "alt": seq, "mutations": []}
        p = pairs[key]
        p["alt"] = p["alt"][: pos - 1] + alt + p["alt"][pos:]
        p["mutations"].append({"pos": pos, "ref": ref, "alt": alt})
    return list(pairs.values()), notes


# ---------------------------------------------------------------- 各格式解析


def _parse_fasta_or_peptides(text: str) -> ParseResult:
    if looks_like_fasta(text):
        recs = parse_fasta(text)
        res = ParseResult(format="FASTA", kind="proteins")
        res.proteins_text = text
        if len(recs) > 3000:
            res.notes.append(f"共 {len(recs)} 条序列，数量较大。")
        return res
    peps = parse_peptide_list(text)
    if peps:
        res = ParseResult(format="多肽列表", kind="peptides", peptides=peps)
        return res
    return ParseResult(kind="empty", notes=["没有识别到任何序列。"])


def _parse_table(rows: list[list[str]], source_format: str) -> ParseResult:
    """rows: 已切好的单元格矩阵（含表头行）。"""
    res = ParseResult(format=source_format)
    if not rows:
        res.notes = ["表格为空。"]
        return res

    # 1. 在前 5 行里找表头
    header_idx = -1
    pep_col = allele_col = gene_col = -1
    for i, row in enumerate(rows[:5]):
        cells = [_clean_cell(c) for c in row]
        pc = next((j for j, c in enumerate(cells) if _match_col(c, PEP_COLS)), -1)
        ac = next((j for j, c in enumerate(cells) if _match_col(c, ALLELE_COLS)), -1)
        gc = next((j for j, c in enumerate(cells) if _match_col(c, GENE_COLS)), -1)
        if pc >= 0:
            header_idx, pep_col, allele_col, gene_col = i, pc, ac, gc
            break

    if header_idx < 0:
        # 无表头：整表扫肽
        peps: list[str] = []
        for row in rows[:MAX_ROWS_SCAN]:
            for c in row:
                s = _clean_cell(c).upper()
                if _is_peptide(s) and len(s) >= 6:
                    peps.append(s)
                    break
        if peps:
            res.kind = "peptides"
            res.peptides = peps
            res.notes.append("未找到表头，已按「每行第一个像肽段的单元格」提取。")
        else:
            res.notes.append("表格里没有找到肽段样式的列。")
        return res

    data = rows[header_idx + 1: header_idx + 1 + MAX_ROWS_SCAN]
    peps, alleles_raw, names = [], [], []
    for row in data:
        if not any(_clean_cell(c) for c in row):
            continue
        get = lambda j: _clean_cell(row[j]) if 0 <= j < len(row) else ""   # noqa: E731
        pep = get(pep_col).upper()
        if pep and PEP_RE.match(pep):
            peps.append(pep)
            if allele_col >= 0:
                alleles_raw.append(get(allele_col))
            if gene_col >= 0:
                names.append(get(gene_col))
        elif pep:
            # 长序列列——可能是蛋白而不是肽
            if len(pep) <= 40000 and set(pep) <= set("ACDEFGHIKLMNPQRSTVWYBXZUJO*-"):
                names.append("")  # 占位，后面统一处理
    if not peps:
        res.notes.append(f"表头已识别（肽列 = 第 {pep_col + 1} 列），但数据行里没有合法肽段。")
        return res

    # 2. 长度分布判断：肽 还是 蛋白
    med = sorted(len(p) for p in peps)[len(peps) // 2]
    if med >= 30:
        recs = []
        for idx, pep in enumerate(peps):
            nm = names[idx].strip() if idx < len(names) and names else ""
            recs.append(FastaRecord(name=nm or f"SEQ{idx + 1}", seq=pep))
        res.kind = "proteins"
        res.proteins_text = "\n".join(f">{r.name}\n{r.seq}" for r in recs)
        res.notes.append(f"该列中位长度 {med}aa，按蛋白序列处理（FASTA 模式，工具会自动滑窗切肽）。")
        return res

    # 3. 肽 + 等位基因列
    res.kind = "peptides"
    res.peptides = peps
    if allele_col >= 0 and alleles_raw:
        uniq = []
        for a in alleles_raw:
            if not a:
                continue
            for one in re.split(r"[;,/|]+", a):
                one = one.strip()
                if not one:
                    continue
                n = resolve_alleles([one])[0] if resolve_alleles([one]) else one
                if n and n not in uniq:
                    uniq.append(n)
        class1 = [a for a in uniq if a.upper().startswith(("HLA-A", "HLA-B", "HLA-C", "HLA-E", "HLA-G", "H2-", "H-2"))]
        dropped = len(uniq) - len(class1)
        res.alleles = class1[:20]
        if dropped:
            res.notes.append(
                f"等位基因列里滤掉了 {dropped} 个本工具不支持的条目"
                "（如 HLA-DR/DQ/DP 二类分子，NetMHCpan 系列只支持一类）。"
            )
        if len(class1) > 20:
            res.notes.append(f"共发现 {len(class1)} 个不同的一类等位基因，已截取前 20 个。")
        if res.alleles:
            res.notes.append(f"检测到等位基因列，已解析出 {len(res.alleles)} 个等位基因，可一键带入。")
    dup = len(peps) - len(set(peps))
    if dup:
        res.peptides = list(dict.fromkeys(peps))
        res.notes.append(f"表格中有 {dup} 条重复肽段，已去重。")
    if len(res.peptides) > MAX_PEPTIDES:
        res.notes.append(f"肽段数量超过 {MAX_PEPTIDES}，已截断。")
        res.peptides = res.peptides[:MAX_PEPTIDES]
    return res


def _parse_vcf(text: str) -> ParseResult:
    res = ParseResult(format="VCF", kind="variants")
    csq_keys: list[str] = []
    for line in text.splitlines():
        if line.startswith("##INFO=<ID=CSQ"):
            m = re.search(r"Format:\s*([^>\"]+)", line)
            if m:
                csq_keys = [k.strip() for k in m.group(1).split("|")]
            continue
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            parts = line.split(",")
        if len(parts) < 5:
            continue
        chrom, pos_s, _rid, ref, alt_field = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            pos = int(pos_s)
        except ValueError:
            continue
        info = parts[7] if len(parts) > 7 else ""
        alts = [a for a in alt_field.split(",") if a and a != "."]
        base = {"source": "vcf", "chrom": chrom, "pos": pos}
        found_hgvs = False
        # snpEff ANN / VEP HGVS.p / CSQ HGVSp
        for pat in (r"HGVS\.?p=([^;,|]+)",):
            for m in re.finditer(pat, info):
                parsed = parse_hgvs_p(m.group(1))
                if parsed:
                    p, r_, a_ = parsed
                    res.variants.append({**base, "protein": "", "pos": p, "ref": r_, "alt": a_,
                                         "hgvs": m.group(1)})
                    found_hgvs = True
        # ANN=...|p.Gly12Asp|...（snpEff；值内多个注释以逗号分隔，整块到行尾）
        for m in re.finditer(r"ANN=(.+?)(?=\t|$)", info):
            fields = m.group(1).split(",")
            for f in fields:
                seg = f.split("|")
                gene = seg[3] if len(seg) > 3 else ""
                for s_ in seg:
                    if re.match(r"^p\.", s_ or ""):
                        parsed = parse_hgvs_p(s_)
                        if parsed:
                            p, r_, a_ = parsed
                            res.variants.append({**base, "protein": gene, "pos": p, "ref": r_,
                                                 "alt": a_, "hgvs": s_})
                            found_hgvs = True
        # CSQ=...（VEP；值内多个注释以逗号分隔，整块到行尾）
        for m in re.finditer(r"CSQ=(.+?)(?=\t|$)", info):
            for f in m.group(1).split(","):
                seg = f.split("|")
                if not csq_keys:
                    continue
                kv = dict(zip(csq_keys, seg))
                hg = kv.get("HGVSp") or kv.get("HGVS_p") or ""
                if hg and parse_hgvs_p(hg):
                    p, r_, a_ = parse_hgvs_p(hg)
                    res.variants.append({**base, "protein": kv.get("SYMBOL") or kv.get("Gene") or "",
                                         "pos": p, "ref": r_, "alt": a_, "hgvs": hg})
                    found_hgvs = True
        # 无蛋白注释的 SNV 也记录（前端展示用，不能直接做 neoantigen 筛选）
        for a in alts:
            if len(ref) == 1 and len(a) == 1 and not found_hgvs:
                res.variants.append({**base, "protein": "", "pos": pos, "ref": ref.upper(),
                                     "alt": a.upper(), "hgvs": ""})
    if not res.variants:
        res.notes = ["VCF 里没有可用的变异（只支持 SNV 与带 HGVS.p 注释的记录）。"]
        return res
    hg = [v for v in res.variants if v.get("hgvs")]
    if hg:
        res.mutations = [
            {"protein": v["protein"], "pos": v["pos"], "ref": v["ref"], "alt": v["alt"], "hgvs": v["hgvs"]}
            for v in hg
        ]
        res.notes.append(
            f"共 {len(res.variants)} 个变异，其中 {len(hg)} 个带蛋白级 HGVS 注释，"
            "可直接进突变肽筛选（还需配套的蛋白 FASTA）。"
        )
    else:
        res.notes.append(
            f"共 {len(res.variants)} 个 SNV，但没有蛋白级注释（无 HGVS.p / ANN / CSQ）。"
            "基因组坐标需要先经 VEP/snpEff 注释或比对到蛋白序列才能做新抗原筛选。"
        )
    return res


def _parse_maf(text: str) -> ParseResult:
    res = ParseResult(format="MAF（TCGA）", kind="variants")
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    if not lines:
        res.notes = ["MAF 文件为空。"]
        return res
    header = [_norm_key(h) for h in re.split(r"[\t,]", lines[0])]
    def col(*names: str) -> int:
        for n in names:
            k = _norm_key(n)
            if k in header:
                return header.index(k)
        return -1
    i_gene = col("Hugo_Symbol", "gene")
    i_ref = col("Reference_Allele", "ref")
    i_t1 = col("Tumor_Seq_Allele1")
    i_t2 = col("Tumor_Seq_Allele2", "alt")
    i_hg = col("HGVSp_Short", "HGVSp", "protein_change", "HGVSp_Short")
    i_start = col("Start_Position", "start")
    if i_gene < 0 or i_ref < 0 or i_t2 < 0:
        res.notes = ["MAF 表头不完整（缺 Hugo_Symbol / Reference_Allele / Tumor_Seq_Allele2）。"]
        return res
    n_rows = n_snv = 0
    for line in lines[1: MAX_ROWS_SCAN]:
        cells = re.split(r"[\t,]", line)
        get = lambda j: _clean_cell(cells[j]) if 0 <= j < len(cells) else ""  # noqa: E731
        gene, ref = get(i_gene), get(i_ref).upper()
        alt = get(i_t2).upper() or get(i_t1).upper()
        if not gene or gene == "Unknown":
            continue
        n_rows += 1
        base = {"source": "maf", "chrom": get(col("Chromosome", "chr")), "pos": get(i_start)}
        if len(ref) == 1 and len(alt) == 1 and ref != alt:
            n_snv += 1
            v = {**base, "protein": gene, "pos": None, "ref": ref, "alt": alt, "hgvs": ""}
            hg = get(i_hg)
            if hg:
                parsed = parse_hgvs_p(hg)
                if parsed:
                    v["pos"], v["ref"], v["alt"] = parsed
                    v["hgvs"] = hg
            res.variants.append(v)
    has_hg = [v for v in res.variants if v.get("hgvs")]
    if has_hg:
        res.mutations = [
            {"protein": v["protein"], "pos": v["pos"], "ref": v["ref"], "alt": v["alt"], "hgvs": v["hgvs"]}
            for v in has_hg
        ]
        res.notes.append(
            f"共 {n_rows} 行突变 / {n_snv} 个 SNV，其中 {len(has_hg)} 个带 HGVSp 蛋白注释"
            "（p.G12D 样式），可直接进突变肽筛选（还需配套的蛋白 FASTA）。"
        )
    else:
        res.notes.append(
            f"共 {n_rows} 行突变 / {n_snv} 个 SNV，但该 MAF 没有 HGVSp_Short 蛋白注释列，"
            "无法直接定位到蛋白残基。可改用带注释的 MAF 或自行提供 p. 突变列表。"
        )
    return res


def _parse_mutation_list(text: str) -> ParseResult | None:
    """KRAS p.G12D / p.Gly12Asp 每行一条。"""
    muts = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s+(p\..+)$", s)
        if m:
            parsed = parse_hgvs_p(m.group(2))
            if parsed:
                muts.append({"protein": m.group(1), "pos": parsed[0], "ref": parsed[1],
                             "alt": parsed[2], "hgvs": m.group(2)})
                continue
        m = re.match(r"^(p\..+)$", s)
        if m:
            parsed = parse_hgvs_p(m.group(1))
            if parsed:
                muts.append({"protein": "", "pos": parsed[0], "ref": parsed[1],
                             "alt": parsed[2], "hgvs": m.group(1)})
                continue
        if muts:
            return None  # 混合内容，不是纯突变列表
    if muts:
        res = ParseResult(format="HGVS 突变列表", kind="mutations")
        res.mutations = muts
        res.variants = [dict(m, source="hgvs", chrom="") for m in muts]
        res.notes = [f"识别出 {len(muts)} 条蛋白突变。需要配套蛋白 FASTA 才能生成突变序列。"]
        return res
    return None


def _parse_xlsx(raw: bytes) -> tuple[list[list[str]], str] | None:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return None
    ws = wb.active
    rows: list[list[str]] = []
    for row in ws.iter_rows(values_only=True):
        cells = ["" if c is None else str(c) for c in row]
        if any(c.strip() for c in cells):
            rows.append(cells)
        if len(rows) >= MAX_ROWS_SCAN:
            break
    wb.close()
    return rows, f"Excel（{ws.title}）"


# ---------------------------------------------------------------- 总入口


def parse_any(text: str = "", *, filename: str = "", raw: bytes | None = None) -> dict:
    """识别并解析输入文件。text 为文本内容；raw 为原始字节（xlsx 二进制）。"""
    fname = (filename or "").lower()

    if raw is not None:
        if raw[:2] == b"PK":
            parsed_x = _parse_xlsx(raw)
            if parsed_x:
                rows, fmt = parsed_x
                return _parse_table(rows, fmt).to_dict()
            return ParseResult(kind="empty", notes=["xlsx 文件无法读取（可能已损坏）。"]).to_dict()
        if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            return ParseResult(
                kind="empty",
                notes=["旧版 .xls 格式不支持，请在 Excel 里「另存为 .xlsx」后重新上传。"],
            ).to_dict()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gbk")
            except UnicodeDecodeError:
                return ParseResult(kind="empty", notes=["文件不是 UTF-8/GBK 文本，也不是 xlsx。"]).to_dict()

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    head = text.lstrip()

    # VCF
    if head.startswith("##fileformat=VCF") or (text.startswith("#") and re.search(
            r"^#CHROM\s+POS\s+ID\s+REF\s+ALT", text, re.M)):
        return _parse_vcf(text).to_dict()
    # MAF
    if "Hugo_Symbol" in text[:4000] and ("Tumor_Seq_Allele2" in text[:4000] or "Tumor_Seq_Allele1" in text[:4000]):
        return _parse_maf(text).to_dict()

    # HGVS 突变列表（在 FASTA/纯肽分支之前：'KRAS p.G12D' 会被纯肽分支误收）
    mut = _parse_mutation_list(text)
    if mut:
        return mut.to_dict()

    # FASTA / 纯肽
    if looks_like_fasta(text):
        r = _parse_fasta_or_peptides(text)
        if r.kind != "empty":
            return r.to_dict()

    # 表格
    if any(ch in text[:5000] for ch in (",", "\t", ";")):
        sample = "\n".join(text.splitlines()[:10])
        delim = _sniff_delimiter(sample)
        try:
            rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        except csv.Error:
            rows = [l.split(delim) for l in text.splitlines() if l.strip()]
        rows = [r for r in rows if any(_clean_cell(c) for c in r)][:MAX_ROWS_SCAN]
        fmt = {"\t": "TSV", ",": "CSV", ";": "分号表格"}[delim]
        res = _parse_table(rows, fmt)
        if res.kind != "empty":
            return res.to_dict()

    # 兜底：纯肽列表
    r = _parse_fasta_or_peptides(text)
    if r.kind != "empty":
        return r.to_dict()
    r.notes = r.notes or ["无法识别文件结构。支持：FASTA / 多肽列表 / CSV / TSV / xlsx / VCF / MAF。"]
    return r.to_dict()
