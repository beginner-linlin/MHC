"""外部数据库与在线工具集成。

设计书（基于AI的胰腺癌新抗原mRNA疫苗设计与评价）用到的资源分两类：

A. 可内嵌直接检索/调用的（本模块实现）：
   - GDC（Genomic Data Commons）突变检索：TCGA-PAAD 等项目按基因查体细胞突变
     端点 POST https://api.gdc.cancer.gov/ssms
     注意：按基因过滤的字段名是 consequence.transcript.gene.symbol，
           用 symbol / gene.symbol 会返回 0 条（已实测）。
   - IEDB Analysis Resource tools_api：云端 MHC-I / MHC-II 结合与稳定性预测
     端点 POST https://tools-cluster-interface.iedb.org/tools_api/{mhci,mhcii}
     返回 tab 分隔文本；无 csv 参数。

B. 只能外链的（给出卡片与说明）：
   - IEDB 免疫原性工具（网页表单，无 REST API）
   - NetCTLpan、VaxiJen、ToxinPred、OptiType、JCAT、GenScript、C-ImmSim 等

所有网络请求走标准库 urllib（venv 未装 requests），带超时与错误归一化。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GDC_API = "https://api.gdc.cancer.gov"
IEDB_TOOLS_API = "https://tools-cluster-interface.iedb.org/tools_api"
DEFAULT_TIMEOUT = 45
USER_AGENT = "MHC-Workbench/1.0 (+https://github.com/beginner-linlin/MHC)"

# GDC 里按基因过滤必须用这个完整路径，简写字段无效
GDC_GENE_FIELD = "consequence.transcript.gene.symbol"
GDC_PROJECT_FIELD = "cases.project.project_id"


class ResourceError(RuntimeError):
    """外部资源调用失败（网络、参数、远端报错）。"""

    def __init__(self, message: str, *, detail: str = "", status: int = 502):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {"message": self.message, "detail": self.detail}


# ---------------------------------------------------------------- HTTP


def _post_form(url: str, data: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> str:
    body = urllib.parse.urlencode({k: v for k, v in data.items() if v is not None}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
            "Accept": "text/plain, */*",
        },
        method="POST",
    )
    return _read(req, timeout)


def _post_json(url: str, payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="POST",
    )
    text = _read(req, timeout)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResourceError("远端返回的不是合法 JSON", detail=text[:500]) from exc


def _get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    text = _read(req, timeout)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResourceError("远端返回的不是合法 JSON", detail=text[:500]) from exc


def _read(req: urllib.request.Request, timeout: int) -> str:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:  # noqa: BLE001
            pass
        raise ResourceError(f"远端返回 HTTP {exc.code}", detail=detail) from exc
    except urllib.error.URLError as exc:
        raise ResourceError("无法连接远端服务（网络不通或 DNS 失败）", detail=str(exc.reason)) from exc
    except TimeoutError as exc:
        raise ResourceError("远端服务响应超时", detail=f"{timeout} 秒") from exc


# ---------------------------------------------------------------- GDC 突变检索


def gdc_projects() -> list[dict[str, str]]:
    """常用项目（设计书相关 + 常见肿瘤）。"""
    return [
        {"id": "TCGA-PAAD", "name": "胰腺癌（TCGA-PAAD）", "note": "设计书主用队列，185 例"},
        {"id": "TCGA-LUAD", "name": "肺腺癌（TCGA-LUAD）", "note": "常作方法学对照"},
        {"id": "TCGA-BRCA", "name": "乳腺癌（TCGA-BRCA）", "note": "突变负荷高，适合新抗原筛选"},
        {"id": "TCGA-SKCM", "name": "黑色素瘤（TCGA-SKCM）", "note": "免疫治疗经典队列"},
        {"id": "TCGA-COAD", "name": "结肠癌（TCGA-COAD）", "note": ""},
        {"id": "TCGA-GBM", "name": "胶质母细胞瘤（TCGA-GBM）", "note": ""},
        {"id": "TCGA-HNSC", "name": "头颈鳞癌（TCGA-HNSC）", "note": ""},
        {"id": "TCGA-STAD", "name": "胃癌（TCGA-STAD）", "note": ""},
    ]


PAAD_DRIVERS = ["KRAS", "TP53", "SMAD4", "CDKN2A", "ARID1A", "KDM6A", "MUC16", "TTN", "RYR2", "GNAS"]


def _gdc_filter(project: str, gene: str | None, chromosome: str | None, mutation_type: str | None) -> dict:
    content: list[dict] = []
    if project:
        content.append({"op": "in", "content": {"field": GDC_PROJECT_FIELD, "value": [project]}})
    if gene:
        content.append({"op": "in", "content": {"field": GDC_GENE_FIELD, "value": [gene.strip().upper()]}})
    if chromosome:
        content.append({"op": "in", "content": {"field": "chromosome", "value": [chromosome]}})
    if mutation_type:
        content.append({"op": "in", "content": {"field": "mutation_type", "value": [mutation_type]}})
    if not content:
        raise ResourceError("至少要指定项目或基因", status=400)
    return {"op": "and", "content": content}


GDC_SSM_FIELDS = ",".join(
    [
        "id",
        "chromosome",
        "start_position",
        "end_position",
        "genomic_dna_change",
        "gene_aa_change",
        "mutation_type",
        "mutation_subtype",
        "reference_allele",
        "tumor_allele",
        "ncbi_build",
        "consequence.transcript.gene.symbol",
        "consequence.transcript.consequence_type",
        "consequence.transcript.aa_change",
        "consequence.transcript.transcript_id",
    ]
)


def _flatten_ssm(hit: dict) -> dict[str, Any]:
    """把 GDC 嵌套 consequence 拍平成表格行（取第一条有 aa_change 的 missense 转录本）。"""
    gene = ""
    aa = ""
    ctype = ""
    tx = ""
    for c in hit.get("consequence") or []:
        t = c.get("transcript") or {}
        g = (t.get("gene") or {}).get("symbol") or ""
        if g and not gene:
            gene = g
        if t.get("aa_change") and not aa:
            aa = t["aa_change"]
            ctype = t.get("consequence_type") or ""
            tx = t.get("transcript_id") or ""
    gene_aa = (hit.get("gene_aa_change") or [""])[0]
    if not aa and gene_aa:
        # 形如 "KRAS Q61H"
        parts = gene_aa.split()
        if len(parts) >= 2:
            gene = gene or parts[0]
            aa = parts[-1]
    return {
        "gene": gene,
        "aa_change": aa,
        "consequence_type": ctype,
        "transcript_id": tx,
        "chromosome": hit.get("chromosome") or "",
        "start": hit.get("start_position"),
        "end": hit.get("end_position"),
        "dna_change": hit.get("genomic_dna_change") or "",
        "ref": hit.get("reference_allele") or "",
        "alt": hit.get("tumor_allele") or "",
        "mutation_type": hit.get("mutation_type") or "",
        "mutation_subtype": hit.get("mutation_subtype") or "",
        "build": hit.get("ncbi_build") or "",
        "ssm_id": hit.get("id") or "",
    }


def search_gdc_mutations(
    *,
    project: str = "TCGA-PAAD",
    gene: str | None = None,
    chromosome: str | None = None,
    mutation_type: str | None = None,
    size: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """在 GDC 检索体细胞突变（SSM）。返回 {total, rows, filters}。"""
    size = max(1, min(int(size), 2000))
    offset = max(0, int(offset))
    payload = {
        "filters": _gdc_filter(project, gene, chromosome, mutation_type),
        "fields": GDC_SSM_FIELDS,
        "format": "JSON",
        "size": size,
        "from": offset,
        "sort": "chromosome:asc,start_position:asc",
    }
    data = _post_json(f"{GDC_API}/ssms", payload, timeout=60)
    d = data.get("data") or {}
    pag = d.get("pagination") or {}
    hits = d.get("hits") or []
    rows = [_flatten_ssm(h) for h in hits]
    return {
        "total": pag.get("total", len(rows)),
        "returned": len(rows),
        "offset": offset,
        "rows": rows,
        "filters": {"project": project, "gene": gene, "chromosome": chromosome, "mutation_type": mutation_type},
    }


def gdc_project_summary(project: str = "TCGA-PAAD") -> dict[str, Any]:
    """项目概况：病例数 + 突变总数。两次轻量查询。"""
    if not project:
        raise ResourceError("缺少项目 ID", status=400)
    proj = _post_json(
        f"{GDC_API}/projects",
        {
            "filters": {"op": "in", "content": {"field": "project_id", "value": [project]}},
            "fields": "project_id,name,primary_site,disease_type,summary.case_count,summary.file_count",
            "size": 1,
        },
        timeout=45,
    )
    hits = ((proj.get("data") or {}).get("hits") or [{}])[0]
    ssm = _post_json(
        f"{GDC_API}/ssms",
        {
            "filters": {"op": "in", "content": {"field": GDC_PROJECT_FIELD, "value": [project]}},
            "size": 0,
        },
        timeout=60,
    )
    ssm_total = ((ssm.get("data") or {}).get("pagination") or {}).get("total", 0)
    return {
        "project_id": hits.get("project_id") or project,
        "name": hits.get("name") or "",
        "primary_site": hits.get("primary_site") or [],
        "disease_type": hits.get("disease_type") or [],
        "case_count": ((hits.get("summary") or {}).get("case_count")) or 0,
        "file_count": ((hits.get("summary") or {}).get("file_count")) or 0,
        "ssm_total": ssm_total,
    }


# ---------------------------------------------------------------- IEDB tools_api

IEDB_MHCI_METHODS = [
    ("netmhcpan_el", "NetMHCpan EL（推荐，与本地一致）"),
    ("netmhcpan_ba", "NetMHCpan BA（亲和力）"),
    ("netmhcpan", "NetMHCpan（4.1 综合）"),
    ("netmhcstabpan", "NetMHCstabpan（稳定性）"),
    ("recommended", "IEDB 推荐组合"),
    ("consensus", "Consensus（多方法共识）"),
    ("ann", "ANN（人工神经网络）"),
    ("smm", "SMM"),
    ("smmpmbec", "SMMPMBEC"),
    ("comblib_sidney2008", "Comblib Sidney 2008"),
    ("pickpocket", "PickPocket"),
    ("netmhccons", "NetMHCcons"),
]

IEDB_MHCII_METHODS = [
    ("recommended", "IEDB 推荐组合"),
    ("netmhciipan", "NetMHCIIpan"),
    ("consensus", "Consensus"),
    ("comblib", "Comblib"),
    ("nn_align", "NN-Align"),
]


def _parse_iedb_table(text: str) -> list[dict[str, str]]:
    """IEDB tools_api 返回 tab 分隔文本，首行是表头。"""
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        return []
    if len(lines) == 1 or lines[0].lower().startswith(("invalid", "error", "the length")):
        raise ResourceError("IEDB 返回错误", detail=text[:600])
    header = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        rows.append({h: cells[i] for i, h in enumerate(header)})
    return rows


def iedb_allele_format(allele: str) -> str:
    """把本地写法转成 IEDB 要求的带星号写法。

    本地工具用 HLA-A02:01（无星号），IEDB tools_api 只认 HLA-A*02:01，
    否则报 Invalid allele name。这里统一补星号。
    """
    a = (allele or "").strip().upper()
    if not a:
        return a
    if "*" in a:
        return a
    # HLA-A02:01 → HLA-A*02:01 ； HLA-A0201 → HLA-A*02:01
    if a.startswith("HLA-") and len(a) >= 8:
        body = a[4:]
        locus = body[0]
        rest = body[1:]
        if ":" in rest:
            return f"HLA-{locus}*{rest}"
        if len(rest) == 4 and rest.isdigit():
            return f"HLA-{locus}*{rest[:2]}:{rest[2:]}"
    # 小鼠 H2-Kb / H2-Db 等保持原样
    return a


def iedb_predict(
    *,
    mhc_class: str = "I",
    method: str = "netmhcpan_el",
    peptides: list[str],
    allele: str,
    length: int | None = None,
) -> dict[str, Any]:
    """调用 IEDB tools_api 做 MHC-I / MHC-II 预测。"""
    mhc_class = (mhc_class or "I").upper().lstrip("MHC-")
    if mhc_class not in ("I", "II"):
        raise ResourceError("mhc_class 只支持 I 或 II", status=400)
    if not peptides:
        raise ResourceError("没有输入肽段", status=400)
    if not allele:
        raise ResourceError("必须指定等位基因", status=400)

    seq_text = "\n".join(p.strip().upper() for p in peptides if p.strip())
    endpoint = "mhci" if mhc_class == "I" else "mhcii"
    data: dict[str, Any] = {
        "method": method,
        "sequence_text": seq_text,
        "allele": iedb_allele_format(allele),
    }
    if mhc_class == "I":
        # IEDB 要求 8-14，缺省 9
        data["length"] = length or 9
    else:
        # MHC-II 用窗口长度，通常 15
        data["length"] = length or 15

    text = _post_form(f"{IEDB_TOOLS_API}/{endpoint}/", data, timeout=180)
    rows = _parse_iedb_table(text)
    return {
        "mhc_class": mhc_class,
        "method": method,
        "allele": allele,
        "count": len(rows),
        "rows": rows,
        "raw_head": text[:1200],
    }


# ---------------------------------------------------------------- 资源卡片


DATABASES: list[dict[str, Any]] = [
    {
        "id": "gdc-paad",
        "name": "GDC / TCGA-PAAD",
        "full": "Genomic Data Commons · 胰腺癌队列",
        "url": "https://portal.gdc.cancer.gov/projects/TCGA-PAAD",
        "api": "内嵌可用（突变检索）",
        "desc": "设计书主用队列。可在此直接按基因检索体细胞突变，或跳转 GDC 门户下载 WES/RNA-Seq 原始数据。",
        "tags": ["突变", "表达", "临床", "内嵌检索"],
        "builtin": True,
    },
    {
        "id": "gdc",
        "name": "GDC 数据门户",
        "full": "Genomic Data Commons",
        "url": "https://portal.gdc.cancer.gov/",
        "api": "内嵌可用（突变检索）",
        "desc": "NCI 统一肿瘤基因组库，含 TCGA / TARGET / CPTAC 等。支持按项目、基因、染色体组合筛选。",
        "tags": ["突变", "表达", "多队列"],
        "builtin": True,
    },
    {
        "id": "icgc",
        "name": "ICGC / PACA-AU",
        "full": "International Cancer Genome Consortium",
        "url": "https://dcc.icgc.org/",
        "api": "外链",
        "desc": "设计书指定 ICGC-PACA-AU（澳大利亚胰腺癌队列）作为独立验证集，避免只用 TCGA 单队列过拟合。",
        "tags": ["突变", "验证集"],
        "builtin": False,
    },
    {
        "id": "iedb",
        "name": "IEDB 表位数据库",
        "full": "Immune Epitope Database",
        "url": "https://www.iedb.org/",
        "api": "外链（查询接口无公开 REST）",
        "desc": "已实验验证的 T/B 细胞表位库。设计书用它交叉验证候选表位是否有实验证据。",
        "tags": ["表位", "实验验证", "免疫原性"],
        "builtin": False,
    },
    {
        "id": "iedb-tools",
        "name": "IEDB Analysis Resource",
        "full": "IEDB 在线分析工具集",
        "url": "https://tools.iedb.org/main/",
        "api": "内嵌可用（MHC-I/II 预测）",
        "desc": "云端预测工具集合：MHC-I/II 结合、加工呈递、免疫原性、B 细胞表位。本工作台已内嵌 mhci/mhcii 预测接口。",
        "tags": ["预测", "内嵌调用"],
        "builtin": True,
    },
    {
        "id": "uniprot",
        "name": "UniProt",
        "full": "Universal Protein Resource",
        "url": "https://www.uniprot.org/",
        "api": "外链",
        "desc": "蛋白参考序列与注释。用于取野生型蛋白全长、确认突变位点在蛋白上的坐标。",
        "tags": ["蛋白序列", "注释"],
        "builtin": False,
    },
    {
        "id": "ensembl",
        "name": "Ensembl",
        "full": "Ensembl Genome Browser",
        "url": "https://www.ensembl.org/index.html",
        "api": "外链",
        "desc": "基因组注释与转录本。GDC 返回的 ENST 编号可在此核对，确认用哪条转录本翻译蛋白。",
        "tags": ["注释", "转录本"],
        "builtin": False,
    },
]


ONLINE_TOOLS: list[dict[str, Any]] = [
    {
        "id": "netctlpan",
        "name": "NetCTLpan 1.1",
        "url": "https://services.healthtech.dtu.dk/services/NetCTLpan-1.1/",
        "stage": "加工呈递",
        "desc": "综合蛋白酶体切割、TAP 转运、MHC 结合的整条呈递通路评分。设计书用来补 NetMHCpan 之外的加工环节信息。",
        "status": "在线可用",
        "local_alt": "本地 NetChop（切割）+ NetMHCpan（结合）分步近似",
    },
    {
        "id": "vaxijen",
        "name": "VaxiJen 2.0",
        "url": "http://www.ddg-pharmfac.net/vaxijen/VaxiJen/VaxiJen.html",
        "stage": "抗原性",
        "desc": "基于蛋白理化性质的抗原性打分（无需比对）。设计书作为候选肽的抗原性特征之一。",
        "status": "站点返回 403（可能需要浏览器直访）",
        "local_alt": "无",
    },
    {
        "id": "toxinpred",
        "name": "ToxinPred 2",
        "url": "https://toxinpred2.sce.iitb.ac.in/",
        "stage": "毒性",
        "desc": "预测肽段毒性，用于剔除有毒候选。设计书安全评估环节。",
        "status": "站点暂不可达",
        "local_alt": "无",
    },
    {
        "id": "iedb-immuno",
        "name": "IEDB 免疫原性",
        "url": "https://tools.iedb.org/immunogenicity/",
        "stage": "免疫原性",
        "desc": "预测肽段能否引发 T 细胞应答（基于实验数据的机器学习模型）。无 REST 接口，需网页提交。",
        "status": "在线可用",
        "local_alt": "无",
    },
    {
        "id": "optitype",
        "name": "OptiType",
        "url": "https://github.com/FRED-2/OptiType",
        "stage": "HLA 分型",
        "desc": "从 RNA-Seq 读段做 HLA-I 分型。是命令行工具（非网页），设计书用它得到每例患者的 HLA 型别。",
        "status": "命令行工具",
        "local_alt": "工作台已内置 10491 个等位基因手工选择",
    },
    {
        "id": "jcat",
        "name": "JCAT",
        "url": "http://www.jcat.de/",
        "stage": "密码子优化",
        "desc": "按目标物种密码子偏好优化序列并评估 CAI。前期预研已验证可用。",
        "status": "在线可用",
        "local_alt": "无",
    },
    {
        "id": "genscript",
        "name": "GenScript 稀有密码子分析",
        "url": "https://www.genscript.com/tools/rare-codon-analyzer",
        "stage": "密码子优化",
        "desc": "设计书指定的密码子优化工具，输出适合人源表达的 ORF。",
        "status": "站点暂不可达",
        "local_alt": "无",
    },
    {
        "id": "cimmsim",
        "name": "C-ImmSim",
        "url": "https://www.iac.cnr.it/filippo/c-immsim/index.html",
        "stage": "免疫模拟",
        "desc": "免疫系统 agent-based 模拟，预测疫苗接种后的抗体/T 细胞动态。设计书用于疫苗设计合理性预演。",
        "status": "页面路径可能变更",
        "local_alt": "无",
    },
    {
        "id": "orffinder",
        "name": "NCBI ORFfinder",
        "url": "https://www.ncbi.nlm.nih.gov/orffinder/",
        "stage": "序列处理",
        "desc": "在核酸序列中找开放阅读框，核对串联多表位 ORF 的翻译是否正确。",
        "status": "在线可用",
        "local_alt": "无",
    },
]


def resource_catalog() -> dict[str, Any]:
    return {
        "databases": DATABASES,
        "tools": ONLINE_TOOLS,
        "gdc_projects": gdc_projects(),
        "paad_drivers": PAAD_DRIVERS,
        "iedb_methods": {"mhci": IEDB_MHCI_METHODS, "mhcii": IEDB_MHCII_METHODS},
    }
