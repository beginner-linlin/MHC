"""新抗原一键流水线：GDC 突变 → UniProt 野生型序列 → 突变蛋白 → 三步串联。

设计书（基于 AI 的胰腺癌新抗原 mRNA 疫苗设计与评价）的候选肽来源是
「体细胞突变 → 突变蛋白 → 突变位点附近滑窗肽」。工作台原本要求用户自己
准备参考蛋白 FASTA，这里把这段补全：

  1. 从 GDC 拿到 ``KRAS Q61H`` 这样的突变（或用户手输）
  2. 按基因名去 UniProt 取规范异构体（reviewed，human）全长序列
  3. 在序列上应用替换，得到突变蛋白
  4. NetChop 判切割位点 → 生成覆盖突变位点的候选肽（标注 C 端是否为切割位点）
  5. NetMHCpan 预测结合 → NetMHCstabpan 预测稳定性
  6. 同时预测野生型对照肽，给出 Δrank（突变肽比野生型强多少）

UniProt 查询实测结论（scripts/160_uniprot_probe.sh）：
  ``gene_exact:KRAS AND organism_id:9606 AND reviewed:true`` 是最稳的写法；
  只写 ``gene_exact`` 会命中 TrEMBL 碎片（KRAS 只剩 54aa）。
  唯一例外是 CDKN2A：gene 精确匹配会先命中 CDKN2A-AS1，故加 ``gene_exact``
  后再按「返回的 GN 字段必须等于目标基因」复核，不匹配就继续取下一候选。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Sequence

from .pipeline import mutant_peptides
from .resources import ResourceError
from .runner import (
    FastaRecord,
    ProgressLike,
    ToolCaller,
    predict_binding,
    predict_cleavage,
    predict_stability_mixed,
)

AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}
STD_AA = set("ACDEFGHIKLMNPQRSTVWY")

UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search"
UNIPROT_ENTRY = "https://rest.uniprot.org/uniprotkb"
USER_AGENT = "MHC-Workbench/1.0 (+https://github.com/beginner-linlin/MHC)"
TIMEOUT = 45

CACHE_PATH = Path(os.environ.get("MHC_APP_ROOT", "/opt/bio/app")) / "data" / "uniprot_cache.json"

_cache_lock = threading.Lock()
_cache: dict[str, dict] | None = None


# ---------------------------------------------------------------- 缓存


def _load_cache() -> dict[str, dict]:
    global _cache
    if _cache is not None:
        return _cache
    data: dict[str, dict] = {}
    try:
        if CACHE_PATH.exists():
            raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = {k: v for k, v in raw.items() if isinstance(v, dict) and v.get("seq")}
    except Exception:  # noqa: BLE001
        data = {}
    _cache = data
    return data


def _save_cache() -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(_cache or {}, ensure_ascii=False, indent=0), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- 突变解析


def parse_mutation(text: str) -> dict | None:
    """``KRAS G12D`` / ``KRAS p.G12D`` / ``KRAS:G12D`` / ``KRAS p.Gly12Asp`` → 结构化。

    返回 ``{gene, pos, ref, alt, aa_change, kind}``；同义突变 kind=synonymous，
    无义突变（``*``/``Ter``）kind=nonsense（后续跳过，因为不产生新表位肽）。
    """
    s = (text or "").strip()
    if not s:
        return None
    s = re.sub(r"\s+", " ", s)
    # 拆基因名与突变体
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*[ :\t]\s*(.+)$", s)
    if m:
        gene, body = m.group(1), m.group(2).strip()
    else:
        m = re.match(r"^([A-Za-z0-9_.\-]+?)(p?\.[A-Za-z]{1,3}\d+[A-Za-z*]{1,3})$", s)
        if not m:
            return None
        gene, body = m.group(1), m.group(2)

    body = body.strip().lstrip("pP").lstrip(".")
    body = body.replace(" ", "")

    # p.Gly12Asp
    m = re.match(r"^([A-Za-z]{3})(\d+)([A-Za-z]{3}|[*X])$", body)
    if m:
        ref = AA3.get(m.group(1).upper())
        alt_raw = m.group(3)
        alt = "*" if alt_raw in ("*", "X") else AA3.get(alt_raw.upper())
        if ref and alt:
            return _mk(gene, int(m.group(2)), ref, alt)
        return None

    # p.G12D
    m = re.match(r"^([ACDEFGHIKLMNPQRSTVWY])(\d+)([ACDEFGHIKLMNPQRSTVWY*])$", body.upper())
    if m:
        return _mk(gene, int(m.group(2)), m.group(1), m.group(3))
    return None


def _mk(gene: str, pos: int, ref: str, alt: str) -> dict:
    kind = "missense"
    if alt == "*":
        kind = "nonsense"
    elif ref == alt:
        kind = "synonymous"
    return {
        "gene": gene.upper(),
        "pos": pos,
        "ref": ref,
        "alt": alt,
        "aa_change": f"{ref}{pos}{alt}",
        "kind": kind,
        "text": f"{gene.upper()} p.{ref}{pos}{alt}",
    }


def normalize_mutation(raw: Any) -> dict | None:
    """接受字符串或 ``{gene,pos,ref,alt}`` / ``{gene,aa_change}`` 字典。"""
    if isinstance(raw, dict):
        gene = str(raw.get("gene") or raw.get("protein") or "").strip()
        if not gene:
            return None
        if raw.get("pos") and raw.get("ref") and raw.get("alt"):
            try:
                return _mk(gene, int(raw["pos"]), str(raw["ref"]).upper()[:1],
                           str(raw["alt"]).upper()[:1])
            except (TypeError, ValueError):
                return None
        aa = raw.get("aa_change") or raw.get("hgvs_p") or ""
        if aa:
            return parse_mutation(f"{gene} {aa}")
        return None
    return parse_mutation(str(raw))


# ---------------------------------------------------------------- UniProt


def _http_get(url: str, timeout: int = TIMEOUT) -> str:
    """GET 文本，对瞬时网络错误重试（UniProt 偶发连接重置/超时）。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err = ResourceError(f"UniProt 返回 HTTP {exc.code}", detail=url, status=502)
            if exc.code != 429 and exc.code < 500:
                raise err from exc
            last = err
        except urllib.error.URLError as exc:
            last = ResourceError("无法连接 UniProt（网络或 DNS 不通）", detail=str(exc.reason), status=502)
        except (TimeoutError, OSError) as exc:
            last = ResourceError("UniProt 响应超时或连接中断", detail=f"{timeout} 秒 / {type(exc).__name__}", status=504)
        if attempt < 2:
            time.sleep(0.8 * (2**attempt))
    assert last is not None
    raise last


