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
) -> tuple[bytes, str, str]:
    """返回 (字节, 文件名, MIME)。"""
    table = {
        "pan": ("NetMHCpan结果", PAN_COLUMNS),
        "chop": ("NetChop结果", CHOP_COLUMNS),
        "stab": ("NetMHCstabpan结果", STAB_COLUMNS),
        "pipeline": ("串联流水线结果", PIPE_COLUMNS),
        "mutant": ("突变肽筛选结果", MUT_COLUMNS),
    }
    label, columns = table.get(kind, ("结果", PAN_COLUMNS))
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
