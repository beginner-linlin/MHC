"""调用三个预测工具并解析输出。

设计要点（全部来自实测）：
- 三个工具在出错时**退出码仍为 0**，错误信息打在 stdout。因此不能靠 rc 判断成败，
  必须同时检查 stdout 中的 Error 行与是否解析到数据行。
- netMHCpan / netMHCstabpan 的 `-p` 输入，Identity 列固定为 `PEPLIST`；
  `-f` 输入时为 FASTA 头（工具会截断到 10 字符），故写盘前统一把名字压到
  <=10 字符并保证唯一，解析时再用映射还原。
- netMHCstabpan 的 `-p` 模式要求所有肽**长度一致**，混合长度必须按长度分组分别调用。
- 非标准氨基酸（B/Z/U/J/O/X/-/*）会被工具静默替换为 X，应在入库前校验并提示。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence


class ProgressLike(Protocol):
    """进度回调的鸭子类型（mhc.jobs.Progress 满足它）。"""

    def update(self, stage: str, progress: float, message: str = "") -> None: ...
    def check(self) -> None: ...
    @property
    def cancelled(self) -> bool: ...


# ---------------------------------------------------------------- 常量

STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")

#: 每个工具自己的临时目录（launcher 里的默认值在部分环境下不可用）
TOOL_TMP = {
    "netMHCpan": "/opt/bio/netMHCpan-4.2/tmp",
    "netchop": "/opt/bio/netchop-3.1/tmp",
    "netMHCstabpan": "/opt/bio/netMHCstabpan-1.0/tmp",
}

BINARIES = {
    "netMHCpan": "netMHCpan",
    "netchop": "netchop",
    "netMHCstabpan": "netMHCstabpan",
    "netMHCpan_ctx": "netMHCpan_ctx",
}

#: 工具输出里“这其实是失败”的特征行
ERROR_PATTERNS = (
    "Error",
    "error:",
    "Wrong line format",
    "Cannot ",
    "Unable to open",
    "not found",
    "must be of length",
    "must be equal",
)

DEFAULT_TIMEOUT = 900


class ToolError(RuntimeError):
    """工具执行失败（含“退出码 0 但输出 Error”的情况）。"""

    def __init__(self, tool: str, message: str, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.tool = tool
        self.stdout = stdout
        self.stderr = stderr

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "message": str(self),
            "stdout_tail": _tail(self.stdout, 4000),
            "stderr_tail": _tail(self.stderr, 2000),
        }


def _tail(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else "..." + text[-n:]


# ---------------------------------------------------------------- 输入整理


@dataclass
class FastaRecord:
    name: str
    seq: str


def parse_fasta(text: str) -> list[FastaRecord]:
    """宽松解析 FASTA。没有 `>` 头时，把整段当作单条序列。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    records: list[FastaRecord] = []
    if ">" not in text:
        seq = re.sub(r"[^A-Za-z*\-]", "", text).upper().rstrip("*")
        return [FastaRecord("Protein", seq)] if seq else []

    cur_name, cur_parts = None, []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            if cur_name is not None:
                records.append(FastaRecord(cur_name, "".join(cur_parts)))
            header = line[1:].strip()
            cur_name = header.split()[0] if header else f"seq{len(records) + 1}"
            cur_parts = []
        elif cur_name is not None:
            cur_parts.append(re.sub(r"[^A-Za-z*\-]", "", line).upper())
    if cur_name is not None:
        records.append(FastaRecord(cur_name, "".join(cur_parts)))

    out = []
    for r in records:
        seq = r.seq.replace("-", "").rstrip("*")
        if seq:
            out.append(FastaRecord(r.name, seq))
    return out


def parse_peptide_list(text: str) -> list[str]:
    """每行一条肽；忽略空行、`#` 注释、以及行内其他列（取第一列）。"""
    peptides: list[str] = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = re.split(r"[\s,;\t]+", line)[0]
        token = re.sub(r"[^A-Za-z*]", "", token).upper().rstrip("*")
        if token:
            peptides.append(token)
    return peptides


def looks_like_fasta(text: str) -> bool:
    stripped = (text or "").lstrip()
    return stripped.startswith(">")