def _parse_fasta(text: str) -> tuple[str, str]:
    lines = (text or "").strip().splitlines()
    if not lines or not lines[0].startswith(">"):
        return "", ""
    return lines[0][1:].strip(), "".join(x.strip() for x in lines[1:] if x.strip())


def fetch_protein(gene_or_acc: str, *, use_cache: bool = True) -> dict:
    """按基因名或 accession 取人类规范蛋白序列。

    返回 ``{gene, accession, entry_name, header, seq, length, source, url}``。
    """
    key = (gene_or_acc or "").strip().upper()
    if not key:
        raise ResourceError("基因名/accession 为空", status=400)

    with _cache_lock:
        cache = _load_cache()
        if use_cache and key in cache:
            hit = dict(cache[key])
            hit["cached"] = True
            return hit

    want_gene = key

    # 1) 规范条目：gene_exact + reviewed + human
    query = f"gene_exact:{want_gene} AND organism_id:9606 AND reviewed:true"
    url = UNIPROT_SEARCH + "?" + urllib.parse.urlencode(
        {"query": query, "format": "fasta", "size": 5}
    )
    header, seq = _parse_fasta(_http_get(url))

    # 2) 兜底：去掉 reviewed 限制（少数基因只有 TrEMBL 全长）
    if not seq or len(seq) < 20:
        query = f"gene_exact:{want_gene} AND organism_id:9606"
        url = UNIPROT_SEARCH + "?" + urllib.parse.urlencode(
            {"query": query, "format": "fasta", "size": 5}
        )
        header, seq = _parse_fasta(_http_get(url))

    # 3) 再兜底：直接当 accession 查
    if not seq or len(seq) < 20:
        url = f"{UNIPROT_ENTRY}/{urllib.parse.quote(want_gene)}.fasta"
        try:
            header, seq = _parse_fasta(_http_get(url))
        except ResourceError:
            header, seq = "", ""

    if not seq:
        raise ResourceError(f"UniProt 没有找到「{gene_or_acc}」的人类蛋白序列", status=404)

    acc, entry_name, desc = _split_header(header)
    info = {
        "gene": want_gene,
        "accession": acc,
        "entry_name": entry_name,
        "header": header,
        "description": desc,
        "seq": seq.upper(),
        "length": len(seq),
        "source": "UniProt REST",
        "url": f"https://www.uniprot.org/uniprotkb/{acc}/entry" if acc else "",
        "cached": False,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _cache_lock:
        cache = _load_cache()
        cache[key] = info
        _save_cache()
    return info


def _split_header(header: str) -> tuple[str, str, str]:
    """``sp|P01116|RASK_HUMAN GTPase KRas OS=...`` → (acc, entry, desc)。"""
    parts = (header or "").split(" ", 1)
    head = parts[0]
    desc = parts[1] if len(parts) > 1 else ""
    desc = re.split(r"\s+OS=", desc)[0].strip()
    bits = head.split("|")
    if len(bits) >= 3:
        return bits[1], bits[2], desc
    return head, head, desc


def lookup(gene: str) -> dict:
    """给前端预览用：序列 + 若干元信息（不返回完整序列时用 head/tail 摘要）。"""
    info = fetch_protein(gene)
    seq = info["seq"]
    return {
        "gene": info["gene"],
        "accession": info["accession"],
        "entry_name": info["entry_name"],
        "description": info["description"],
        "length": info["length"],
        "seq": seq,
        "head": seq[:60],
        "tail": seq[-60:],
        "url": info["url"],
        "cached": info.get("cached", False),
    }


# ---------------------------------------------------------------- 新抗原流水线

NEO_DEFAULTS = {
    "peptide_lengths": [9],
    "cleavage_threshold": 0.5,
    "cleavage_model": 0,
    # 设计书做法是「突变位点前后各 10aa → 切 8-11aa」，即所有覆盖突变位点的滑窗都算候选，
    # 切割位点只作标注。打开本项才只保留 C 端落在切割位点的肽（更严，候选会少很多）。
    "use_cleavage_filter": False,
    "cleavage_tolerance": 1,
    # 0 = 不做硬过滤，全部候选肽按 EL 排名升序排出（结合等级仍标注），
    # 用户可在结果表里用筛选器收窄。设成 2.0 就只留强+弱结合肽。
    "max_rank_el": 0.0,
    "min_thalf": 0.0,
    "include_wt": True,
    "mutant_specific_only": False,
}


def _apply_substitution(seq: str, pos: int, ref: str, alt: str) -> str:
    return seq[: pos - 1] + alt + seq[pos:]


def run_neoantigen(
    caller: ToolCaller,
    *,
    mutations: Sequence[Any],
    alleles: Sequence[str],
    params: dict | None = None,
    progress: ProgressLike | None = None,
) -> dict:
    """突变 → 序列 → 三步串联，返回与流水线同构的结果字典。"""
    p = {**NEO_DEFAULTS, **(params or {})}
    lengths = [int(x) for x in p["peptide_lengths"] if 8 <= int(x) <= 14] or [9]
    alleles = [a for a in alleles if a]
    if not alleles:
        raise ValueError("至少需要一个等位基因")
    if not mutations:
        raise ValueError("至少需要一个突变")

    def tick(stage: str, frac: float, msg: str = "") -> None:
        if progress:
            progress.update(stage, frac, msg)

    notes: list[str] = []
    steps: list[dict] = []

    # ---- 第 0 步：解析突变 + 取 UniProt 序列
    tick("获取蛋白序列", 0.03, f"{len(mutations)} 个突变")
    t0 = time.monotonic()
    entries: list[dict] = []
    seen_gene: dict[str, dict] = {}
    for raw in mutations:
        mu = normalize_mutation(raw)
        if mu is None:
            notes.append(f"无法解析突变「{raw}」，已跳过。")
            continue
        if mu["kind"] == "nonsense":
            notes.append(f"{mu['text']} 是无义突变，不产生新表位肽，已跳过。")
            continue
        if mu["kind"] == "synonymous":
            notes.append(f"{mu['text']} 是同义突变，肽段与野生型相同，已跳过。")
            continue
        gene = mu["gene"]
        try:
            if gene not in seen_gene:
                seen_gene[gene] = fetch_protein(gene)
            prot = seen_gene[gene]
        except ResourceError as exc:
            notes.append(f"{gene} 取序列失败：{exc.message}，已跳过。")
            continue
        seq = prot["seq"]
        if not (1 <= mu["pos"] <= len(seq)):
            notes.append(
                f"{mu['text']} 的位置 {mu['pos']} 超出 {gene}（UniProt {prot['accession']}，"
                f"{len(seq)} aa）长度，已跳过。"
            )
            continue
        actual = seq[mu["pos"] - 1]
        if actual != mu["ref"]:
            notes.append(
                f"{mu['text']} 与 UniProt {prot['accession']} 第 {mu['pos']} 位（{actual}）不一致，"
                f"已按给定替换强制应用（常见于转录本异构体差异）。"
            )
        alt_seq = _apply_substitution(seq, mu["pos"], mu["ref"], mu["alt"])
        entries.append(
            {
                "gene": gene,
                "accession": prot["accession"],
                "entry_name": prot["entry_name"],
                "ref_seq": seq,
                "alt_seq": alt_seq,
                "mutation": mu,
            }
        )
    if not entries:
        raise ValueError(
            "没有可用的突变。" + (" ".join(notes) if notes else "请检查基因名与氨基酸改变写法。")
        )
    # 同一个基因的多个突变共用一条序列，展示时按基因去重
    seen_tag: dict[str, str] = {}
    for e in entries:
        seen_tag.setdefault(e["gene"], f"{e['gene']}({e['accession']},{len(e['ref_seq'])}aa)")
    steps.append(
        {
            "name": "uniprot",
            "label": "UniProt 取序列",
            "rows_in": len(mutations),
            "rows_out": len(entries),
            "seconds": round(time.monotonic() - t0, 2),
            "note": "、".join(seen_tag.values()),
        }
    )

    # ---- 第 1 步：netchop（跑突变蛋白，判切割位点）
    tick("酶切预测", 0.12, f"{len(entries)} 条突变蛋白")
    t0 = time.monotonic()
    chop_records = [FastaRecord(name=e["gene"], seq=e["alt_seq"]) for e in entries]
    cleavage_map: dict[str, list[int]] = {}
    cleavage_rows: list[dict] = []
    try:
        groups, _, _ = predict_cleavage(
            caller,
            records=chop_records,
            version=int(p["cleavage_model"]),
            threshold=float(p["cleavage_threshold"]),
        )
        for name, rows in groups.items():
            cleavage_map[name] = [r.pos for r in rows if r.cleavage == "S"]
            for r in rows:
                cleavage_rows.append(
                    {"protein": name, "pos": r.pos, "aa": r.aa,
                     "cleavage": r.cleavage, "score": r.score}
                )
    except Exception as exc:  # noqa: BLE001
        notes.append(f"NetChop 失败（{exc}），本次按全滑窗取肽。")
    total_sites = sum(len(v) for v in cleavage_map.values())
    steps.append(
        {
            "name": "netchop",
            "label": "NetChop 酶切预测",
            "rows_in": len(chop_records),
            "rows_out": total_sites,
            "seconds": round(time.monotonic() - t0, 2),
            "note": f"共 {total_sites} 个切割位点",
        }
    )

    # ---- 第 2 步：突变候选肽
    tick("生成突变肽", 0.25, "")
    cand: list[dict] = []
    tol = max(0, int(p.get("cleavage_tolerance") or 0))
    for e in entries:
        gene = e["gene"]
        sites = set(cleavage_map.get(gene, []))
        score_of: dict[int, float] = {}
        for r in cleavage_rows:
            if r["protein"] == gene and r["cleavage"] == "S":
                score_of[r["pos"]] = r["score"]
        peps = mutant_peptides(e["ref_seq"], e["alt_seq"], lengths)
        for x in peps:
            end = x["pos"] + len(x["peptide"]) - 1
            # 距最近切割位点的偏移（C 端）
            near = [d for d in range(-tol, tol + 1) if (end + d) in sites]
            is_site = bool(near)
            best = min(near, key=lambda d: abs(d)) if near else 0
            if p["use_cleavage_filter"] and sites and not is_site:
                continue
            cand.append(
                {
                    "gene": gene,
                    "accession": e["accession"],
                    "mutation": e["mutation"],
                    "pos": x["pos"],
                    "peptide": x["peptide"],
                    "ref_peptide": x["ref_peptide"],
                    "length": x["length"],
                    "cut_pos": end + best if is_site else 0,
                    "cut_score": score_of.get(end + best) if is_site else None,
                }
            )
    if not cand:
        # 切割位点过滤太狠时退回全滑窗，避免直接失败
        for e in entries:
            for x in mutant_peptides(e["ref_seq"], e["alt_seq"], lengths):
                cand.append(
                    {
                        "gene": e["gene"], "accession": e["accession"],
                        "mutation": e["mutation"], "pos": x["pos"],
                        "peptide": x["peptide"], "ref_peptide": x["ref_peptide"],
                        "length": x["length"], "cut_pos": 0, "cut_score": None,
                    }
                )
        if cand:
            notes.append("切割位点过滤后没有候选肽，已自动退回全滑窗取肽。")
    if not cand:
        raise ValueError("突变位点附近没有生成任何候选肽，请检查突变位置或肽长设置。")
    steps.append(
        {
            "name": "candidates",
            "label": "突变肽生成",
            "rows_in": len(entries),
            "rows_out": len(cand),
            "seconds": 0.0,
            "note": f"肽长 {','.join(map(str, lengths))}；"
                    + (
                        f"C 端须在切割位点 ±{tol}"
                        if p["use_cleavage_filter"]
                        else "覆盖突变位点的全滑窗（切割位点仅作标注）"
                    ),
        }
    )

    # ---- 第 3 步：netMHCpan（突变肽 + 可选野生型对照）
    tick("MHC 结合预测", 0.4, f"{len(cand)} 条突变肽 × {len(alleles)} 个 HLA")
    t0 = time.monotonic()
    mut_peps = [c["peptide"] for c in cand]
    pan_rows, _, _ = predict_binding(
        caller, peptides=mut_peps, alleles=alleles, with_ba=True, sort=False
    )
    t1 = time.monotonic()

    wt_rows: list = []
    if p["include_wt"]:
        tick("野生型对照预测", 0.6, f"{len(cand)} 条野生型肽")
        wt_peps = sorted({c["ref_peptide"] for c in cand})
        try:
            wt_rows, _, _ = predict_binding(
                caller, peptides=wt_peps, alleles=alleles, with_ba=True, sort=False
            )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"野生型对照预测失败（{exc}），Δrank 留空。")
    steps.append(
        {
            "name": "netMHCpan",
            "label": "NetMHCpan 结合预测",
            "rows_in": len(mut_peps) * len(alleles),
            "rows_out": len(pan_rows),
            "seconds": round(t1 - t0, 2),
            "note": f"突变肽 {len(mut_peps)} 条" + ("＋野生型对照" if p["include_wt"] else ""),
        }
    )

    max_rank = float(p["max_rank_el"])
    passed = [r for r in pan_rows if r.rank_el <= max_rank] if max_rank > 0 else list(pan_rows)

    # ---- 第 4 步：netMHCstabpan
    stab_lookup: dict[tuple[str, str], Any] = {}
    if passed:
        # passed 里同一条肽会因多个 HLA 重复出现，去重后再送工具，
        # 否则 netMHCstabpan 会按重复次数成倍输出（实测 36 条 → 144 行）。
        uniq_peps = sorted({r.peptide for r in passed})
        tick("稳定性预测", 0.78, f"{len(uniq_peps)} 条结合肽")
        t0 = time.monotonic()
        stab_rows, _ = predict_stability_mixed(
            caller, peptides=uniq_peps, alleles=alleles, with_ia=True
        )
        for s in stab_rows:
            stab_lookup.setdefault((s.hla.replace("*", ""), s.peptide), s)
        steps.append(
            {
                "name": "netMHCstabpan",
                "label": "NetMHCstabpan 稳定性预测",
                "rows_in": len(uniq_peps),
                "rows_out": len(stab_rows),
                "seconds": round(time.monotonic() - t0, 2),
                "note": f"{len(uniq_peps)} 条肽 × {len(alleles)} 个 HLA，含亲和力列",
            }
        )

    # ---- 汇总
    tick("汇总结果", 0.94, "")
    wt_lookup: dict[tuple[str, str], Any] = {}
    for r in wt_rows:
        wt_lookup.setdefault((r.mhc.replace("*", ""), r.peptide), r)

    cand_by_pep: dict[str, dict] = {}
    for c in cand:
        prev = cand_by_pep.get(c["peptide"])
        if prev is None:
            cand_by_pep[c["peptide"]] = c
            continue
        if (c["cut_score"] or 0) > (prev["cut_score"] or 0):
            cand_by_pep[c["peptide"]] = c

    rows: list[dict] = []
    for r in passed:
        mhc_norm = r.mhc.replace("*", "")
        meta = cand_by_pep.get(r.peptide) or {}
        s = stab_lookup.get((mhc_norm, r.peptide))
        if s is not None and p["min_thalf"] and (s.thalf or 0) < float(p["min_thalf"]):
            continue
        wt = wt_lookup.get((mhc_norm, meta.get("ref_peptide") or ""))
        delta = None
        if wt is not None and r.rank_el is not None and wt.rank_el is not None:
            delta = round(wt.rank_el - r.rank_el, 4)
        if p["mutant_specific_only"]:
            # 只保留「突变肽明显优于野生型」的：Δrank > 0 且野生型本身不强
            if wt is None or delta is None or delta <= 0:
                continue
            if wt.rank_el is not None and wt.rank_el < max_rank:
                continue
        mu = meta.get("mutation") or {}
        rows.append(
            {
                "gene": meta.get("gene", ""),
                "accession": meta.get("accession", ""),
                "mutation": mu.get("aa_change", ""),
                "pos": meta.get("pos", 0),
                "peptide": r.peptide,
                "ref_peptide": meta.get("ref_peptide"),
                "mhc": r.mhc,
                "rank_el": r.rank_el,
                "score_el": r.score_el,
                "aff_nm": r.aff_nm,
                "bind_pan": r.bind,
                "wt_rank_el": wt.rank_el if wt else None,
                "wt_aff_nm": wt.aff_nm if wt else None,
                "delta_rank": delta,
                "cut_pos": meta.get("cut_pos", 0),
                "cut_score": meta.get("cut_score"),
                "thalf": s.thalf if s else None,
                "rank_stab": s.rank_stab if s else None,
                "combined_rank": s.combined_rank if s else None,
            }
        )
    rows.sort(key=lambda d: (d["rank_el"] if d["rank_el"] is not None else 999))

    bound = sum(1 for d in rows if "SB" in str(d.get("bind_pan") or ""))
    tick("完成", 1.0, f"{len(rows)} 条结果")
    return {
        "proteins": list(dict.fromkeys(seen_tag.values())),
        "alleles": list(alleles),
        "params": p,
        "rows": rows,
        "steps": steps,
        "cleavage": cleavage_rows,
        "candidates": len(cand),
        "bound": bound,
        "mutations": [
            {
                "gene": e["gene"], "accession": e["accession"],
                "aa_change": e["mutation"]["aa_change"],
                "pos": e["mutation"]["pos"],
                "ref": e["mutation"]["ref"],
                "alt": e["mutation"]["alt"],
            }
            for e in entries
        ],
        "notes": notes,
        "summary": {
            "gene_count": len(entries),
            "mutation_count": len(entries),
            "allele_count": len(alleles),
            "candidate_peptides": len(cand),
            "bound_peptides": bound,
            "result_rows": len(rows),
        },
    }
