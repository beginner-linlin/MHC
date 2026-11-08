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
  - 列识别用别名打分表 + 前 15 行内找表头（IEDB epitope_table_export 顶部有多行
    标签如 EPITOPES / IEDB，真正表头常在第 3 行以后；标签行与说明行自动跳过）
  - 能提取的额外信息（等位基因列、蛋白名列、突变注释）一并返回
"""

from __future__ import annotations

import csv
import io
import os
import re
import time
from dataclasses import dataclass, field

from .runner import FastaRecord, looks_like_fasta, parse_fasta, parse_peptide_list, resolve_alleles

MAX_PEPTIDES = 20000
MAX_ROWS_SCAN = 20000
PEP_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBXZUJO*-]+$")

# IEDB 导出（epitope_table_export 等）顶部及分节处的固定标签词。
# 这些词全部由标准氨基酸字母组成（如 EPITOPES、REFERENCE），不挡掉就会被
# 当成肽段——「识别为多肽列表，2 条肽 EPITOPES/IEDB」误报的直接原因之一。
LABEL_WORDS = {
    "EPITOPES", "EPITOPE", "IEDB", "REFERENCE", "REFERENCES",
    "ASSAY", "ASSAYS", "MHC", "HOST", "ELISPOT", "POSITIVE", "NEGATIVE",
    "TCELL", "BCELL",
}

AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}

# 列别名（全部小写、去空格后匹配）。
# 打分制：3 = 明确的肽/序列语义；2 = 表位/结构/描述类（IEDB epitope_table_export
# 常把序列放在 Epitope Structure / Description 这类列里）；1 = 泛指列名（慎用，
# 仅在没有更强候选时兜底）。
PEP_COL_SCORED: list[tuple[str, int]] = [
    # —— 3 分：肽 / 序列语义 ——
    ("peptide", 3), ("peptides", 3), ("peptide seq", 3), ("peptide sequence", 3),
    ("mt peptide", 3), ("mut peptide", 3), ("mutant peptide", 3), ("mutated peptide", 3),
    ("alt peptide", 3), ("tumor peptide", 3), ("neoantigen", 3),
    ("linear sequence", 3), ("epitope sequence", 3), ("epitope seq", 3),
    ("sequence", 3), ("seq", 3), ("short sequence", 3),
    ("肽", 3), ("肽段", 3), ("序列", 3), ("突变肽", 3), ("抗原肽", 3),
    # —— 2 分：表位 / 结构 / 描述类 ——
    ("epitope", 2), ("epitope structure", 2), ("structure", 2),
    ("structure description", 2), ("description", 2), ("表位", 2),
    # —— 1 分：泛指列名 ——
    ("name", 1), ("名称", 1),
]
# 兼容旧引用：纯别名列表（不含打分信息）
PEP_COLS = [a for a, _ in PEP_COL_SCORED]
WT_PEP_COLS = ["wt peptide", "wt_peptide", "wildtype peptide", "wild type peptide",
               "ref peptide", "normal peptide", "野生型肽"]
# IEDB 导出的等位基因列常见写法：Allele / MHC Allele / HLA Allele /
# MHC - Allele Name / Restriction (Element) 等
ALLELE_COLS = ["allele", "alleles", "mhc", "hla", "mhc allele", "hla allele",
               "mhc_allele", "hla_allele", "allele name", "allele_name", "hla type",
               "mhc allele name", "hla allele name", "mhc restriction",
               "restriction", "restriction element",
               "hla_allele_1", "等位基因", "hla 分型"]
GENE_COLS = ["gene", "gene name", "gene_name", "hugo_symbol", "hugo symbol", "symbol",
             "protein", "protein name", "protein_name", "uniprot", "protein_id",
             "gene symbol", "基因", "蛋白", "蛋白名"]

# 这些列名开头的列绝不是肽列（IEDB 的 Epitope IRI / Object ID / Accession 等）
_PEP_COL_EXCLUDE = ("epitope iri", "epitope id", "object id", "iri", "url",
                    "accession", "sequence id", "seq id", "id")


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


def _pep_col_score(header: str) -> int:
    """表头列的「肽语义」打分：0 = 不是肽列。

    IRI / ID / URL / Accession 开头的列（IEDB 的 Epitope IRI、Object ID 等）
    一律 0 分，避免前缀匹配把标识列误当肽列。
    """
    k = _norm_key(header)
    if not k:
        return 0
    for ex in _PEP_COL_EXCLUDE:
        e = _norm_key(ex)
        if k == e or k.startswith(e):
            return 0
    best = 0
    for a, s in PEP_COL_SCORED:
        an = _norm_key(a)
        if k == an or k.startswith(an) or an.startswith(k):
            best = max(best, s)
    return best


def _is_label_word(s: str) -> bool:
    """IEDB 导出顶部的固定标签词（EPITOPES / IEDB / REFERENCE …）。"""
    return _clean_cell(s).upper() in LABEL_WORDS


def _drop_label_tokens(peps: list[str]) -> tuple[list[str], int]:
    """从肽列表里剔除标签词条目，返回 (保留列表, 剔除数)。"""
    kept = [p for p in peps if p not in LABEL_WORDS]
    return kept, len(peps) - len(kept)


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
    peps, n_label = _drop_label_tokens(peps)
    if peps:
        # 收紧无表头兜底：中位长度必须在 8–15aa，否则更像说明文字而不是肽列表
        med = sorted(len(p) for p in peps)[len(peps) // 2]
        if not (8 <= med <= 15):
            return ParseResult(
                kind="empty",
                notes=[
                    f"未识别出表头，且内容不像肽段列表（中位长度 {med}aa，肽段应约为 8–15aa），"
                    "已放弃按肽列表解析。"
                ],
            )
        res = ParseResult(format="多肽列表", kind="peptides", peptides=peps)
        if n_label:
            res.notes.append(f"已跳过 {n_label} 行非肽内容（如标题/说明行）。")
        return res
    if n_label:
        return ParseResult(
            kind="empty",
            notes=["内容只包含标题/标签行（如 EPITOPES、IEDB），没有识别到任何肽段。"],
        )
    return ParseResult(kind="empty", notes=["没有识别到任何序列。"])


def _parse_table(rows: list[list[str]], source_format: str) -> ParseResult:
    """rows: 已切好的单元格矩阵（含表头行）。"""
    res = ParseResult(format=source_format)
    if not rows:
        res.notes = ["表格为空。"]
        return res

    # 1. 在前 15 行里找表头（打分制）。
    #    IEDB epitope_table_export 顶部有多行标签（EPITOPES / IEDB / 说明行），
    #    真正的表头常在第 3 行以后。逐行统计命中的肽列/等位基因列/基因列别名，
    #    取总分最高的行；得分相同时先看肽列得分，再看行序。
    header_idx = -1
    pep_col = allele_col = gene_col = -1
    best_key = (0, 0)  # (总分, 肽列得分)
    for i, row in enumerate(rows[:15]):
        cells = [_clean_cell(c) for c in row]
        # 全部由标签词（或空单元格）组成的行不是表头：EPITOPES / IEDB / REFERENCE …
        if cells and all(c == "" or _is_label_word(c) for c in cells):
            continue
        pc, pc_score = -1, 0
        for j, c in enumerate(cells):
            s = _pep_col_score(c)
            if s > pc_score:
                pc, pc_score = j, s
        ac = next((j for j, c in enumerate(cells) if _match_col(c, ALLELE_COLS)), -1)
        gc = next((j for j, c in enumerate(cells) if _match_col(c, GENE_COLS)), -1)
        if pc < 0 and ac < 0:
            continue
        key = (pc_score + (1 if ac >= 0 else 0) + (1 if gc >= 0 else 0), pc_score)
        if key > best_key:
            header_idx, pep_col, allele_col, gene_col, best_key = i, pc, ac, gc, key

    if header_idx < 0:
        # 无表头：逐行取第一个像肽段的单元格
        peps: list[str] = []
        skipped = 0
        for row in rows[:MAX_ROWS_SCAN]:
            picked = None
            for c in row:
                s = _clean_cell(c).upper()
                if _is_peptide(s) and len(s) >= 6 and s not in LABEL_WORDS:
                    picked = s
                    break
            if picked:
                peps.append(picked)
            elif any(_clean_cell(c) for c in row):
                skipped += 1
        if peps:
            # 收紧兜底：中位长度必须在 8–15aa，否则更像说明文字而不是肽列表
            med = sorted(len(p) for p in peps)[len(peps) // 2]
            if 8 <= med <= 15:
                res.kind = "peptides"
                res.peptides = peps
                res.notes.append("未找到表头，已按「每行第一个像肽段的单元格」提取。")
                if skipped:
                    res.notes.append(f"已跳过 {skipped} 行非肽内容（如标题/说明行）。")
            else:
                res.notes.append(
                    f"未找到表头，且内容不像肽段列表（中位长度 {med}aa，肽段应约为 8–15aa），"
                    "已放弃按肽列表解析。"
                )
        else:
            res.notes.append("表格里没有找到肽段样式的列。")
        return res

    data = rows[header_idx + 1: header_idx + 1 + MAX_ROWS_SCAN]
    peps, alleles_raw, names = [], [], []
    skipped = 0
    for row in data:
        if not any(_clean_cell(c) for c in row):
            continue
        get = lambda j: _clean_cell(row[j]) if 0 <= j < len(row) else ""   # noqa: E731
        pep = get(pep_col).upper() if pep_col >= 0 else ""
        if pep and PEP_RE.match(pep) and len(pep) >= 8 and pep not in LABEL_WORDS:
            peps.append(pep)
            if allele_col >= 0:
                alleles_raw.append(get(allele_col))
            if gene_col >= 0:
                names.append(get(gene_col))
        else:
            # 标题/说明行、IRI/ID 列、过短碎片等一律视为非肽内容
            skipped += 1
    if skipped:
        res.notes.append(f"已跳过 {skipped} 行非肽内容（如标题/说明行）。")
    if not peps:
        if pep_col >= 0:
            res.notes.append(f"表头已识别（肽列 = 第 {pep_col + 1} 列），但数据行里没有合法肽段。")
        else:
            res.notes.append("表头已识别，但没有找到肽段列（列名不在已知别名表内）。")
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


# ---------------------------------------------------------------- 诊断


#: 识别可疑时的原文落盘目录；可用环境变量 MHC_UPLOAD_DEBUG_DIR 覆盖（测试用）
DEBUG_UPLOAD_DIR = os.environ.get("MHC_UPLOAD_DEBUG_DIR") or "/opt/bio/app/data/uploads"


def save_upload_for_debug(text: str, filename: str) -> str:
    """把疑似识别失败的原文写到磁盘，供人工核对真实文件结构。

    纯函数实现（不依赖 Flask）；目录不存在时自动创建；同秒重名自动加序号。
    返回保存路径。
    """
    ts = time.strftime("%Y%m%d_%H%M%S")
    base = re.sub(r"[^A-Za-z0-9._\-]+", "_", os.path.basename(filename or "")).strip("_")
    base = base or "upload.txt"
    os.makedirs(DEBUG_UPLOAD_DIR, exist_ok=True)
    path = os.path.join(DEBUG_UPLOAD_DIR, f"{ts}_{base}")
    n = 1
    while os.path.exists(path):
        path = os.path.join(DEBUG_UPLOAD_DIR, f"{ts}_{n}_{base}")
        n += 1
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text or "")
    return path


# ---------------------------------------------------------------- 总入口


def parse_any(text: str = "", *, filename: str = "", raw: bytes | None = None) -> dict:
    """识别并解析输入文件。text 为文本内容；raw 为原始字节（xlsx 二进制）。

    识别结果可疑（kind=empty，或 kind=peptides 且肽数 ≤3）时，顺带把原文
    落盘（save_upload_for_debug），并在返回 dict 附加 debug_saved=<路径>；
    落盘失败不影响解析本身。
    """
    result = _parse_any_impl(text, filename=filename, raw=raw)
    try:
        kind = result.get("kind")
        if kind == "empty" or (kind == "peptides" and result.get("peptide_count", 0) <= 3):
            dump = text or (raw.decode("utf-8", "replace") if raw else "")
            result["debug_saved"] = save_upload_for_debug(dump, filename)
    except Exception:  # noqa: BLE001 诊断落盘失败不影响主解析
        pass
    return result


def _parse_any_impl(text: str = "", *, filename: str = "", raw: bytes | None = None) -> dict:
    """parse_any 的实际解析逻辑（见 parse_any 文档字符串）。"""
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
