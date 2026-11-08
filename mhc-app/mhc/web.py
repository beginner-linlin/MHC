"""Flask 后端：把三个工具包装成 JSON API。

端点分区：
  /api/health            健康检查与工具版本
  /api/alleles           HLA 等位基因清单
  /api/validate/input    输入预检（长度、非标准残基、重复）
  /api/jobs/*            提交/查询/取消任务，导出结果
  /api/history           历史记录
"""

from __future__ import annotations

import io
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file

from . import __version__, exporters
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


# ---------------------------------------------------------------- 输入预检


def _collect_inputs(payload: dict) -> tuple[list[str], list[FastaRecord], str]:
    """从请求中抽取 (肽列表, FASTA 记录, 输入类型)。"""
    raw = payload.get("input") or ""
    mode = payload.get("input_mode") or "auto"

    if mode == "fasta" or (mode == "auto" and looks_like_fasta(raw)):
        return [], parse_fasta(raw), "fasta"
    peptides = parse_peptide_list(raw)
    return peptides, [], "peptide"


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
        warnings.append(
            {
                "level": "error",
                "code": "nonstandard_aa",
                "message": f"发现非标准氨基酸：{', '.join(sorted(bad))}。"
                "工具会把这些字符静默当作 X 处理，预测结果不可靠。",
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
        progress.update("完成", 1.0, f"{len(rows)} 行")
        return {"rows": [r.to_dict() for r in rows], "count": len(rows)}

    return _submit("pan", p, task)


@app.post("/api/jobs/chop")
def submit_chop() -> Response:
    p = body()
    _, records, _ = _collect_inputs(p)
    if not records:
        return api_error("酶切预测需要 FASTA 格式的蛋白序列（以 > 开头）")

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
            summary.append({"protein": name, "length": len(rr), "sites": sites})
            for x in rr:
                rows.append(
                    {"protein": name, "pos": x.pos, "aa": x.aa,
                     "cleavage": x.cleavage, "score": x.score}
                )
        progress.update("完成", 1.0, f"{len(rows)} 行")
        return {"rows": rows, "count": len(rows), "summary": summary,
                "model": int(p.get("model", 0)), "threshold": float(p.get("threshold", 0.5))}

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
        progress.update("完成", 1.0, f"{len(rows)} 行")
        return {"rows": [r.to_dict() for r in rows], "count": len(rows),
                "with_ia": with_ia}

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
        return result.to_dict()

    return _submit("pipeline", p, task)


@app.post("/api/jobs/mutant")
def submit_mutant() -> Response:
    p = body()
    alleles = resolve_alleles(p.get("alleles") or [])
    if not alleles:
        return api_error("请至少选择一个 HLA 等位基因")
    ref = (p.get("ref_seq") or "").strip().upper()
    alt = (p.get("alt_seq") or "").strip().upper()
    if not ref or not alt:
        return api_error("需要提供参考序列与突变序列")
    if len(ref) != len(alt):
        return api_error(f"两条序列长度必须一致（参考 {len(ref)}，突变 {len(alt)}）")
    lengths = [int(x) for x in (p.get("peptide_lengths") or [9])]

    # 同步预生成候选肽：既用于标题里的数量，也用于「完全相同」的即时报错
    peptides = mutant_peptides(ref, alt, lengths)
    if not peptides:
        return api_error("两条序列完全相同，未找到突变位点")

    def task(progress: Progress) -> dict:
        c = caller()
        progress.update("生成突变肽", 0.1, "")
        peps = [x["peptide"] for x in peptides]
        progress.update("结合预测", 0.3, f"{len(peps)} 条突变肽")
        pan_rows, _, _ = predict_binding(c, peptides=peps, alleles=alleles, with_ba=True)
        progress.update("稳定性预测", 0.7, "")
        stab_rows, _ = predict_stability_mixed(c, peptides=peps, alleles=alleles, with_ia=True)

        stab_lookup = {(s.hla.replace("*", ""), s.peptide): s for s in stab_rows}
        info = {x["peptide"]: x for x in peptides}
        rows = []
        for r in pan_rows:
            s = stab_lookup.get((r.mhc.replace("*", ""), r.peptide))
            meta = info.get(r.peptide, {})
            rows.append(
                {
                    "protein": "mutant",
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
                }
            )
        rows.sort(key=lambda d: d["rank_el"] if d["rank_el"] is not None else 999)
        progress.update("完成", 1.0, f"{len(rows)} 行")
        return {
            "rows": rows,
            "count": len(rows),
            "mutations": [{"pos": p_, "ref": a, "alt": b} for p_, a, b in _subs(ref, alt)],
            "candidate_peptides": len(peptides),
        }

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
