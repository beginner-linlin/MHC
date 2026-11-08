"""三步串联流水线与新抗原突变肽生成。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .runner import (
    ChopRow,
    FastaRecord,
    PanRow,
    ProgressLike,
    StabRow,
    ToolCaller,
    predict_binding,
    predict_cleavage,
    predict_stability_mixed,
)

IUPAC_DNA = set("ACGTN")


# ---------------------------------------------------------------- 候选肽生成


def windows_from_protein(seq: str, lengths: Sequence[int]) -> list[tuple[int, str]]:
    """全滑窗（1-based 起始位置）。"""
    out: list[tuple[int, str]] = []
    for L in lengths:
        if L <= 0 or L > len(seq):
            continue
        for i in range(0, len(seq) - L + 1):
            out.append((i + 1, seq[i : i + L]))
    return out


def windows_before_cleavage(
    seq: str,
    cleavage_positions: Sequence[int],
    lengths: Sequence[int],
    *,
    include_site: bool = True,
) -> list[tuple[int, int, str]]:
    """从每个切割位点向左取肽。

    cleavage_positions 是 netchop 报的 1-based 位置：该位置**之前**被切开，
    即蛋白在 pos-1 与 pos 之间断开。因此以 pos 为肽的第一个残基（C 端片段起点）
    或向左取（N 端片段末端）。这里取「以切割位点为起点向右」是不对的——
    我们按需求取「终点落在切割位点前的肽」，即 C 端对齐到 pos-1。
    """
    out: list[tuple[int, int, str]] = []
    for L in lengths:
        for pos in cleavage_positions:
            end = pos - 1 if not include_site else pos
            start = end - L
            if start >= 0 and end <= len(seq):
                peptide = seq[start:end]
                if len(peptide) == L:
                    out.append((pos, start + 1, peptide))
    # 去重
    seen: set[tuple[int, str]] = set()
    uniq: list[tuple[int, int, str]] = []
    for item in out:
        key = (item[1], item[2])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def find_substitutions(ref: str, alt: str) -> list[tuple[int, str, str]]:
    """逐位比较两条等长蛋白，返回 [(1-based 位置, ref_aa, alt_aa), ...]。"""
    if len(ref) != len(alt):
        raise ValueError(f"参考序列与突变序列长度不一致：{len(ref)} vs {len(alt)}")
    return [(i + 1, a, b) for i, (a, b) in enumerate(zip(ref, alt)) if a != b]


def mutant_peptides(
    ref: str,
    alt: str,
    lengths: Sequence[int],
) -> list[dict]:
    """生成覆盖突变位点的所有滑窗肽，并标注是否含突变残基。

    返回 [{"pos", "peptide", "mutated", "mut_sites"}]，按 (位置, 长度) 排序。
    """
    subs = find_substitutions(ref, alt)
    if not subs:
        return []
    sub_map = {p: (a, b) for p, a, b in subs}
    mut_positions = set(sub_map)

    seen: dict[tuple[int, str], dict] = {}
    for L in lengths:
        if L > len(ref):
            continue
        for i in range(0, len(ref) - L + 1):
            covered = mut_positions & set(range(i + 1, i + L + 1))
            if not covered:
                continue
            pep = alt[i : i + L]
            key = (i + 1, pep)
            if key in seen:
                continue
            seen[key] = {
                "pos": i + 1,
                "peptide": pep,
                "ref_peptide": ref[i : i + L],
                "mutated": True,
                "mut_sites": [
                    {"pos": q, "ref": sub_map[q][0], "alt": sub_map[q][1]}
                    for q in sorted(covered)
                ],
                "length": L,
            }
    return sorted(seen.values(), key=lambda d: (d["pos"], d["length"]))


# ---------------------------------------------------------------- 流水线


PIPE_DEFAULTS = {
    "cleavage_threshold": 0.5,
    "cleavage_model": 0,          # 0 = C-term 3.0, 1 = 20S 3.0
    "peptide_lengths": [9],
    "use_cleavage_filter": True,
    "max_rank_el": 2.0,
    "min_thalf": 0.0,
    "include_ia": True,
    "include_site": True,
}


@dataclass
class PipelineStep:
    name: str
    label: str
    rows_in: int
    rows_out: int
    seconds: float
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "seconds": round(self.seconds, 2),
            "note": self.note,
        }


@dataclass
class PipelineResult:
    proteins: list[str]
    alleles: list[str]
    params: dict
    rows: list[dict] = field(default_factory=list)
    steps: list[PipelineStep] = field(default_factory=list)
    cleavage: list[dict] = field(default_factory=list)
    candidates: int = 0
    bound: int = 0

    def to_dict(self) -> dict:
        return {
            "proteins": self.proteins,
            "alleles": self.alleles,
            "params": self.params,
            "rows": self.rows,
            "steps": [s.to_dict() for s in self.steps],
            "cleavage": self.cleavage,
            "candidates": self.candidates,
            "bound": self.bound,
            "summary": {
                "protein_count": len(self.proteins),
                "allele_count": len(self.alleles),
                "candidate_peptides": self.candidates,
                "bound_peptides": self.bound,
                "result_rows": len(self.rows),
            },
        }


def run_pipeline(
    caller: ToolCaller,
    *,
    records: Sequence[FastaRecord],
    alleles: Sequence[str],
    params: dict | None = None,
    progress: ProgressLike | None = None,
) -> PipelineResult:
    """切割 → 结合 → 稳定性 三步串联。"""
    import time

    p = {**PIPE_DEFAULTS, **(params or {})}
    lengths = [int(x) for x in p["peptide_lengths"] if 8 <= int(x) <= 14] or [9]
    alleles = [a for a in alleles if a]
    if not alleles:
        raise ValueError("至少需要一个等位基因")
    if not records:
        raise ValueError("至少需要一条蛋白序列")

    steps: list[PipelineStep] = []

    def tick(stage: str, frac: float, msg: str = "") -> None:
        if progress:
            progress.update(stage, frac, msg)

    # ---- 第 1 步：netchop
    tick("酶切预测", 0.05, f"{len(records)} 条蛋白")
    t0 = time.monotonic()
    groups, _, _ = predict_cleavage(
        caller,
        records=records,
        version=int(p["cleavage_model"]),
        threshold=float(p["cleavage_threshold"]),
    )
    t1 = time.monotonic()

    cleavage_rows: list[dict] = []
    cleavage_map: dict[str, list[int]] = {}
    for name, rows in groups.items():
        sites = [r.pos for r in rows if r.cleavage == "S"]
        cleavage_map[name] = sites
        for r in rows:
            cleavage_rows.append(
                {"protein": name, "pos": r.pos, "aa": r.aa, "cleavage": r.cleavage, "score": r.score}
            )
    total_sites = sum(len(v) for v in cleavage_map.values())
    steps.append(
        PipelineStep("netchop", "NetChop 酶切预测", len(records), total_sites, t1 - t0,
                     f"共 {total_sites} 个切割位点")
    )

    # ---- 第 2 步：生成候选肽
    tick("生成候选肽", 0.25, "")
    cand: list[dict] = []
    for rec in records:
        if p["use_cleavage_filter"]:
            sites = cleavage_map.get(rec.name, [])
            if not sites:
                continue
            for pos, start, pep in windows_before_cleavage(
                rec.seq, sites, lengths, include_site=bool(p["include_site"])
            ):
                cand.append({"protein": rec.name, "cut_pos": pos, "peptide": pep})
        else:
            # 全滑窗模式：仍标注肽的 C 端是否恰好是切割位点，便于人工判读
            site_set = set(cleavage_map.get(rec.name, []))
            for start, pep in windows_from_protein(rec.seq, lengths):
                end = start + len(pep) - 1  # 1-based 末位
                cut = end if end in site_set else 0
                cand.append({"protein": rec.name, "cut_pos": cut, "peptide": pep})

    # 去重（同一蛋白同一肽只留一条）
    seen: set[tuple[str, str]] = set()
    uniq: list[dict] = []
    for c in cand:
        key = (c["protein"], c["peptide"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    cand = uniq
    if not cand:
        raise ValueError(
            "没有生成任何候选肽。可能原因：切割阈值过高导致无切割位点，"
            "或蛋白长度小于所选肽长。请降低阈值或改用「全滑窗」模式。"
        )
    steps.append(
        PipelineStep("candidates", "候选肽生成", total_sites, len(cand), 0.0,
                     f"肽长 {','.join(map(str, lengths))}；"
                     + ("从切割位点取肽" if p["use_cleavage_filter"] else "全滑窗"))
    )

    # ---- 第 3 步：netMHCpan
    tick("MHC 结合预测", 0.45, f"{len(cand)} 条候选肽 × {len(alleles)} 个 HLA")
    t0 = time.monotonic()
    pep_list = [c["peptide"] for c in cand]
    pan_rows, _, _ = predict_binding(
        caller, peptides=pep_list, alleles=alleles, with_ba=True, sort=False
    )
    t1 = time.monotonic()

    # 只保留通过排名的
    max_rank = float(p["max_rank_el"])
    passed = [r for r in pan_rows if r.rank_el <= max_rank] if max_rank > 0 else pan_rows
    steps.append(
        PipelineStep("netMHCpan", "NetMHCpan 结合预测", len(pep_list) * len(alleles),
                     len(passed), t1 - t0,
                     f"EL 排名 ≤ {max_rank} 保留 {len(passed)}/{len(pan_rows)}")
    )

    if not passed:
        return PipelineResult(
            proteins=[r.name for r in records],
            alleles=list(alleles),
            params=p,
            rows=[],
            steps=steps,
            cleavage=cleavage_rows,
            candidates=len(cand),
            bound=0,
        )

    # ---- 第 4 步：netMHCstabpan（按肽长分组，与 pan 结果无关地跑全量候选肽）
    tick("稳定性预测", 0.7, f"{len(passed)} 条结合肽")
    t0 = time.monotonic()
    stab_rows, _ = predict_stability_mixed(
        caller, peptides=[r.peptide for r in passed], alleles=alleles, with_ia=True
    )
    t1 = time.monotonic()
    steps.append(
        PipelineStep("netMHCstabpan", "NetMHCstabpan 稳定性预测",
                     len(passed), len(stab_rows), t1 - t0,
                     f"含亲和力列：{'是' if p['include_ia'] else '否'}")
    )

    # ---- 合并
    tick("汇总结果", 0.92, "")
    # 注意：netMHCpan 的 `-p` 模式 Identity 列固定为 PEPLIST，拿不到蛋白名。
    # 所以回溯切割位点必须用「肽序列 -> 候选记录」查，而不是 (protein, peptide)。
    # 同一肽可能对应多个切割位点，取切割概率最高的那个。
    site_score: dict[tuple[str, int], float] = {}
    for r in cleavage_rows:
        if r["cleavage"] == "S":
            site_score[(r["protein"], r["pos"])] = r["score"]

    pep_to_cand: dict[str, dict] = {}
    for c in cand:
        prev = pep_to_cand.get(c["peptide"])
        if prev is None:
            pep_to_cand[c["peptide"]] = c
            continue
        new_s = site_score.get((c["protein"], c["cut_pos"]), 0.0) if c["cut_pos"] else 0.0
        old_s = site_score.get((prev["protein"], prev["cut_pos"]), 0.0) if prev["cut_pos"] else 0.0
        if new_s > old_s:
            pep_to_cand[c["peptide"]] = c

    stab_lookup: dict[tuple[str, str], StabRow] = {}
    for s in stab_rows:
        stab_lookup.setdefault((s.hla.replace("*", ""), s.peptide), s)

    rows: list[dict] = []
    for r in passed:
        mhc_norm = r.mhc.replace("*", "")
        s = stab_lookup.get((mhc_norm, r.peptide)) or stab_lookup.get(("", r.peptide))
        if s is not None and p["min_thalf"] and s.thalf < float(p["min_thalf"]):
            continue
        meta = pep_to_cand.get(r.peptide, {})
        prot = meta.get("protein") or r.identity
        cutpos = meta.get("cut_pos", 0)
        rows.append(
            {
                "protein": prot,
                "cut_pos": cutpos,
                "cut_score": site_score.get((prot, cutpos)) if cutpos else None,
                "peptide": r.peptide,
                "mhc": r.mhc,
                "rank_el": r.rank_el,
                "score_el": r.score_el,
                "aff_nm": r.aff_nm,
                "bind_pan": r.bind,
                "thalf": s.thalf if s else None,
                "rank_stab": s.rank_stab if s else None,
                "combined_rank": s.combined_rank if s else None,
                "pred_stab": s.pred if s else None,
            }
        )

    # 综合排序：先按 EL 排名
    rows.sort(key=lambda d: (d["rank_el"] if d["rank_el"] is not None else 999))

    bound = sum(1 for d in rows if "SB" in str(d.get("bind_pan", "")))
    tick("完成", 1.0, f"{len(rows)} 条结果")
    return PipelineResult(
        proteins=[r.name for r in records],
        alleles=list(alleles),
        params=p,
        rows=rows,
        steps=steps,
        cleavage=cleavage_rows,
        candidates=len(cand),
        bound=bound,
    )
