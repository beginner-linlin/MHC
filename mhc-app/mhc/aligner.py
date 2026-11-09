"""BWA-MEM 序列比对。

把参考序列建成 BWA 索引，用 `bwa mem` 把查询序列比对上去，
解析 SAM 得到每条 query 的最佳比对、CIGAR、以及逐个差异明细。

设计要点（都来自实测）：
  * bwa 默认 -k19 -T30，**短于 30bp 的 query 默认完全无法比对**（flag=4）。
    因此提供 preset：strict / short / peptide，并强制在短序列时提示不可靠。
  * 极短序列（<12bp）在随机参考上会产生大量假比对（实测 9bp×30 条在 3kb
    参考上得到 31 条命中），所以结果里必须给出唯一性与显著性提示。
  * 蛋白序列用 bwa 比对不会报错但静默 0 行 —— 输入侧必须显式拒绝非 ACGTN。
  * SAM 里 flag&16 的 query 序列是原始方向，与 MD tag 反向，
    必须 revcomp 后才能与参考逐位对齐。
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .runner import FastaRecord, ToolError

# ---------------------------------------------------------------- 常量

BWA_BIN = "bwa"
SAMTOOLS_BIN = "samtools"

IDX_ROOT = Path("/opt/bio/app/work/bwa_idx")

MAX_REF_BP = 20_000_000        # 参考总长上限（约 20 Mb）
MAX_QUERY_SEQS = 20_000        # 查询序列条数上限
MAX_QUERY_BP = 40_000_000      # 查询总碱基上限
MAX_QUERY_LEN = 200_000        # 单条查询长度上限

DNA_ALPHABET = set("ACGTN")
IUPAC = set("ACGTRYSWKMBDHVN")

CIGAR_RE = re.compile(r"(\d+)([MIDNSHP=X])")

#: 比对预设。数值来自实测：-T 决定最短可比对长度，-k 决定最短种子。
PRESETS: dict[str, dict[str, Any]] = {
    "strict": {
        "label": "标准（默认，适合 ≥30bp 的 reads/序列）",
        "k": 19, "T": 30, "W": 100,
        "note": "bwa mem 出厂参数；短于 30bp 的 query 不会被比对。",
    },
    "short": {
        "label": "短序列（20–30bp）",
        "k": 11, "T": 20, "W": 20,
        "note": "放宽种子与最低分数，20bp 起可比对；假阳性会上升。",
    },
    "peptide": {
        "label": "极短序列（8–20bp，仅供定位参考）",
        "k": 5, "T": 1, "W": 5,
        "note": "实测 8bp 也能比上，但随机序列同样会大量命中，必须结合唯一性判断。",
    },
}

DEFAULTS: dict[str, Any] = {
    "preset": "strict",
    "min_seed": None,          # None → 用 preset 的 k
    "min_score": None,         # None → 用 preset 的 T
    "band_width": None,        # None → 用 preset 的 W
    "threads": 2,
    "all_alignments": False,   # -a：输出所有比对（含 secondary）
    "max_hits": 500,           # 每查询最多保留多少条比对（-a 时有效）
    "min_mapq": 0,             # 结果过滤
    "max_mismatch": None,      # 按 NM 过滤
    "sort_by": "query",        # query | score | identity
}


# ---------------------------------------------------------------- 数据结构


@dataclass
class AlignRow:
    """一条 query 的一条比对记录。"""

    query: str
    query_len: int
    flag: int
    ref: str
    pos: int                 # 1-based
    mapq: int
    cigar: str
    nm: int | None
    score: int | None
    matches: int
    mismatches: int
    insertions: int
    deletions: int
    identity: float
    strand: str
    ref_aligned: str
    query_aligned: str
    diffs: list[dict] = field(default_factory=list)
    secondary: bool = False
    primary_of: str | None = None

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "query_len": self.query_len,
            "ref": self.ref,
            "pos": self.pos,
            "end": self.pos + len(self.ref_aligned) - 1 if self.ref_aligned else self.pos,
            "strand": self.strand,
            "mapq": self.mapq,
            "cigar": self.cigar,
            "nm": self.nm,
            "score": self.score,
            "matches": self.matches,
            "mismatches": self.mismatches,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "identity": round(self.identity, 4),
            "ref_aligned": self.ref_aligned,
            "query_aligned": self.query_aligned,
            "diff_count": len(self.diffs),
            "diffs": self.diffs,
            "secondary": self.secondary,
        }


# ---------------------------------------------------------------- 序列工具


def _revcomp(seq: str) -> str:
    table = str.maketrans("ACGTNacgtn", "TGCANtgcan")
    return seq.translate(table)[::-1]


def clean_dna(seq: str) -> str:
    """去掉空白与数字，转大写；保留 IUPAC 之外的字符由调用方校验。"""
    return re.sub(r"[\s\d\-]", "", (seq or "")).upper()


def non_dna_residues(seq: str) -> list[str]:
    return sorted({c for c in seq if c not in IUPAC})


def looks_like_protein(seq: str) -> bool:
    """蛋白序列的典型特征：出现 EFILPQ 之类在 DNA 里不存在的字母，且比例高。"""
    if not seq:
        return False
    dna = set("ACGTN")
    odd = sum(1 for c in seq if c not in dna)
    return odd / len(seq) > 0.25


def parse_cigar(cigar: str) -> list[tuple[int, str]]:
    if not cigar or cigar == "*":
        return []
    return [(int(n), op) for n, op in CIGAR_RE.findall(cigar)]


def cigar_summary(blocks: Sequence[tuple[int, str]]) -> dict[str, int]:
    out = {"match": 0, "ins": 0, "del": 0, "soft": 0, "hard": 0, "ref_span": 0}
    for n, op in blocks:
        if op in "M=X":
            out["match"] += n
            out["ref_span"] += n
        elif op == "I":
            out["ins"] += n
        elif op in "DN":
            out["del"] += n
            out["ref_span"] += n
        elif op == "S":
            out["soft"] += n
        elif op == "H":
            out["hard"] += n
    return out


def expand_alignment(
    ref_seq: str, pos1: int, cigar: str, query_seq: str
) -> tuple[str, str, int, int]:
    """按 CIGAR 展开出等长的参考片段与查询片段。

    返回 (ref_aligned, query_aligned, matches, mismatches)。
    indel 位置在两侧都填 '-'，使两串等长便于逐位比较。
    """
    blocks = parse_cigar(cigar)
    if not blocks:
        return "", "", 0, 0

    # 去掉 soft/hard clip，取核心 query
    lead_soft = 0
    for n, op in blocks:
        if op == "S":
            lead_soft += n
        elif op == "H":
            continue
        else:
            break
    core_q = query_seq[lead_soft:]

    ri = pos1 - 1
    qi = 0
    ref_out: list[str] = []
    qry_out: list[str] = []
    matches = mismatches = 0

    for n, op in blocks:
        if op in "M=X":
            rseg = ref_seq[ri:ri + n]
            qseg = core_q[qi:qi + n]
            ref_out.append(rseg)
            qry_out.append(qseg)
            for a, b in zip(rseg, qseg):
                if a == b:
                    matches += 1
                else:
                    mismatches += 1
            ri += n
            qi += n
        elif op == "I":
            qseg = core_q[qi:qi + n]
            ref_out.append("-" * n)
            qry_out.append(qseg)
            qi += n
        elif op in "DN":
            rseg = ref_seq[ri:ri + n]
            ref_out.append(rseg)
            qry_out.append("-" * n)
            ri += n
        elif op == "S":
            qi += n
        # H / P 不消耗

    return "".join(ref_out), "".join(qry_out), matches, mismatches


def diffs_from_alignment(ref_aln: str, qry_aln: str, pos1: int) -> list[dict]:
    """逐位比较展开后的两串，产出差异列表（1-based 参考坐标）。"""
    diffs: list[dict] = []
    rpos = pos1
    i = 0
    n = len(ref_aln)
    while i < n:
        r = ref_aln[i]
        q = qry_aln[i]
        if r == q:
            rpos += 1
            i += 1
            continue
        if r == "-":
            # 查询相对参考多出碱基（插入）
            j = i
            ins = []
            while j < n and ref_aln[j] == "-":
                ins.append(qry_aln[j])
                j += 1
            diffs.append({
                "kind": "ins",
                "ref_pos": rpos,
                "ref_base": "",
                "query_base": "".join(ins),
                "length": len(ins),
                "label": f"插入 {''.join(ins)}",
            })
            i = j
            continue
        if q == "-":
            j = i
            dele = []
            while j < n and qry_aln[j] == "-":
                dele.append(ref_aln[j])
                j += 1
            diffs.append({
                "kind": "del",
                "ref_pos": rpos,
                "ref_base": "".join(dele),
                "query_base": "",
                "length": len(dele),
                "label": f"缺失 {''.join(dele)}",
            })
            rpos += len(dele)
            i = j
            continue
        diffs.append({
            "kind": "sub",
            "ref_pos": rpos,
            "ref_base": r,
            "query_base": q,
            "length": 1,
            "label": f"{r}→{q}",
        })
        rpos += 1
        i += 1
    return diffs


# ---------------------------------------------------------------- 索引


def bwa_version() -> str:
    try:
        p = subprocess.run([BWA_BIN], capture_output=True, text=True, timeout=20)
        for line in (p.stderr or p.stdout or "").splitlines():
            if line.strip().startswith("Version:"):
                return "bwa " + line.split(":", 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass
    return "bwa (unknown)"


def samtools_version() -> str:
    try:
        p = subprocess.run([SAMTOOLS_BIN, "--version"], capture_output=True, text=True, timeout=20)
        first = (p.stdout or "").splitlines()
        return first[0].strip() if first else "samtools (unknown)"
    except Exception:  # noqa: BLE001
        return "samtools (unknown)"


def _ref_digest(ref_records: Sequence[FastaRecord], params: dict) -> str:
    h = hashlib.sha256()
    for r in ref_records:
        h.update(r.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(r.seq.encode("ascii", "replace"))
        h.update(b"\x01")
    # 索引与 -a 参数无关，只跟参考内容有关
    return h.hexdigest()[:20]


def ensure_index(ref_records: Sequence[FastaRecord]) -> tuple[Path, Path, dict]:
    """把参考写成 ref.fa 并建 BWA 索引，按内容哈希缓存。"""
    if not ref_records:
        raise ToolError("bwa", "参考序列为空")
    total = sum(len(r.seq) for r in ref_records)
    if total > MAX_REF_BP:
        raise ToolError("bwa", f"参考序列总长 {total:,} bp，超过上限 {MAX_REF_BP:,} bp")

    digest = _ref_digest(ref_records, {})
    idx_dir = IDX_ROOT / digest
    ref_path = idx_dir / "ref.fa"
    done_mark = idx_dir / ".ok"

    if done_mark.is_file() and ref_path.is_file():
        return idx_dir, ref_path, {"cached": True, "digest": digest, "ref_bp": total,
                                   "ref_count": len(ref_records)}

    idx_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for r in ref_records:
        lines.append(f">{r.name}")
        seq = r.seq
        for i in range(0, len(seq), 70):
            lines.append(seq[i:i + 70])
    ref_path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")

    started = time.monotonic()
    p = subprocess.run(
        [BWA_BIN, "index", "-a", "is", str(ref_path)],
        capture_output=True, text=True, timeout=1800, cwd=str(idx_dir),
    )
    if p.returncode != 0 or not (idx_dir / "ref.fa.bwt").is_file():
        raise ToolError("bwa", f"建立索引失败：{(p.stderr or p.stdout or '').strip()[:500]}")
    done_mark.write_text(str(time.time()), encoding="utf-8")
    return idx_dir, ref_path, {
        "cached": False, "digest": digest, "ref_bp": total,
        "ref_count": len(ref_records), "index_seconds": round(time.monotonic() - started, 3),
    }


# ---------------------------------------------------------------- SAM 解析


def _tag_map(fields: Sequence[str]) -> dict[str, str]:
    out = {}
    for f in fields:
        if len(f) > 5 and f[2] == ":":
            out[f[:2]] = f[5:]
    return out


def parse_sam(text: str, ref_seqs: dict[str, str]) -> list[AlignRow]:
    rows: list[AlignRow] = []
    for line in text.splitlines():
        if not line or line.startswith("@"):
            continue
        f = line.split("\t")
        if len(f) < 11:
            continue
        qname = f[0]
        flag = int(f[1])
        rname = f[2]
        pos = int(f[3])
        mapq = int(f[4])
        cigar = f[5]
        seq = f[9]
        tags = _tag_map(f[11:])

        if flag & 4 or rname == "*":   # unmapped
            rows.append(AlignRow(
                query=qname, query_len=len(seq), flag=flag, ref="", pos=0, mapq=0,
                cigar="*", nm=None, score=None, matches=0, mismatches=0,
                insertions=0, deletions=0, identity=0.0, strand="+",
                ref_aligned="", query_aligned="",
            ))
            continue

        ref_seq = ref_seqs.get(rname, "")
        strand = "-" if flag & 16 else "+"
        qseq = _revcomp(seq) if strand == "-" else seq

        if ref_seq:
            ref_aln, qry_aln, matches, mismatches = expand_alignment(ref_seq, pos, cigar, qseq)
        else:
            ref_aln, qry_aln, matches, mismatches = "", "", 0, 0

        blocks = parse_cigar(cigar)
        cs = cigar_summary(blocks)
        nm = int(tags["NM"]) if "NM" in tags else None
        score = int(tags["AS"]) if "AS" in tags else None

        denom = cs["match"] + cs["ins"] + cs["del"]
        identity = (matches / denom) if denom else 0.0

        diffs = diffs_from_alignment(ref_aln, qry_aln, pos) if ref_aln else []

        rows.append(AlignRow(
            query=qname, query_len=len(seq), flag=flag, ref=rname, pos=pos,
            mapq=mapq, cigar=cigar, nm=nm, score=score,
            matches=matches, mismatches=mismatches,
            insertions=cs["ins"], deletions=cs["del"],
            identity=identity, strand=strand,
            ref_aligned=ref_aln, query_aligned=qry_aln,
            diffs=diffs, secondary=bool(flag & 256),
        ))
    return rows


# ---------------------------------------------------------------- 主流程


def _resolve_params(params: dict) -> dict:
    p = dict(DEFAULTS)
    p.update({k: v for k, v in (params or {}).items() if v is not None})

    preset_name = p.get("preset") or "strict"
    preset = PRESETS.get(preset_name, PRESETS["strict"])
    k = p.get("min_seed")
    t = p.get("min_score")
    w = p.get("band_width")
    p["min_seed"] = int(k) if k not in (None, "", 0) else preset["k"]
    p["min_score"] = int(t) if t not in (None, "", -1) else preset["T"]
    p["band_width"] = int(w) if w not in (None, "", 0) else preset["W"]
    p["preset_label"] = preset["label"]

    try:
        p["threads"] = max(1, min(int(p.get("threads") or 2), 8))
    except (TypeError, ValueError):
        p["threads"] = 2
    try:
        p["max_hits"] = max(1, min(int(p.get("max_hits") or 500), 20000))
    except (TypeError, ValueError):
        p["max_hits"] = 500
    try:
        p["min_mapq"] = max(0, min(int(p.get("min_mapq") or 0), 60))
    except (TypeError, ValueError):
        p["min_mapq"] = 0
    mm = p.get("max_mismatch")
    try:
        p["max_mismatch"] = int(mm) if mm not in (None, "", -1) else None
    except (TypeError, ValueError):
        p["max_mismatch"] = None
    return p


def validate_inputs(ref_records: Sequence[FastaRecord], queries: Sequence[FastaRecord]) -> list[dict]:
    """返回 warnings 列表（level/code/message）。"""
    warns: list[dict] = []

    if not ref_records:
        warns.append({"level": "error", "code": "no_ref", "message": "请提供参考序列（FASTA）。"})
    if not queries:
        warns.append({"level": "error", "code": "no_query", "message": "请提供待比对的查询序列。"})

    # 参考：非 DNA 字符
    bad_ref = [(r.name, non_dna_residues(r.seq)) for r in ref_records]
    bad_ref = [(n, c) for n, c in bad_ref if c]
    if bad_ref:
        names = ", ".join(f"{n}({'/'.join(c[:6])})" for n, c in bad_ref[:3])
        warns.append({
            "level": "error", "code": "ref_not_dna",
            "message": f"参考序列含非核酸字符：{names}。BWA-MEM 只能比对 A/C/G/T/N。",
        })
    if any(looks_like_protein(r.seq) for r in ref_records):
        warns.append({
            "level": "error", "code": "ref_protein",
            "message": "参考序列看起来是蛋白序列。BWA-MEM 是核酸比对器，蛋白序列会被静默忽略。",
        })

    # 查询：非 DNA 字符
    bad_q = [(r.name, non_dna_residues(r.seq)) for r in queries]
    bad_q = [(n, c) for n, c in bad_q if c]
    if bad_q:
        names = ", ".join(f"{n}({'/'.join(c[:6])})" for n, c in bad_q[:3])
        warns.append({
            "level": "error", "code": "query_not_dna",
            "message": f"查询序列含非核酸字符：{names}。BWA-MEM 只能比对 A/C/G/T/N。",
        })
    if any(looks_like_protein(r.seq) for r in queries):
        warns.append({
            "level": "error", "code": "query_protein",
            "message": "查询序列看起来是蛋白序列（或氨基酸序列），无法用 BWA-MEM 比对。",
        })

    # 长度统计
    if queries:
        lens = sorted(len(r.seq) for r in queries)
        shortest = lens[0]
        if shortest < 30:
            warns.append({
                "level": "warn", "code": "short_query",
                "message": (
                    f"最短查询只有 {shortest} bp。bwa mem 默认（-k19 -T30）不会比对短于 30bp 的序列；"
                    "请把预设切到「短序列」或「极短序列」，并把结果当作定位参考。"
                ),
            })
        if shortest < 12:
            warns.append({
                "level": "warn", "code": "very_short_query",
                "message": (
                    f"最短查询只有 {shortest} bp。实测 9bp 随机序列在 3kb 参考上会得到大量假比对，"
                    "请结合 MAPQ、identity 与唯一性命中数判断，不要直接采信。"
                ),
            })
        too_long = [r.name for r in queries if len(r.seq) > MAX_QUERY_LEN]
        if too_long:
            warns.append({
                "level": "error", "code": "query_too_long",
                "message": f"{len(too_long)} 条查询超过 {MAX_QUERY_LEN:,} bp 上限。",
            })

    total_ref = sum(len(r.seq) for r in ref_records)
    if total_ref > MAX_REF_BP:
        warns.append({
            "level": "error", "code": "ref_too_long",
            "message": f"参考总长 {total_ref:,} bp 超过上限 {MAX_REF_BP:,} bp。",
        })
    if total_ref and total_ref < 200:
        warns.append({
            "level": "warn", "code": "ref_short",
            "message": f"参考只有 {total_ref} bp，比对上来的序列几乎无法判断特异性。",
        })

    if len(queries) > MAX_QUERY_SEQS:
        warns.append({
            "level": "error", "code": "too_many_queries",
            "message": f"查询序列 {len(queries)} 条，超过上限 {MAX_QUERY_SEQS:,} 条。",
        })

    # 重名
    names = [r.name for r in ref_records]
    if len(set(names)) != len(names):
        warns.append({
            "level": "error", "code": "dup_ref_name",
            "message": "参考序列存在重名，BWA 索引会互相覆盖。",
        })

    return warns


def _write_queries(queries: Sequence[FastaRecord], path: Path) -> None:
    lines: list[str] = []
    for i, r in enumerate(queries):
        name = r.name or f"query{i + 1}"
        lines.append(f">{name}")
        seq = r.seq
        for j in range(0, len(seq), 70):
            lines.append(seq[j:j + 70])
    path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")


def align(
    ref_records: Sequence[FastaRecord],
    queries: Sequence[FastaRecord],
    params: dict,
    progress=None,
) -> dict:
    """执行比对，返回可直接给前端的结构。"""
    p = _resolve_params(params)

    def step(stage: str, frac: float, msg: str = "") -> None:
        if progress is not None:
            progress.update(stage, frac, msg)

    step("准备参考", 0.05, f"{len(ref_records)} 条参考序列")
    idx_dir, ref_path, idx_info = ensure_index(ref_records)

    step("写查询", 0.15, f"{len(queries)} 条查询序列")
    q_path = idx_dir / f"query_{hashlib.sha1(str(time.time()).encode()).hexdigest()[:8]}.fa"
    _write_queries(queries, q_path)

    cmd = [
        BWA_BIN, "mem",
        "-k", str(p["min_seed"]),
        "-T", str(p["min_score"]),
        "-w", str(p["band_width"]),
        "-t", str(p["threads"]),
    ]
    if p.get("all_alignments"):
        cmd += ["-a", "-h", str(p["max_hits"])]
    cmd += [str(ref_path), str(q_path)]

    step("比对中", 0.35, f"bwa mem -k{p['min_seed']} -T{p['min_score']}")
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600,
                              cwd=str(idx_dir), errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise ToolError("bwa", "bwa mem 超时（>3600s）") from exc
    finally:
        try:
            q_path.unlink()
        except OSError:
            pass

    if proc.returncode != 0:
        raise ToolError("bwa", f"bwa mem 失败：{(proc.stderr or '').strip()[:800]}")
    elapsed = time.monotonic() - started

    step("解析结果", 0.8, "解析 SAM")
    ref_seqs = {r.name: r.seq for r in ref_records}
    rows = parse_sam(proc.stdout or "", ref_seqs)

    # 过滤
    if p["min_mapq"]:
        rows = [r for r in rows if r.mapq >= p["min_mapq"] or r.ref == ""]
    if p["max_mismatch"] is not None:
        rows = [r for r in rows if r.nm is None or r.nm <= p["max_mismatch"]]

    # 排序
    sort_by = p.get("sort_by") or "query"
    if sort_by == "score":
        rows.sort(key=lambda r: (-(r.score or 0), r.query))
    elif sort_by == "identity":
        rows.sort(key=lambda r: (-r.identity, r.query))
    else:
        rows.sort(key=lambda r: (r.query, -r.mapq, -(r.score or 0)))

    # 每条 query 的唯一性命中统计
    hits_per_query: dict[str, int] = {}
    for r in rows:
        if r.ref:
            hits_per_query[r.query] = hits_per_query.get(r.query, 0) + 1

    mapped = sum(1 for r in rows if r.ref)
    unmapped = sum(1 for r in rows if not r.ref)
    queries_with_hit = len(hits_per_query)
    total_diffs = sum(len(r.diffs) for r in rows)
    subs = sum(1 for r in rows for d in r.diffs if d["kind"] == "sub")

    step("完成", 1.0, f"{mapped} 条比对 · {elapsed:.2f}s")

    return {
        "rows": [r.to_dict() for r in rows],
        "params": p,
        "index": idx_info,
        "stats": {
            "ref_count": len(ref_records),
            "ref_bp": sum(len(r.seq) for r in ref_records),
            "query_count": len(queries),
            "query_bp": sum(len(r.seq) for r in queries),
            "alignments": len(rows),
            "mapped": mapped,
            "unmapped": unmapped,
            "queries_with_hit": queries_with_hit,
            "multi_hit_queries": sum(1 for v in hits_per_query.values() if v > 1),
            "total_diffs": total_diffs,
            "substitutions": subs,
            "seconds": round(elapsed, 3),
        },
        "hits_per_query": hits_per_query,
    }
