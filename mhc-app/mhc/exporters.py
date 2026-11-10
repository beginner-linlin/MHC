"""结果导出：CSV（UTF-8 BOM，Excel 直接打开不乱码）与 xlsx。"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------- 列定义


PAN_COLUMNS = [
    ("pos", "位置", 8),
    ("mhc", "MHC", 16),
    ("peptide", "肽段", 18),
    ("core", "核心序列", 18),
    ("icore", "结合核心", 18),
    ("identity", "来源蛋白", 18),
    ("score_el", "EL 得分", 11),
    ("rank_el", "EL 排名%", 11),
    ("score_ba", "BA 得分", 11),
    ("rank_ba", "BA 排名%", 11),
    ("aff_nm", "亲和力 nM", 13),
    ("bind", "结合等级", 11),
]

CHOP_COLUMNS = [
    ("protein", "蛋白", 18),
    ("pos", "位置", 8),
    ("aa", "氨基酸", 10),
    ("cleavage", "切割位点", 11),
    ("score", "切割概率", 12),
]

STAB_COLUMNS = [
    ("pos", "位置", 8),
    ("hla", "HLA", 16),
    ("peptide", "肽段", 18),
    ("identity", "来源蛋白", 18),
    ("pred", "稳定性得分", 13),
    ("thalf", "半衰期(h)", 12),
    ("rank_stab", "稳定性排名%", 13),
    ("l50", "1-log50k", 12),
    ("aff", "亲和力 nM", 13),
    ("rank_aff", "亲和力排名%", 14),
    ("combined", "综合得分", 12),
    ("combined_rank", "综合排名%", 12),
    ("bind", "结合等级", 11),
]

PIPE_COLUMNS = [
    ("protein", "来源蛋白", 18),
    ("cut_pos", "切割位点", 11),
    ("cut_score", "切割概率", 12),
    ("peptide", "候选肽", 18),
    ("mhc", "HLA", 16),
    ("rank_el", "EL 排名%", 11),
    ("aff_nm", "亲和力 nM", 13),
    ("bind_pan", "结合等级", 11),
    ("thalf", "半衰期(h)", 12),
    ("rank_stab", "稳定性排名%", 13),
    ("combined_rank", "综合排名%", 13),
]

_NUM_FMT = "0.000"

MUT_COLUMNS = [
    ("pos", "肽起点", 10),
    ("peptide", "突变肽", 18),
    ("ref_peptide", "野生型肽", 18),
    ("mutation", "突变", 12),
    ("mhc", "HLA", 16),
    ("rank_el", "EL 排名%", 11),
    ("score_el", "EL 得分", 11),
    ("aff_nm", "亲和力 nM", 13),
    ("bind_pan", "结合等级", 11),
    ("thalf", "半衰期(h)", 12),
    ("rank_stab", "稳定性排名%", 13),
    ("combined_rank", "综合排名%", 13),
]

NEO_COLUMNS = [
    ("gene", "基因", 10),
    ("mutation", "突变", 11),
    ("accession", "UniProt", 12),
    ("pos", "肽起点", 9),
    ("peptide", "突变肽", 17),
    ("ref_peptide", "野生型肽", 17),
    ("mhc", "HLA", 15),
    ("rank_el", "EL 排名%", 10),
    ("score_el", "EL 得分", 10),
    ("aff_nm", "亲和力 nM", 12),
    ("bind_pan", "结合等级", 10),
    ("wt_rank_el", "野生型排名%", 12),
    ("wt_aff_nm", "野生型亲和力", 13),
    ("delta_rank", "Δ排名", 10),
    ("cut_pos", "切割位点", 10),
    ("cut_score", "切割概率", 10),
    ("thalf", "半衰期(h)", 11),
    ("rank_stab", "稳定性排名%", 12),
    ("combined_rank", "综合排名%", 12),
]

ALIGN_COLUMNS = [
    ("query", "查询序列", 18),
    ("query_len", "查询长度", 10),
    ("ref", "参考序列", 16),
    ("pos", "起点", 8),
    ("end", "终点", 8),
    ("strand", "方向", 7),
    ("mapq", "MAPQ", 8),
    ("identity", "一致性", 10),
    ("matches", "匹配", 8),
    ("mismatches", "错配", 8),
    ("insertions", "插入", 8),
    ("deletions", "缺失", 8),
    ("nm", "编辑距离", 10),
    ("score", "比对得分", 10),
    ("cigar", "CIGAR", 16),
    ("diff_count", "差异数", 9),
    ("ref_aligned", "参考片段", 30),
    ("query_aligned", "查询片段", 30),
]

GDC_COLUMNS = [
    ("gene", "基因", 10),
    ("aa_change", "氨基酸改变", 14),
    ("consequence_type", "变异类型", 20),
    ("dna_change", "基因组改变", 28),
    ("chromosome", "染色体", 9),
    ("start", "起点", 12),
    ("end", "终点", 12),
    ("ref", "参考碱基", 11),
    ("alt", "突变碱基", 11),
    ("mutation_type", "突变类型", 22),
    ("mutation_subtype", "突变亚型", 18),
    ("build", "参考基因组", 12),
    ("transcript_id", "转录本", 20),
    ("ssm_id", "SSM ID", 38),
]

# IEDB 返回的列随预测方法变化（netmhcpan_el 给 score，netmhcpan_ba 给 ic50，
# consensus 给一大堆子方法列），所以列定义只能从返回行动态推导，这里只负责中文化。
IEDB_LABELS = {
    "allele": "HLA",
    "peptide": "肽段",
    "seq_num": "序号",
    "start": "起点",
    "end": "终点",
    "length": "长度",
    "core_peptide": "核心肽",
    "core": "核心肽",
    "icore": "核心肽(内含)",
    "ic50": "IC50 nM",
    "score": "得分",
    "rank": "排名%",
    "percentile_rank": "百分位排名%",
    "adjusted_rank": "校正排名%",
    "ann_ic50": "ANN IC50",
    "ann_rank": "ANN 排名%",
    "smm_ic50": "SMM IC50",
    "smm_rank": "SMM 排名%",
    "smmpmbec_ic50": "SMMPMBEC IC50",
    "smmpmbec_rank": "SMMPMBEC 排名%",
    "comblib_sidney2008_score": "Comblib 得分",
    "comblib_sidney2008_rank": "Comblib 排名%",
    "consensus_percentile_rank": "Consensus 百分位%",
    "netmhcpan_ic50": "NetMHCpan IC50",
    "netmhcpan_rank": "NetMHCpan 排名%",
    "netmhcpan_exp": "NetMHCpan 实验值",
    "n_binders": "结合数",
    "project": "项目",
}


def dynamic_columns(
    rows: Sequence[dict],
    labels: dict[str, str] | None = None,
) -> list[tuple[str, str, int]]:
    """从返回行的键推导列定义（中文标签缺失时回退原键名）。

    跳过以下划线开头的内部键——前端渲染表格时也做了同样的过滤。
    """
    if not rows:
        return []
    labels = labels or {}
    out: list[tuple[str, str, int]] = []
    seen = set()
    for row in rows[:1]:
        for key in row.keys():
            if str(key).startswith("_") or key in seen:
                continue
            seen.add(key)
            label = labels.get(str(key), str(key))
            width = max(10, min(28, len(label) * 2 + 6))
            out.append((str(key), label, width))
    return out

HEADER_FILL = PatternFill("solid", fgColor="1E3A5F")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
BORDER = Border(*[Side(style="thin", color="D0D7DE")] * 4)
SB_FILL = PatternFill("solid", fgColor="C6E6C6")
WB_FILL = PatternFill("solid", fgColor="FDF3C6")


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:  # NaN
            return ""
        return f"{value:.4f}".rstrip("0").rstrip(".") if abs(value) < 1e6 else f"{value:.2f}"
    return str(value)


def to_csv(rows: Sequence[dict], columns: Sequence[tuple[str, str, int]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([c[1] for c in columns])
    for row in rows:
        writer.writerow([_fmt(row.get(c[0])) for c in columns])
    # UTF-8 BOM 让 Excel 正确识别中文
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def to_xlsx(
    rows: Sequence[dict],
    columns: Sequence[tuple[str, str, int]],
    *,
    sheet_name: str = "结果",
    meta: dict[str, Any] | None = None,
) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31] or "结果"

    r = 1
    if meta:
        ws.cell(row=1, column=1, value=str(meta.get("title", ""))).font = Font(bold=True, size=13)
        r = 2
        for key, val in meta.get("lines", []):
            ws.cell(row=r, column=1, value=key).font = Font(bold=True, size=9, color="666666")
            ws.cell(row=r, column=2, value=str(val)).font = Font(size=9)
            r += 1
        r += 1

    header_row = r
    for ci, (_, label, width) in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=ci, value=label)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(ci)].width = max(9, min(width, 30))

    bind_idx = None
    for ci, (key, _, _) in enumerate(columns, start=1):
        if key in ("bind", "bind_pan"):
            bind_idx = ci
            break

    for ri, row in enumerate(rows, start=header_row + 1):
        for ci, (key, _, _) in enumerate(columns, start=1):
            val = row.get(key)
            cell = ws.cell(row=ri, column=ci, value=val if not isinstance(val, float) else round(val, 4))
            cell.border = BORDER
            cell.font = Font(size=10)
            if isinstance(val, float):
                cell.number_format = _NUM_FMT
                cell.alignment = Alignment(horizontal="right")
            elif isinstance(val, int):
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="left")
        if bind_idx:
            bindval = str(row.get(columns[bind_idx - 1][0]) or "")
            if "SB" in bindval:
                for ci in range(1, len(columns) + 1):
                    ws.cell(row=ri, column=ci).fill = SB_FILL
            elif "WB" in bindval:
                for ci in range(1, len(columns) + 1):
                    ws.cell(row=ri, column=ci).fill = WB_FILL

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(len(columns))}{header_row + len(rows)}"
        )

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def export_rows(
    rows: Sequence[dict],
    kind: str,
    fmt: str,
    *,
    meta: dict[str, Any] | None = None,
    columns: Sequence[tuple[str, str, int]] | None = None,
    label: str | None = None,
) -> tuple[bytes, str, str]:
    """返回 (字节, 文件名, MIME)。

    `columns` / `label` 显式给出时优先使用——IEDB 这类外部接口的列随预测方法
    变化，只能从返回行动态推导，不能在模块级写死。
    """
    table = {
        "pan": ("NetMHCpan结果", PAN_COLUMNS),
        "chop": ("NetChop结果", CHOP_COLUMNS),
        "stab": ("NetMHCstabpan结果", STAB_COLUMNS),
        "pipeline": ("串联流水线结果", PIPE_COLUMNS),
        "mutant": ("突变肽筛选结果", MUT_COLUMNS),
        "neoantigen": ("新抗原候选肽", NEO_COLUMNS),
        "align": ("序列比对结果", ALIGN_COLUMNS),
        "gdc": ("GDC突变检索", GDC_COLUMNS),
        "iedb": ("IEDB预测结果", None),  # 列随方法变化，运行时推导
    }
    tbl_label, tbl_cols = table.get(kind, ("结果", PAN_COLUMNS))
    label = label or tbl_label
    if columns is not None:
        columns = list(columns)
    elif tbl_cols is None:
        columns = dynamic_columns(rows, IEDB_LABELS)
    else:
        columns = list(tbl_cols)
    if not columns:
        columns = list(PAN_COLUMNS)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "xlsx":
        data = to_xlsx(rows, columns, sheet_name=label, meta=meta)
        return (
            data,
            f"{label}_{stamp}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    data = to_csv(rows, columns)
    return data, f"{label}_{stamp}.csv", "text/csv; charset=utf-8"


def write_export(
    rows: Sequence[dict],
    kind: str,
    fmt: str,
    out_dir: Path,
    *,
    name: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Path:
    data, filename, _ = export_rows(rows, kind, fmt, meta=meta)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / (name or filename)
    path.write_bytes(data)
    return path
