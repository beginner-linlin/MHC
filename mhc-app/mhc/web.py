"""Flask 后端：把三个工具包装成 JSON API。

端点分区：
  /api/health            健康检查与工具版本
  /api/alleles           HLA 等位基因清单
  /api/validate/input    输入预检（长度、非标准残基、重复）
  /api/jobs/*            提交/查询/取消任务，导出结果
  /api/history           历史记录
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file

from . import __version__, exporters
from . import resources as resources_mod
from .fileformats import build_pairs, parse_any
from .jobs import JobStore, Progress, STATUS_DONE, STATUS_FAILED, STATUS_RUNNING
from .pipeline import mutant_peptides, run_pipeline
from .runner import (
    FastaRecord,
    STANDARD_AA,
    ToolCaller,
    ToolError,
    list_alleles,
    looks_like_fasta,
    nonstandard_residues,
    parse_fasta,
    parse_peptide_list,
    predict_binding,
    predict_cleavage,
    predict_stability,
    predict_stability_mixed,
    resolve_alleles,
    tool_version,
)

APP_ROOT = Path(os.environ.get("MHC_APP_ROOT", "/opt/bio/app"))
DATA_DIR = APP_ROOT / "data"
WORK_DIR = APP_ROOT / "work"
EXPORT_DIR = APP_ROOT / "exports"
DB_PATH = DATA_DIR / "mhc.sqlite3"

for d in (DATA_DIR, WORK_DIR, EXPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

MAX_BODY = 32 * 1024 * 1024  # 32 MB

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
app.json.ensure_ascii = False

store = JobStore(DB_PATH)


# ---------------------------------------------------------------- 工具


def caller() -> ToolCaller:
    return ToolCaller(workdir=WORK_DIR / "scratch")


def api_error(message: str, status: int = 400, **extra: Any) -> tuple[Response, int]:
    payload = {"ok": False, "error": message, **extra}
    return jsonify(payload), status


def body() -> dict:
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------- 健康检查


@app.get("/api/health")
def health() -> Response:
    c = caller()
    tools = {}
    for name in ("netMHCpan", "netchop", "netMHCstabpan"):
        try:
            tools[name] = tool_version(c, name)
        except Exception as exc:  # noqa: BLE001
            tools[name] = f"不可用: {exc}"
    return jsonify(
        {
            "ok": True,
            "app_version": __version__,
            "tools": tools,
            "running_jobs": store.running_count(),
            "history_count": store.count(),
            "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
            "data_dir": str(DATA_DIR),
        }
    )


@app.get("/api/alleles")
def alleles() -> Response:
    q = (request.args.get("q") or "").strip().upper()
    try:
        limit = max(1, min(int(request.args.get("limit", 2000)), 20000))
    except (TypeError, ValueError):
        limit = 2000
    try:
        items = list_alleles(caller())
    except Exception as exc:  # noqa: BLE001
        return api_error(f"读取等位基因列表失败：{exc}", 500)
    total_all = len(items)
    if q:
        items = [a for a in items if q in a.upper()]
    return jsonify({
        "ok": True,
        "total": total_all,
        "matched": len(items),
        "alleles": items[:limit],
        "truncated": len(items) > limit,
    })


@app.get("/api/presets")
def presets() -> Response:
    """常用等位基因预设。"""
    common = [
        ("HLA-A02:01", "A*02:01（人群最常见）"),
        ("HLA-A01:01", "A*01:01"),
        ("HLA-A03:01", "A*03:01"),
        ("HLA-A24:02", "A*24:02（东亚常见）"),
        ("HLA-A11:01", "A*11:01（东亚常见）"),
        ("HLA-B07:02", "B*07:02"),
        ("HLA-B08:01", "B*08:01"),
        ("HLA-B15:01", "B*15:01"),
        ("HLA-B35:01", "B*35:01"),
        ("HLA-B40:01", "B*40:01（东亚常见）"),
        ("HLA-C07:01", "C*07:01"),
        ("HLA-C07:02", "C*07:02"),
    ]
    mouse = [
        ("H2-Db", "小鼠 H2-Db"),
        ("H2-Kb", "小鼠 H2-Kb"),
        ("H2-Ld", "小鼠 H2-Ld"),
    ]
    return jsonify({"ok": True, "human": common, "mouse": mouse})


# ---------------------------------------------------------------- 资源中心


@app.get("/api/resources")
def resources() -> Response:
    """数据库 + 在线工具清单（含可达状态、本地替代方案）。"""
    try:
        return jsonify({"ok": True, **resources_mod.resource_catalog()})
    except Exception as exc:  # noqa: BLE001
        return api_error(f"读取资源清单失败：{exc}", 500)


@app.get("/api/gdc/summary")
def gdc_summary() -> Response:
    project = (request.args.get("project") or "TCGA-PAAD").strip()
    try:
        return jsonify({"ok": True, "summary": resources_mod.gdc_project_summary(project)})
    except resources_mod.ResourceError as exc:
        return api_error(exc.message, exc.status, detail=exc.detail)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"GDC 查询失败：{exc}", 502)


@app.post("/api/gdc/mutations")
def gdc_mutations() -> Response:
    """GDC 体细胞突变检索（TCGA-PAAD 等）。"""
    payload = body()
    raw_project = payload.get("project")
    project = (raw_project if raw_project is not None else "TCGA-PAAD").strip()
    gene = (payload.get("gene") or "").strip() or None
    chromosome = (payload.get("chromosome") or "").strip() or None
    mutation_type = (payload.get("mutation_type") or "").strip() or None
    if not gene and not chromosome and not project:
        return api_error("请至少指定项目、基因或染色体之一。")
    try:
        result = resources_mod.search_gdc_mutations(
            project=project,
            gene=gene,
            chromosome=chromosome,
            mutation_type=mutation_type,
            size=int(payload.get("size") or 200),
            offset=int(payload.get("offset") or 0),
        )
        return jsonify({"ok": True, **result})
    except resources_mod.ResourceError as exc:
        return api_error(exc.message, exc.status, detail=exc.detail)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"GDC 查询失败：{exc}", 502)


@app.post("/api/iedb/predict")
def iedb_predict() -> Response:
    """IEDB tools_api 云端 MHC-I/II 预测。"""
    payload = body()
    raw = payload.get("input") or ""
    peptides = parse_peptide_list(raw)
    if not peptides:
        return api_error("没有识别到肽段。请每行一条，或用蛋白 FASTA 走本地工具。")

    # MHC-II 等位基因形如 HLA-DRB1*01:01，星号必须保留，
    # 不能走本地工具的 resolve_alleles（它按 HLA-A/B/C 规则去星号，会破坏 II 类名）
    alleles = [str(a).strip().upper() for a in (payload.get("alleles") or []) if str(a).strip()]
    if not alleles:
        return api_error("请至少选择一个 HLA 等位基因。")
    if len(alleles) > 5:
        return api_error("IEDB 一次最多 5 个等位基因，请分批提交。")
    if len(peptides) > 500:
        return api_error("IEDB 一次最多 500 条肽，请分批提交。")

    mhc_class = (payload.get("mhc_class") or "I").upper().lstrip("MHC-")
    method = payload.get("method") or ("netmhcpan_el" if mhc_class == "I" else "recommended")
    try:
        length = int(payload.get("length") or (9 if mhc_class == "I" else 15))
    except (TypeError, ValueError):
        length = 9 if mhc_class == "I" else 15

    all_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for allele in alleles:
        try:
            res = resources_mod.iedb_predict(
                mhc_class=mhc_class,
                method=method,
                peptides=peptides,
                allele=allele,
                length=length,
            )
            for r in res["rows"]:
                r["_allele"] = allele
                r["_method"] = method
            all_rows.extend(res["rows"])
        except resources_mod.ResourceError as exc:
            errors.append(f"{allele}: {exc.message} {exc.detail[:200]}")
    if not all_rows and errors:
        return api_error("IEDB 预测失败", 502, detail="; ".join(errors))

    return jsonify(
        {
            "ok": True,
            "mhc_class": mhc_class,
            "method": method,
            "alleles": alleles,
            "peptides": len(peptides),
            "count": len(all_rows),
            "rows": all_rows,
            "errors": errors,
        }
    )


# ---------------------------------------------------------------- 输入预检


def _collect_inputs(payload: dict) -> tuple[list[str], list[FastaRecord], str]:
    """从请求中抽取 (肽列表, FASTA 记录, 输入类型)。"""
    raw = payload.get("input") or ""
    mode = payload.get("input_mode") or "auto"

    if mode == "fasta" or (mode == "auto" and looks_like_fasta(raw)):
        return [], parse_fasta(raw), "fasta"
    peptides = parse_peptide_list(raw)
    return peptides, [], "peptide"


def _is_ns(seq: str) -> bool:
    """序列是否含非标准氨基酸（超出 20 种标准残基）。"""
    return bool(seq) and bool(nonstandard_residues([seq]))


def _ns_action(payload: dict) -> str:
    action = str(payload.get("nonstandard_action") or "mark").strip().lower()
    return action if action in ("mark", "skip", "remove") else "mark"


def _apply_nonstandard(
    payload: dict, peptides: list[str], records: list[FastaRecord]
) -> tuple[str, list[str], list[FastaRecord], dict]:
    """按用户选择的策略处理含非标准残基的输入。

    返回 (action, 处理后的肽列表, 处理后的记录, 报告信息)。
    报告信息的键会合并进任务 result：
      nonstandard_skipped / nonstandard_removed      肽级处理数量
      skipped_peptides                                skip 模式占位行数据
      nonstandard_proteins_skipped                    被跳过的蛋白名列表
      all_nonstandard                                 全部输入都含非标准残基（调用方应报 400）
    """
    action = _ns_action(payload)
    info: dict[str, Any] = {"nonstandard_action": action}

    if action == "mark":
        return action, peptides, records, info

    if peptides:
        bad = [x for x in peptides if _is_ns(x)]
        if bad:
            good = [x for x in peptides if not _is_ns(x)]
            if not good:
                info["all_nonstandard"] = True
                return action, peptides, records, info
            if action == "skip":
                info["nonstandard_skipped"] = len(bad)
                info["skipped_peptides"] = [
                    {"peptide": x, "chars": sorted(nonstandard_residues([x]))} for x in bad
                ]
            else:
                info["nonstandard_removed"] = len(bad)
            return action, good, records, info
        return action, peptides, records, info

    if records:
        bad_recs = [r for r in records if _is_ns(r.seq)]
        if bad_recs:
            good = [r for r in records if not _is_ns(r.seq)]
            if not good:
                info["all_nonstandard"] = True
                return action, peptides, records, info
            info["nonstandard_proteins_skipped"] = [r.name for r in bad_recs]
            return action, peptides, good, info
    return action, peptides, records, info


@app.post("/api/validate/input")
def validate_input() -> Response:
    payload = body()
    peptides, records, kind = _collect_inputs(payload)
    warnings: list[dict] = []
    stats: dict[str, Any] = {"kind": kind}

    # 每个工具对长度的要求不同，必须按实际要跑的模式判断，不能一刀切
    #   netMHCpan   : 肽长 >= 8（<8 直接报 Error: peptide must be of length >= 8）
    #   netMHCstabpan: 肽长 7–20 有数值，<7 也会出 1 行但亲和力列为空 → 只 warn
    #   netchop     : 任意长度都能跑，1 个残基也出行 → 不校验
    mode = (payload.get("mode") or "").strip().lower()
    # 缺省（旧调用方不带 mode）按最严格的 pan 规则校验，宁可误拦不可漏拦
    need_pan = mode in ("pan", "pipeline", "mutant") or not mode
    need_stab_chk = mode in ("stab", "pipeline", "mutant")

    seqs = [r.seq for r in records] if records else peptides
    if not seqs:
        return api_error("没有识别到任何序列。请粘贴 FASTA（以 > 开头）或每行一条肽。")

    bad = nonstandard_residues(seqs)
    if bad:
        action = _ns_action(payload)
        ns_count_pep = sum(1 for x in peptides if _is_ns(x)) if kind == "peptide" else 0
        ns_count_rec = sum(1 for r in records if _is_ns(r.seq)) if kind == "fasta" else 0
        if action == "mark":
            warnings.append(
                {
                    "level": "warn",
                    "code": "nonstandard_aa",
                    "message": f"发现非标准氨基酸：{', '.join(sorted(bad))}"
                    f"（{ns_count_pep or ns_count_rec} 条序列受影响）。"
                    "当前策略为「标记并预测」：这些序列会照常计算，结果行会带 ⚠ 标记；"
                    "工具内部把非标准字符当作 X，预测值仅供参考。",
                }
            )
        elif action == "skip":
            warnings.append(
                {
                    "level": "info",
                    "code": "nonstandard_aa",
                    "message": f"发现非标准氨基酸：{', '.join(sorted(bad))}。"
                    "当前策略为「跳过」：含非标准残基的序列不参与预测，"
                    "结果表中以灰色占位行标出。",
                }
            )
        else:  # remove
            warnings.append(
                {
                    "level": "info",
                    "code": "nonstandard_aa",
                    "message": f"发现非标准氨基酸：{', '.join(sorted(bad))}。"
                    "当前策略为「删除」：含非标准残基的序列将被移除，不参与预测、不在结果中出现。",
                }
            )

    if kind == "peptide":
        lengths = sorted({len(p) for p in peptides})
        stats["count"] = len(peptides)
        stats["lengths"] = lengths
        shortest = min(lengths)
        if need_pan and shortest < 8:
            warnings.append(
                {
                    "level": "error",
                    "code": "too_short",
                    "message": f"存在长度 {shortest} 的肽，netMHCpan 要求 ≥ 8。",
                }
            )
        elif need_stab_chk and shortest < 7:
            warnings.append(
                {
                    "level": "warn",
                    "code": "stab_short",
                    "message": f"存在长度 {shortest} 的肽，低于 NetMHCstabpan 的可靠范围（7–20），"
                    "亲和力列可能为空。",
                }
            )
        if need_stab_chk and max(lengths) > 20:
            warnings.append(
                {
                    "level": "warn",
                    "code": "stab_long",
                    "message": f"存在长度 {max(lengths)} 的肽，超出 NetMHCstabpan 的可靠范围（7–20）。",
                }
            )
        if len(lengths) > 1:
            warnings.append(
                {
                    "level": "warn",
                    "code": "mixed_length",
                    "message": f"肽长不一致（{lengths}）。netMHCstabpan 已自动按长度分组分别计算，结果正常。",
                }
            )
        dup = len(peptides) - len(set(peptides))
        if dup:
            warnings.append(
                {"level": "info", "code": "duplicate", "message": f"有 {dup} 条重复肽，已在上游去重。"}
            )
        if len(peptides) > 5000:
            warnings.append(
                {"level": "warn", "code": "large", "message": f"共 {len(peptides)} 条肽，预计耗时较长。"}
            )
    else:
        stats["count"] = len(records)
        stats["lengths"] = [len(r.seq) for r in records]
        stats["names"] = [r.name for r in records][:50]
        # 只有需要切肽（pan/pipeline/mutant）时才关心蛋白够不够长
        if need_pan:
            try:
                shortest_need = int(payload.get("min_peptide_len") or 9)
            except (TypeError, ValueError):
                shortest_need = 9
            shortest_need = max(shortest_need, 8)  # netMHCpan 肽长下限
            short = [r for r in records if len(r.seq) < shortest_need]
            if short:
                warnings.append(
                    {
                        "level": "error",
                        "code": "protein_too_short",
                        "message": f"{len(short)} 条蛋白短于 {shortest_need}aa，无法切出可用肽段。",
                    }
                )
        long = [r for r in records if len(r.seq) > 20000]
        if long:
            warnings.append(
                {
                    "level": "warn",
                    "code": "protein_long",
                    "message": f"{len(long)} 条蛋白超过 20000aa，滑窗会产生大量肽段。",
                }
            )
        # 名字截断风险
        clipped = [r.name for r in records if len(r.name) > 10]
        if clipped:
            warnings.append(
                {
                    "level": "info",
                    "code": "name_clip",
                    "message": "工具内部只保留蛋白名前 10 个字符；应用已自动生成唯一短名并在结果中还原原名。",
                }
            )

    alleles = resolve_alleles(payload.get("alleles") or [])
    stats["alleles"] = alleles
    if not alleles:
        warnings.append({"level": "warn", "code": "no_allele", "message": "尚未选择等位基因。"})

    ok = not any(w["level"] == "error" for w in warnings)
    return jsonify({"ok": True, "valid": ok, "stats": stats, "warnings": warnings})


# ---------------------------------------------------------------- 文件解析


@app.post("/api/parse-file")
def parse_file() -> Response:
    """通用文件解析：IEDB / TCGA MAF / VCF / CSV / TSV / xlsx / FASTA / 肽列表 / HGVS 突变。"""
    payload = body()
    filename = (payload.get("filename") or "").strip()
    text = payload.get("text") or ""
    b64 = payload.get("content_b64") or ""
    raw: bytes | None = None
    if b64:
        try:
            raw = base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            return api_error("content_base64 不是合法的 base64 数据")
        if len(raw) > MAX_BODY:
            return api_error("文件过大（上限 32 MB）")
    elif not text:
        return api_error("没有收到文件内容（text 或 content_b64 至少给一个）")
    if not raw and not text.strip():
        return api_error("文件内容为空")
    try:
        result = parse_any(text=text, filename=filename, raw=raw)
    except Exception as exc:  # noqa: BLE001
        return api_error(f"解析文件时出错：{exc}", 500)
    result["filename"] = filename
    return jsonify(result)


# ---------------------------------------------------------------- 任务提交


def _title(kind: str, payload: dict) -> str:
    label = {"pan": "结合预测", "chop": "酶切预测", "stab": "稳定性预测",
             "pipeline": "串联流水线", "mutant": "突变肽筛选"}.get(kind, kind)
    n = payload.get("_input_count", 0)
    unit = payload.get("_input_unit") or "条序列"
    al = payload.get("alleles") or []
    al_txt = ", ".join(al[:2]) + (f" 等{len(al)}个" if len(al) > 2 else "")
    return f"{label} · {n} {unit}" + (f" · {al_txt}" if al_txt else "")


def _submit(kind: str, payload: dict, fn, *, count: int | None = None, unit: str = "条序列") -> Response:
    if count is None:
        peptides, records, _ = _collect_inputs(payload)
        count = len(records) or len(peptides)
    payload["_input_count"] = count
    payload["_input_unit"] = unit
    job = store.create(kind, _title(kind, payload), _sanitize_params(payload))
    store.submit(job, fn)
    return jsonify({"ok": True, "job": job.to_dict()})


def _sanitize_params(payload: dict) -> dict:
    """只保留可展示的参数，避免把整段序列塞进历史记录。"""
    out = {}
    for k, v in payload.items():
        if k == "input":
            out["_input_preview"] = (v or "")[:300]
            out["_input_len"] = len(v or "")
        else:
            out[k] = v
    return out


@app.post("/api/jobs/pan")
def submit_pan() -> Response:
    p = body()
    alleles = resolve_alleles(p.get("alleles") or [])
    if not alleles:
        return api_error("请至少选择一个 HLA 等位基因")
    peptides, records, _ = _collect_inputs(p)
    if not peptides and not records:
        return api_error("没有识别到任何序列。请粘贴 FASTA（以 > 开头）或每行一条肽。")

    action, peptides, records, ns_info = _apply_nonstandard(p, peptides, records)
    if ns_info.get("all_nonstandard"):
        return api_error(
            "全部输入序列都含非标准氨基酸，无可预测内容。"
            "可在左侧「非标准肽段处理」中改为「标记并预测」，或修改输入后再试。"
        )

    # mark 模式：记住哪些肽含非标准残基，结果行带 ⚠ 标记
    # 注意：工具回显时会把 B/Z 等非标准字符替换成 X，所以匹配用「位置+X 归一化」：
    # 输入肽与其工具回显版本（非标准位替换为 X）一一对应。
    ns_peptides = {x for x in (peptides or []) if _is_ns(x)} if action == "mark" else set()

    def _ns_key(p: str) -> str:
        """把序列中的非标准字符归一成 X，供与工具回显 peptide 对齐。"""
        return "".join(ch if ch in STANDARD_AA else "X" for ch in p.upper())

    ns_keys = {_ns_key(x) for x in ns_peptides}
    ns_exact = set(ns_peptides)

    def task(progress: Progress) -> dict:
        c = caller()
        progress.update("提交", 0.05, "")
        if records:
            rows, _, _ = predict_binding(
                c, records=records, alleles=alleles,
                with_ba=bool(p.get("with_ba", True)),
                sort=bool(p.get("sort")),
                threshold=p.get("threshold"),
            )
        else:
            rows, _, _ = predict_binding(
                c, peptides=peptides, alleles=alleles,
                with_ba=bool(p.get("with_ba", True)),
                sort=bool(p.get("sort")),
                threshold=p.get("threshold"),
            )
        out_rows = []
        for r in rows:
            d = r.to_dict()
            d["nonstandard"] = (r.peptide in ns_exact) or (r.peptide in ns_keys)
            out_rows.append(d)
        if action == "skip":
            for sp in ns_info.get("skipped_peptides", []):
                out_rows.append(
                    {
                        "pos": 0, "mhc": alleles[0] if alleles else "", "peptide": sp["peptide"],
                        "core": "", "icore": "", "identity": "PEPLIST",
                        "score_el": None, "rank_el": None, "score_ba": None,
                        "rank_ba": None, "aff_nm": None, "bind": None,
                        "nonstandard": True, "skipped": True,
                        "skipped_reason": f"非标准残基 {', '.join(sp['chars'])}",
                    }
                )
        progress.update("完成", 1.0, f"{len(out_rows)} 行")
        result = {"rows": out_rows, "count": len(out_rows)}
        result.update(ns_info)
        return result

    return _submit("pan", p, task)


@app.post("/api/jobs/chop")
def submit_chop() -> Response:
    p = body()
    _, records, _ = _collect_inputs(p)
    if not records:
        return api_error("酶切预测需要 FASTA 格式的蛋白序列（以 > 开头）")

    # 酶切是蛋白级预测：remove/skip 都按「丢弃含非标准残基的蛋白」处理
    action, _, records, ns_info = _apply_nonstandard(p, [], records)
    if ns_info.get("all_nonstandard"):
        return api_error(
            "全部蛋白序列都含非标准氨基酸，无可预测内容。"
            "可在左侧「非标准肽段处理」中改为「标记并预测」，或修改输入后再试。"
        )
    ns_proteins = {r.name for r in records if _is_ns(r.seq)} if action == "mark" else set()

    def task(progress: Progress) -> dict:
        c = caller()
        progress.update("酶切预测", 0.1, f"{len(records)} 条蛋白")
        groups, _, _ = predict_cleavage(
            c, records=records,
            version=int(p.get("model", 0)),
            threshold=float(p.get("threshold", 0.5)),
        )
        rows: list[dict] = []
        summary = []
        for name, rr in groups.items():
            sites = sum(1 for x in rr if x.cleavage == "S")
            ns = name in ns_proteins
            summary.append({"protein": name, "length": len(rr), "sites": sites,
                            "nonstandard": ns})
            for x in rr:
                rows.append(
                    {"protein": name, "pos": x.pos, "aa": x.aa,
                     "cleavage": x.cleavage, "score": x.score,
                     "nonstandard": ns}
                )
        progress.update("完成", 1.0, f"{len(rows)} 行")
        result = {"rows": rows, "count": len(rows), "summary": summary,
                  "model": int(p.get("model", 0)), "threshold": float(p.get("threshold", 0.5))}
        result.update(ns_info)
        return result

    return _submit("chop", p, task)


@app.post("/api/jobs/stab")
def submit_stab() -> Response:
    p = body()
    alleles = resolve_alleles(p.get("alleles") or [])
    if not alleles:
        return api_error("请至少选择一个 HLA 等位基因")
    peptides, records, _ = _collect_inputs(p)
    if not peptides and not records:
        return api_error("没有识别到任何序列。请粘贴 FASTA（以 > 开头）或每行一条肽。")

    action, peptides, records, ns_info = _apply_nonstandard(p, peptides, records)
    if ns_info.get("all_nonstandard"):
        return api_error(
            "全部输入序列都含非标准氨基酸，无可预测内容。"
            "可在左侧「非标准肽段处理」中改为「标记并预测」，或修改输入后再试。"
        )

    ns_peptides = {x for x in (peptides or []) if _is_ns(x)} if action == "mark" else set()

    def _ns_key(p: str) -> str:
        return "".join(ch if ch in STANDARD_AA else "X" for ch in p.upper())

    ns_keys = {_ns_key(x) for x in ns_peptides}

    def task(progress: Progress) -> dict:
        c = caller()
        progress.update("稳定性预测", 0.1, "")
        with_ia = bool(p.get("with_ia", True))
        sort = p.get("sort")
        sort = int(sort) if sort is not None and str(sort) != "" else None
        if records:
            rows, _, _ = predict_stability(
                c, records=records, alleles=alleles, with_ia=with_ia, sort=sort
            )
        else:
            rows, _ = predict_stability_mixed(
                c, peptides=peptides, alleles=alleles, with_ia=with_ia
            )
        out_rows = []
        for r in rows:
            d = r.to_dict()
            d["nonstandard"] = (r.peptide in ns_peptides) or (r.peptide in ns_keys)
            out_rows.append(d)
        if action == "skip":
            for sp in ns_info.get("skipped_peptides", []):
                out_rows.append(
                    {
                        "pos": 0, "hla": alleles[0] if alleles else "",
                        "peptide": sp["peptide"], "identity": "PEPLIST",
                        "pred": None, "thalf": None, "rank_stab": None, "l50": None,
                        "aff": None, "rank_aff": None, "combined": None,
                        "combined_rank": None, "bind": None,
                        "nonstandard": True, "skipped": True,
                        "skipped_reason": f"非标准残基 {', '.join(sp['chars'])}",
                    }
                )
        progress.update("完成", 1.0, f"{len(out_rows)} 行")
        result = {"rows": out_rows, "count": len(out_rows), "with_ia": with_ia}
        result.update(ns_info)
        return result

    return _submit("stab", p, task)


@app.post("/api/jobs/pipeline")
def submit_pipeline() -> Response:
    p = body()
    alleles = resolve_alleles(p.get("alleles") or [])
    if not alleles:
        return api_error("请至少选择一个 HLA 等位基因")
    _, records, _ = _collect_inputs(p)
    if not records:
        return api_error("串联流水线需要 FASTA 蛋白序列")

    # 流水线的非标准处理：mark=照跑（滑窗肽若含非标准残基行上带标记）
    # remove/skip=丢弃含非标准残基的蛋白（蛋白级，无法只删一条肽）
    action, _, records, ns_info = _apply_nonstandard(p, [], records)
    if ns_info.get("all_nonstandard"):
        return api_error(
            "全部蛋白序列都含非标准氨基酸，无可预测内容。"
            "可在左侧「非标准肽段处理」中改为「标记并预测」，或修改输入后再试。"
        )
    if ns_info.get("nonstandard_proteins_skipped"):
        action = "remove"  # 蛋白级丢弃
    ns_proteins = {r.name for r in records if _is_ns(r.seq)} if action == "mark" else set()

    lengths = p.get("peptide_lengths") or [9]
    lengths = [int(x) for x in lengths]

    def task(progress: Progress) -> dict:
        c = caller()
        result = run_pipeline(
            c, records=records, alleles=alleles,
            params={
                "cleavage_threshold": float(p.get("cleavage_threshold", 0.5)),
                "cleavage_model": int(p.get("cleavage_model", 0)),
                "peptide_lengths": lengths,
                "use_cleavage_filter": bool(p.get("use_cleavage_filter", True)),
                "max_rank_el": float(p.get("max_rank_el", 2.0)),
                "min_thalf": float(p.get("min_thalf", 0.0)),
                "include_ia": bool(p.get("include_ia", True)),
                "include_site": bool(p.get("include_site", True)),
            },
            progress=progress,
        )
        d = result.to_dict()
        # mark 模式：滑窗肽含非标准残基 → 行上打标
        if ns_proteins:
            for row in d.get("rows", []):
                if nonstandard_residues([row.get("peptide", "")]):
                    row["nonstandard"] = True
        d.update(ns_info)
        return d

    return _submit("pipeline", p, task)


@app.post("/api/jobs/mutant")
def submit_mutant() -> Response:
    p = body()
    alleles = resolve_alleles(p.get("alleles") or [])
    if not alleles:
        return api_error("请至少选择一个 HLA 等位基因")
    lengths = [int(x) for x in (p.get("peptide_lengths") or [9])]
    mutations = p.get("mutations") or []
    pair_notes: list[str] = []

    if mutations:
        # 文件驱动的突变筛选：input = 参考蛋白 FASTA，mutations = [{protein, pos, ref, alt}]
        records = parse_fasta(p.get("input") or "")
        if not records:
            return api_error(
                "携带突变列表时，参考序列框需要粘贴蛋白 FASTA（以 > 开头），"
                "蛋白名需与突变来源基因对应（如 >KRAS）。"
            )
        pairs, pair_notes = build_pairs(records, mutations)
        if not pairs:
            genes = ", ".join(sorted({m.get("protein") or "?" for m in mutations}))[:200]
            return api_error(f"突变（{genes}）没有匹配到参考 FASTA 里的任何蛋白。请核对蛋白名。")
    else:
        ref = (p.get("ref_seq") or "").strip().upper()
        alt = (p.get("alt_seq") or "").strip().upper()
        if not ref or not alt:
            return api_error("需要提供参考序列与突变序列")
        if len(ref) != len(alt):
            return api_error(f"两条序列长度必须一致（参考 {len(ref)}，突变 {len(alt)}）")
        pairs = [{"name": None, "ref": ref, "alt": alt,
                  "mutations": [{"pos": p_, "ref": a, "alt": b} for p_, a, b in _subs(ref, alt)]}]

    # 同步预生成候选肽：既用于标题里的数量，也用于「完全相同」的即时报错
    peptides: list[dict] = []
    for pair in pairs:
        peps = mutant_peptides(pair["ref"], pair["alt"], lengths)
        for x in peps:
            x["protein"] = pair["name"] or "mutant"
            x["mut_sites"] = x.get("mut_sites") or pair["mutations"]
        peptides.extend(peps)
    if not peptides:
        return api_error("参考与突变序列完全相同，未找到突变位点")
    if len(peptides) > 5000:
        peptides = peptides[:5000]
        pair_notes.append("候选肽超过 5000 条，已截断。")

    # 非标准处理（突变模式作用于候选肽级；参考肽含非标残基也算非标行）
    action = _ns_action(p)
    ns_peptides = {x["peptide"] for x in peptides if _is_ns(x["peptide"])}
    ns_ref_peptides = {
        x["ref_peptide"] for x in peptides if x.get("ref_peptide") and _is_ns(x["ref_peptide"])
    }
    ns_info: dict[str, Any] = {"nonstandard_action": action}

    def _ns_key(p2: str) -> str:
        return "".join(ch if ch in STANDARD_AA else "X" for ch in p2.upper())

    ns_keys = {_ns_key(x) for x in ns_peptides}
    ns_ref_keys = {_ns_key(x) for x in ns_ref_peptides}
    if action in ("skip", "remove") and (ns_peptides or ns_ref_peptides):
        kept = [
            x for x in peptides
            if x["peptide"] not in ns_peptides
            and not (x.get("ref_peptide") and x["ref_peptide"] in ns_ref_peptides)
        ]
        if not kept:
            return api_error(
                "全部突变候选肽都含非标准氨基酸，无可预测内容。"
                "可在左侧「非标准肽段处理」中改为「标记并预测」，或修改输入后再试。"
            )
        if action == "skip":
            skipped = ns_peptides | ns_ref_peptides
            ns_info["nonstandard_skipped"] = len(skipped)
            ns_info["skipped_peptides"] = [
                {"peptide": x, "chars": sorted(nonstandard_residues([x]))} for x in skipped
            ]
        else:
            ns_info["nonstandard_removed"] = len(ns_peptides) + len(ns_ref_peptides)
        peptides = kept

    def task(progress: Progress) -> dict:
        c = caller()
        peps = [x["peptide"] for x in peptides]
        progress.update("结合预测", 0.3, f"{len(peps)} 条突变肽")
        pan_rows, _, _ = predict_binding(c, peptides=peps, alleles=alleles, with_ba=True)
        progress.update("稳定性预测", 0.7, "")
        stab_rows, _ = predict_stability_mixed(c, peptides=peps, alleles=alleles, with_ia=True)

        stab_lookup = {(s.hla.replace("*", ""), s.peptide): s for s in stab_rows}
        # 工具会把非标残基回显成 X，因此索引同时保留原始名与 X 归一化名
        info: dict[str, dict] = {}
        for x in peptides:
            info[x["peptide"]] = x
            info.setdefault(_ns_key(x["peptide"]), x)

        rows = []
        for r in pan_rows:
            s = stab_lookup.get((r.mhc.replace("*", ""), r.peptide))
            meta = info.get(r.peptide) or info.get(_ns_key(r.peptide)) or {}
            rows.append(
                {
                    "protein": meta.get("protein", "mutant"),
                    "pos": meta.get("pos", 0),
                    "peptide": r.peptide,
                    "ref_peptide": meta.get("ref_peptide"),
                    "mutation": " / ".join(
                        f"{m['ref']}{m['pos']}{m['alt']}" for m in (meta.get("mut_sites") or [])
                    ),
                    "mut_sites": meta.get("mut_sites"),
                    "mhc": r.mhc,
                    "rank_el": r.rank_el,
                    "score_el": r.score_el,
                    "aff_nm": r.aff_nm,
                    "bind_pan": r.bind,
                    "thalf": s.thalf if s else None,
                    "rank_stab": s.rank_stab if s else None,
                    "combined_rank": s.combined_rank if s else None,
                    # 突变肽、其 X 归一化回显、或野生型对照含非标残基都算非标行
                    "nonstandard": (
                        bool(_is_ns(r.peptide))
                        or (r.peptide in ns_keys)
                        or bool(_is_ns(meta.get("ref_peptide") or ""))
                        or bool(_is_ns(meta.get("peptide") or ""))
                    ) if action == "mark" else False,
                }
            )
        if action == "skip":
            for sp in ns_info.get("skipped_peptides", []):
                meta = None
                rows.append(
                    {
                        "protein": "mutant", "pos": 0, "peptide": sp["peptide"],
                        "ref_peptide": None, "mutation": "", "mut_sites": [],
                        "mhc": alleles[0] if alleles else "",
                        "rank_el": None, "score_el": None, "aff_nm": None,
                        "bind_pan": None, "thalf": None, "rank_stab": None,
                        "combined_rank": None,
                        "nonstandard": True, "skipped": True,
                        "skipped_reason": f"非标准残基 {', '.join(sp['chars'])}",
                    }
                )
        rows.sort(key=lambda d: d["rank_el"] if d["rank_el"] is not None else 999)
        progress.update("完成", 1.0, f"{len(rows)} 行")
        mut_summary = []
        for pair in pairs:
            for m in pair["mutations"]:
                mut_summary.append(
                    {"protein": pair["name"] or "", "pos": m["pos"], "ref": m["ref"], "alt": m["alt"]}
                )
        result = {
            "rows": rows,
            "count": len(rows),
            "mutations": mut_summary,
            "candidate_peptides": len(peptides),
            "notes": pair_notes,
        }
        result.update(ns_info)
        return result

    return _submit("mutant", p, task, count=len(peptides), unit="条候选肽")


def _subs(ref: str, alt: str):
    return [(i + 1, a, b) for i, (a, b) in enumerate(zip(ref, alt)) if a != b]


# ---------------------------------------------------------------- 任务查询


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str) -> Response:
    job = store.get(job_id)
    if not job:
        return api_error("任务不存在", 404)
    return jsonify({"ok": True, "job": job.to_dict()})


@app.post("/api/jobs/<job_id>/cancel")
def cancel_job(job_id: str) -> Response:
    job = store.get(job_id)
    if not job:
        return api_error("任务不存在", 404)
    ok = store.cancel(job_id)
    return jsonify({"ok": True, "cancelled": ok})


@app.delete("/api/jobs/<job_id>")
def delete_job(job_id: str) -> Response:
    ok = store.delete(job_id)
    return jsonify({"ok": ok})


@app.post("/api/history/clear")
def clear_history() -> Response:
    n = store.clear_all()
    return jsonify({"ok": True, "deleted": n})


@app.get("/api/history")
def history() -> Response:
    limit = min(int(request.args.get("limit", 50)), 500)
    offset = max(int(request.args.get("offset", 0)), 0)
    kind = request.args.get("kind") or None
    jobs = store.list(limit=limit, kind=kind, offset=offset)
    return jsonify(
        {
            "ok": True,
            "total": store.count(kind),
            "jobs": [j.to_dict(include_result=False) for j in jobs],
        }
    )


# ---------------------------------------------------------------- 导出


@app.get("/api/jobs/<job_id>/export")
def export_job(job_id: str) -> Response:
    fmt = (request.args.get("format") or "csv").lower()
    if fmt not in ("csv", "xlsx"):
        return api_error("format 只支持 csv 或 xlsx")
    job = store.get(job_id)
    if not job:
        return api_error("任务不存在", 404)
    if job.status != STATUS_DONE or not job.result:
        return api_error("任务尚未成功完成，无法导出", 409)

    rows = job.result.get("rows") or []
    if not rows:
        return api_error("该任务没有结果行", 409)

    kind = {"mutant": "pipeline"}.get(job.kind, job.kind)
    meta = {
        "title": job.title,
        "lines": [
            ("任务 ID", job.id),
            ("类型", job.kind),
            ("完成时间", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job.finished_at or time.time()))),
            ("耗时", f"{job.seconds:.1f} 秒" if job.seconds else "-"),
            ("结果行数", len(rows)),
        ],
    }
    data, filename, mime = exporters.export_rows(rows, kind, fmt, meta=meta)

    # 同时落盘一份，便于离线取用
    try:
        (EXPORT_DIR / filename).write_bytes(data)
    except OSError:
        pass

    return send_file(
        io.BytesIO(data),
        mimetype=mime,
        as_attachment=True,
        download_name=filename,
    )


@app.get("/api/jobs/<job_id>/raw")
def raw_output(job_id: str) -> Response:
    """查看原始输出（调试用）。"""
    job = store.get(job_id)
    if not job:
        return api_error("任务不存在", 404)
    return jsonify({"ok": True, "job_id": job.id, "kind": job.kind,
                    "status": job.status, "error": job.error,
                    "result_keys": list((job.result or {}).keys())})


# ---------------------------------------------------------------- 智能助手（Agent）


def _agent_stream(events, session_id: str, user_text: str):
    """SSE 事件流：把 agent.run_agent_turn 的生成器事件转成 text/event-stream。"""
    from flask import Response as FlaskResp

    def gen():
        for ev in events:
            data = json.dumps({"session_id": session_id, "user": user_text, **ev}, ensure_ascii=False)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return FlaskResp(gen(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


@app.post("/api/agent/chat")
def agent_chat() -> Response:
    from . import agent
    p = body()
    sid = (p.get("session_id") or "").strip()
    text = (p.get("message") or "").strip()
    if not text:
        return api_error("消息不能为空")
    if not sid:
        sid = agent.new_session()["id"]
    return _agent_stream(agent.run_agent_turn(sid, text), sid, text)


@app.post("/api/agent/sessions")
def agent_new_session():
    from . import agent
    return jsonify({"ok": True, "session": agent.new_session()})


@app.get("/api/agent/sessions")
def agent_sessions():
    from . import agent
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"ok": True, "sessions": agent.list_sessions(limit)})


@app.get("/api/agent/sessions/<session_id>/messages")
def agent_messages(session_id: str):
    from . import agent
    return jsonify({"ok": True, "messages": agent.get_history(session_id)})


@app.delete("/api/agent/sessions/<session_id>")
def agent_delete_session(session_id: str):
    from . import agent
    ok = agent.delete_session(session_id)
    return jsonify({"ok": ok})


@app.post("/api/agent/config")
def agent_save_config():
    from . import agent
    new_cfg = body()
    allowed = {"base_url", "api_key", "model", "preset"}
    cur = {k: v for k, v in agent._load_agent_config().items() if k in allowed}
    for k in allowed:
        if k in new_cfg:
            val = (new_cfg.get(k) or "").strip()
            if k == "preset":
                val = new_cfg.get(k) or ""  # 允许空串
            if val or k == "preset":
                cur[k] = val
    # 选了预设且没手动填 base_url/model → 自动从预设填充
    preset_key = cur.get("preset") or ""
    preset = agent.MODEL_PRESETS.get(preset_key) if preset_key else None
    if preset:
        if not cur.get("base_url"):
            cur["base_url"] = preset["base_url"]
        if not cur.get("model"):
            cur["model"] = preset["model"]
    agent.save_agent_config({k: cur[k] for k in allowed if k in cur})
    return jsonify({"ok": True, "config": agent.get_agent_config_public()})


@app.post("/api/agent/test")
def agent_test_connection():
    """连通性自测：POST {base_url?, api_key?, model?}；留空的字段用已保存配置补齐。"""
    from . import agent
    payload = body()
    saved = agent._load_agent_config()
    cfg = {
        "base_url": (payload.get("base_url") or saved.get("base_url") or "").strip(),
        "api_key": (payload.get("api_key") or saved.get("api_key") or "").strip(),
        "model": (payload.get("model") or saved.get("model") or "").strip(),
    }
    if not cfg["base_url"] or not cfg["model"]:
        return jsonify({"ok": False, "status": None, "message": "配置不完整",
                        "suggestion": "请先填写 base_url 与 model（或先保存过配置）后再测试。", "key_len": len(cfg["api_key"])})
    return jsonify(agent.test_llm_connection(cfg))


@app.get("/api/agent/presets")
def agent_get_presets():
    from . import agent
    return jsonify({"ok": True, "presets": agent.get_model_presets()})


@app.get("/api/agent/config")
def agent_get_config():
    from . import agent
    return jsonify({"ok": True, "config": agent.get_agent_config_public()})

# ---------------------------------------------------------------- 静态页


@app.get("/")
def index() -> Response:
    return app.send_static_file("index.html")


@app.errorhandler(413)
def too_large(_exc) -> tuple[Response, int]:
    return api_error("提交的数据过大（上限 32 MB）", 413)


@app.errorhandler(500)
def server_error(exc) -> tuple[Response, int]:
    app.logger.exception("internal error")
    return api_error(f"服务器内部错误：{exc}", 500)


def main() -> None:
    port = int(os.environ.get("MHC_PORT", "8008"))
    host = os.environ.get("MHC_HOST", "127.0.0.1")
    app.run(host=host, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