def nonstandard_residues(seqs: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for s in seqs:
        found |= {c for c in s.upper() if c not in STANDARD_AA}
    return found


def unique_short_names(records: Sequence[FastaRecord], limit: int = 10) -> dict[str, str]:
    """把 FASTA 名压到 <=limit 字符并保证唯一（工具会把名字截断到 10 字符）。

    返回 {原始名: 压缩后的名字}。压缩规则：保留前缀，冲突时追加序号。
    """
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for i, rec in enumerate(records):
        base = re.sub(r"[^A-Za-z0-9_.\-]", "_", rec.name)
        base = base[:limit] or f"p{i}"
        cand, n = base, 1
        while cand in used:
            suffix = str(n)
            cand = base[: limit - len(suffix)] + suffix
            n += 1
        used.add(cand)
        mapping[rec.name] = cand
    return mapping


# ---------------------------------------------------------------- 执行层


@dataclass
class RunResult:
    tool: str
    argv: list[str]
    stdout: str
    stderr: str
    rc: int
    seconds: float

    def has_error(self) -> bool:
        for line in self.stdout.splitlines():
            s = line.strip()
            if s.startswith("#"):
                continue
            for pat in ERROR_PATTERNS:
                if pat in s:
                    return True
        return bool(self.stderr.strip()) and self.rc != 0


@dataclass
class ToolCaller:
    """在受控临时目录里调用工具。"""

    workdir: Path
    timeout: int = DEFAULT_TIMEOUT
    env_overrides: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workdir = Path(self.workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _env(self, tool: str) -> dict[str, str]:
        env = os.environ.copy()
        tmp = TOOL_TMP.get(tool)
        if tmp:
            Path(tmp).mkdir(parents=True, exist_ok=True)
            env["TMPDIR"] = tmp
        env["LC_ALL"] = "C"
        env.update(self.env_overrides)
        return env

    def run(self, tool: str, args: Sequence[str], *, cwd: Path | None = None) -> RunResult:
        import time

        binary = shutil.which(BINARIES[tool]) or BINARIES[tool]
        argv = [binary, *[str(a) for a in args]]
        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                cwd=str(cwd or self.workdir),
                env=self._env(tool),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(
                tool,
                f"{tool} 超时（>{self.timeout}s）",
                (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            ) from exc
        except FileNotFoundError as exc:
            raise ToolError(tool, f"找不到可执行文件：{binary}") from exc

        return RunResult(
            tool=tool,
            argv=argv,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            rc=proc.returncode,
            seconds=time.monotonic() - started,
        )

    def run_checked(self, tool: str, args: Sequence[str], **kw) -> RunResult:
        res = self.run(tool, args, **kw)
        if res.has_error():
            raise ToolError(tool, _first_error(res.stdout, res.stderr) or f"{tool} 执行失败", res.stdout, res.stderr)
        return res

    # ------------------------------------------------------------ 写输入

    def write_peptides(self, peptides: Sequence[str], name: str = "peptides.pep") -> Path:
        path = self.workdir / name
        path.write_text("\n".join(peptides) + "\n", encoding="utf-8")
        return path

    def write_fasta(self, records: Sequence[FastaRecord], name: str = "input.fsa") -> tuple[Path, dict[str, str]]:
        mapping = unique_short_names(records)
        path = self.workdir / name
        lines = []
        for rec in records:
            lines.append(f">{mapping[rec.name]}")
            seq = rec.seq
            for i in range(0, len(seq), 60):
                lines.append(seq[i : i + 60])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path, mapping


def _first_error(stdout: str, stderr: str) -> str:
    for line in stdout.splitlines():
        if line.strip().startswith("#"):
            continue
        if any(p in line for p in ERROR_PATTERNS):
            return line.strip()
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return ""


# ---------------------------------------------------------------- 解析层


@dataclass
class PanRow:
    pos: int
    mhc: str
    peptide: str
    core: str
    icore: str
    identity: str
    score_el: float
    rank_el: float
    score_ba: float | None = None
    rank_ba: float | None = None
    aff_nm: float | None = None
    bind: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChopRow:
    pos: int
    aa: str
    cleavage: str
    score: float
    protein: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StabRow:
    pos: int
    hla: str
    peptide: str
    identity: str
    pred: float
    thalf: float
    rank_stab: float
    l50: float | None = None
    aff: float | None = None
    rank_aff: float | None = None
    combined: float | None = None
    combined_rank: float | None = None
    bind: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _to_float(tok: str) -> float | None:
    try:
        return float(tok)
    except (TypeError, ValueError):
        return None


_BIND_TAIL = ("<=", "<", ">=", ">")


def _strip_bind(tokens: list[str]) -> tuple[list[str], str]:
    """把行尾的 `<= SB` / `<= WB` 拆出来。"""
    if len(tokens) >= 2 and tokens[-2] in _BIND_TAIL:
        return tokens[:-2], f"{tokens[-2]} {tokens[-1]}"
    return tokens, ""


def parse_pan_output(text: str, with_ba: bool = True) -> list[PanRow]:
    """解析 netMHCpan 数据行。

    列序：Pos MHC Peptide Core Of Gp Gl Ip Il Icore Identity Score_EL %Rank_EL
          [Score_BA %Rank_BA Aff(nM)] BindLevel
    """
    rows: list[PanRow] = []
    need = 15 if with_ba else 12
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith(("Pos ", "---", "Protein ", "NetChop", "HLA-")):
            continue
        tokens = line.split()
        if len(tokens) < (need - 2) or not tokens[0].isdigit():
            continue
        tokens, bind = _strip_bind(tokens)
        # 至少要有 pos..identity + scoreEL + rankEL
        if len(tokens) < 12:
            continue
        try:
            pos = int(tokens[0])
        except ValueError:
            continue
        mhc, peptide, core = tokens[1], tokens[2], tokens[3]
        # 定位 Identity 的起点：Score_EL 之前的那个 token。
        # 倒数第 2、3 个是 numeric rank/score；identity 紧随 Icore。
        # 依列语义：tokens[4:9] = Of Gp Gl Ip Il, tokens[9] = Icore
        icore = tokens[9]
        identity = tokens[10]
        score_el = _to_float(tokens[11])
        rank_el = _to_float(tokens[12]) if len(tokens) > 12 else None
        if score_el is None or rank_el is None:
            continue
        row = PanRow(pos, mhc, peptide, core, icore, identity, score_el, rank_el, bind=bind)
        if with_ba and len(tokens) >= 16:
            row.score_ba = _to_float(tokens[13])
            row.rank_ba = _to_float(tokens[14])
            row.aff_nm = _to_float(tokens[15])
        rows.append(row)
    return rows


def parse_chop_output(text: str) -> dict[str, list[ChopRow]]:
    """解析 netchop 输出，按蛋白名分组。

    数据行：`pos AA C score Ident`；每个蛋白后跟一行
    `Number of cleavage sites N. Number of amino acids M. Protein name X`
    """
    groups: dict[str, list[ChopRow]] = {}
    pending: list[ChopRow] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        m = re.match(r"^Number of cleavage sites .* Protein name (\S+)", line.strip())
        if m:
            groups.setdefault(m.group(1), []).extend(pending)
            pending = []
            continue
        if line.lstrip().startswith(("pos ", "---")) or line.startswith("NetChop"):
            continue
        tokens = line.split()
        if len(tokens) < 5 or not tokens[0].isdigit():
            continue
        try:
            pos = int(tokens[0])
            score = float(tokens[3])
        except (ValueError, IndexError):
            continue
        pending.append(ChopRow(pos, tokens[1], tokens[2], score, tokens[4]))
    if pending:
        groups.setdefault("(unnamed)", []).extend(pending)
    return groups


def parse_stab_output(text: str, with_ia: bool = True) -> list[StabRow]:
    """解析 netMHCstabpan 数据行。

    列序：pos HLA peptide Identity Pred Thalf(h) %Rank_Stab
          [1-log50k Aff(nM) %Rank_aff Combined Combined_%rank] BindLevel
    """
    rows: list[StabRow] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith(("pos ", "---", "Protein ", "HLA-", "NetChop")):
            continue
        tokens = line.split()
        if len(tokens) < 7 or not tokens[0].isdigit():
            continue
        tokens, bind = _strip_bind(tokens)
        if len(tokens) < 7:
            continue
        try:
            pos = int(tokens[0])
            pred = float(tokens[4])
            thalf = float(tokens[5])
            rank_stab = float(tokens[6])
        except (ValueError, IndexError):
            continue
        row = StabRow(pos, tokens[1], tokens[2], tokens[3], pred, thalf, rank_stab, bind=bind)
        if with_ia and len(tokens) >= 12:
            row.l50 = _to_float(tokens[7])
            row.aff = _to_float(tokens[8])
            row.rank_aff = _to_float(tokens[9])
            row.combined = _to_float(tokens[10])
            row.combined_rank = _to_float(tokens[11])
        rows.append(row)
    return rows


def iter_pan_blocks(text: str) -> list[tuple[str, str]]:
    """把 netMHCpan 多肽/多等位输出按 (蛋白, 等位基因) 切块。

    返回 [(等位基因, 蛋白), ...]，顺序与文件一致，用于把行归属到正确的组。
    块边界由 `Protein X. Allele Y. ...` 汇总行决定（该行在块末尾）。
    """
    blocks: list[tuple[str, str]] = []
    for raw in text.splitlines():
        m = re.match(r"^Protein (\S+)\. Allele (\S+)\.", raw.strip())
        if m:
            blocks.append((m.group(2).rstrip("."), m.group(1)))
    return blocks


# ---------------------------------------------------------------- 语义层（对外主接口）


def _normalize_allele(a: str) -> str:
    """工具只认不带星号的写法（HLA-A02:01）。"""
    return a.strip().replace("*", "")


def resolve_alleles(values: Sequence[str] | str) -> list[str]:
    if isinstance(values, str):
        parts = re.split(r"[,\s;]+", values)
    else:
        parts = list(values)
    out: list[str] = []
    for p in parts:
        p = _normalize_allele(p)
        if not p:
            continue
        if re.match(r"^HLA-[ABC]\d{4}$", p):  # HLA-A0201 -> HLA-A02:01
            p = f"{p[:5]}{p[5:7]}:{p[7:]}"
        if p not in out:
            out.append(p)
    return out


def predict_binding(
    caller: ToolCaller,
    *,
    peptides: Sequence[str] | None = None,
    records: Sequence[FastaRecord] | None = None,
    alleles: Sequence[str],
    with_ba: bool = True,
    sort: bool = False,
    threshold: float | None = None,
    lengths: Sequence[int] | None = None,
) -> tuple[list[PanRow], dict[str, str], RunResult]:
    """跑 netMHCpan。返回 (行, 名称映射, 原始结果)。"""
    alleles = resolve_alleles(alleles)
    if not alleles:
        raise ValueError("至少需要一个等位基因")

    args: list[str] = []
    mapping: dict[str, str] = {}
    if records:
        path, mapping = caller.write_fasta(records)
        args += ["-f", str(path), "-inptype", "0"]
        if lengths:
            args += ["-l", ",".join(str(x) for x in lengths)]
    elif peptides:
        path = caller.write_peptides(list(peptides))
        args += ["-p", str(path), "-inptype", "1"]
    else:
        raise ValueError("没有输入序列")

    args += ["-a", ",".join(alleles)]
    if with_ba:
        args.append("-BA")
    if sort:
        args.append("-s")
    if threshold is not None:
        args += ["-t", str(threshold)]

    res = caller.run_checked("netMHCpan", args)
    rows = parse_pan_output(res.stdout, with_ba=with_ba)
    if not rows:
        if res.has_error():
            raise ToolError("netMHCpan", _first_error(res.stdout, res.stderr) or "netMHCpan 未返回数据", res.stdout, res.stderr)
        raise ToolError("netMHCpan", "netMHCpan 未返回任何数据行（请检查序列或等位基因）", res.stdout, res.stderr)
    if mapping:
        inverse = {v: k for k, v in mapping.items()}
        for r in rows:
            r.identity = inverse.get(r.identity, r.identity)
    return rows, mapping, res


def predict_cleavage(
    caller: ToolCaller,
    *,
    records: Sequence[FastaRecord],
    version: int = 0,
    threshold: float = 0.5,
) -> tuple[dict[str, list[ChopRow]], dict[str, str], RunResult]:
    """跑 netchop，按蛋白名分组返回。"""
    path, mapping = caller.write_fasta(records, "chop_input.fsa")
    args = [str(path)]
    if version:
        args += ["-v", str(version)]
    if threshold is not None:
        args += ["-t", str(threshold)]
    res = caller.run_checked("netchop", args)
    groups = parse_chop_output(res.stdout)
    if not groups:
        raise ToolError("netchop", _first_error(res.stdout, res.stderr) or "netchop 未返回任何数据行", res.stdout, res.stderr)
    inverse = {v: k for k, v in mapping.items()}
    fixed = {inverse.get(k, k): v for k, v in groups.items()}
    return fixed, mapping, res


def predict_stability(
    caller: ToolCaller,
    *,
    peptides: Sequence[str] | None = None,
    records: Sequence[FastaRecord] | None = None,
    alleles: Sequence[str],
    with_ia: bool = True,
    sort: int | None = None,
    lengths: Sequence[int] | None = None,
) -> tuple[list[StabRow], dict[str, str], RunResult]:
    """跑 netMHCstabpan。

    `-p` 模式要求所有肽长度一致，调用方需自行分组（见 predict_stability_mixed）。
    """
    alleles = resolve_alleles(alleles)
    if not alleles:
        raise ValueError("至少需要一个等位基因")

    args: list[str] = []
    mapping: dict[str, str] = {}
    if records:
        path, mapping = caller.write_fasta(records, "stab_input.fsa")
        args += ["-f", str(path), "-inptype", "0"]
        if lengths:
            args += ["-l", ",".join(str(x) for x in lengths)]
    elif peptides:
        path = caller.write_peptides(list(peptides), "stab.pep")
        args += ["-p", str(path), "-inptype", "1"]
    else:
        raise ValueError("没有输入序列")

    args += ["-a", ",".join(alleles)]
    if with_ia:
        args.append("-ia")
    if sort is not None and sort >= 0:
        args += ["-s", str(sort)]

    res = caller.run_checked("netMHCstabpan", args)
    rows = parse_stab_output(res.stdout, with_ia=with_ia)
    if not rows:
        raise ToolError("netMHCstabpan", _first_error(res.stdout, res.stderr) or "netMHCstabpan 未返回任何数据行", res.stdout, res.stderr)
    if mapping:
        inverse = {v: k for k, v in mapping.items()}
        for r in rows:
            r.identity = inverse.get(r.identity, r.identity)
    return rows, mapping, res


def predict_stability_mixed(
    caller: ToolCaller,
    peptides: Sequence[str],
    alleles: Sequence[str],
    with_ia: bool = True,
) -> tuple[list[StabRow], list[RunResult]]:
    """按肽长分组分别调用（工具要求同一次调用内长度一致）。"""
    by_len: dict[int, list[str]] = {}
    for p in peptides:
        by_len.setdefault(len(p), []).append(p)

    all_rows: list[StabRow] = []
    runs: list[RunResult] = []
    for i, (length, group) in enumerate(sorted(by_len.items())):
        rows, _, res = predict_stability(
            caller,
            peptides=group,
            alleles=alleles,
            with_ia=with_ia,
        )
        runs.append(res)
        all_rows.extend(rows)
    return all_rows, runs


def list_alleles(caller: ToolCaller) -> list[str]:
    """netMHCpan 的 `-listMHC` 输出里每个等位基因会出现两种写法
    （`HLA-A02:01` 与 `HLA-A0201`）。这里统一成带冒号的标准写法并去重。"""
    res = caller.run("netMHCpan", ["-listMHC"])
    seen: set[str] = set()
    out: list[str] = []
    for line in res.stdout.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if not s.startswith("HLA-"):
            continue
        tok = s.split()[0]
        norm_list = resolve_alleles([tok])
        if not norm_list:
            continue
        norm = norm_list[0]
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    out.sort()
    return out


#: 各工具版本号存放在安装目录的 data/version 里（`-version` 参数并不存在）
VERSION_FILES = {
    "netMHCpan": "/opt/bio/netMHCpan-4.2/data/version",
    "netchop": "/opt/bio/netchop-3.1/data/version",
    "netMHCstabpan": "/opt/bio/netMHCstabpan-1.0/data/version",
}

#: netchop 的 data/ 里只有 matrices，没有 version 文件。
#: 依据发布包名 netchop-3.1d 与 etc/ 下的 20S.3.0 / Cterm.3.0 两个矩阵版本。
FALLBACK_VERSIONS = {
    "netchop": "NetChop 3.1d (Cterm.3.0 / 20S.3.0)",
}


def tool_version(caller: ToolCaller, tool: str) -> str:
    path = Path(VERSION_FILES.get(tool, ""))
    if path.is_file():
        try:
            return path.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0]
        except OSError:
            pass
    return FALLBACK_VERSIONS.get(tool, "unknown")


def new_workdir(root: Path) -> Path:
    d = Path(root) / uuid.uuid4().hex[:12]
    d.mkdir(parents=True, exist_ok=True)
    return d


__all__ = [
    "STANDARD_AA",
    "TOOL_TMP",
    "ToolError",
    "ToolCaller",
    "RunResult",
    "PanRow",
    "ChopRow",
    "StabRow",
    "FastaRecord",
    "ProgressLike",
    "parse_fasta",
    "parse_peptide_list",
    "looks_like_fasta",
    "nonstandard_residues",
    "resolve_alleles",
    "predict_binding",
    "predict_cleavage",
    "predict_stability",
    "predict_stability_mixed",
    "list_alleles",
    "tool_version",
    "new_workdir",
    "parse_pan_output",
    "parse_chop_output",
    "parse_stab_output",
    "unique_short_names",
]
