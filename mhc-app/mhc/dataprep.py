"""数据准备（设计书①-⑥步上游工具与数据）——工具清单 + 指南 + 在线检测。

端点（在 web.py 注册）:
  GET  /api/dataprep/tools   已安装上游生信工具清单（读 data/dataprep_tools.json）
  GET  /api/dataprep/guide   十步路线 / TCGA 下载 / 参考基因组 / 流水线脚本说明
  POST /api/dataprep/check   实时检测单个工具 {tool: "fastqc"}
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

APP_ROOT = Path(os.environ.get("MHC_APP_ROOT", "/opt/bio/app"))
INVENTORY_PATH = APP_ROOT / "data" / "dataprep_tools.json"

# 工具注册表: name -> (设计书步骤, 中文名, 版本命令, 安装提示)
TOOL_REGISTRY: dict[str, tuple[int, str, list[str], str]] = {
    "fastqc": (2, "FastQC 测序质控", ["fastqc", "--version"], "apt-get install -y fastqc"),
    "trimmomatic": (2, "Trimmomatic 剪接", ["TrimmomaticPE", "-version"], "apt-get install -y trimmomatic"),
    "bwa": (2, "BWA-MEM 比对", ["bwa"], "apt-get install -y bwa"),
    "samtools": (2, "SAMtools", ["samtools", "--version"], "apt-get install -y samtools"),
    "bcftools": (3, "BCFtools", ["bcftools", "--version"], "apt-get install -y bcftools"),
    "gatk": (3, "GATK4 (MuTect2)", ["gatk", "--version"], "见《流水线使用指南》GATK 安装节"),
    "strelka2": (3, "Strelka2", ["/opt/bio/tools/bin/configureStrelkaSomaticWorkflow", "--version"], "需 python2（Ubuntu-24.04 缺失）；建议用 GATK MuTect2 为主"),
    "vep": (3, "Ensembl VEP 注释", ["vep"], "apt-get install -y ensembl-vep（或 snpeff 替代）"),
    "snpEff": (3, "snpEff 注释", ["snpEff", "-version"], "apt-get install -y snpeff"),
    "STAR": (4, "STAR 比对", ["STAR", "--version"], "apt-get install -y rna-star"),
    "rsem": (4, "RSEM 定量", ["rsem-calculate-expression", "--version"], "apt-get install -y rsem"),
    "bowtie2": (5, "Bowtie2（OptiType 依赖）", ["bowtie2", "--version"], "apt-get install -y bowtie2"),
    "razers3": (5, "Razers3（OptiType 依赖，可选）", ["razers3"], "apt-get install -y seqan-apps"),
    "optitype": (5, "OptiType HLA 分型", ["sh", "-c", "PYTHONPATH=/opt/bio/tools/OptiType/src /opt/bio/tools/optitype-venv/bin/python -m optitype --version"], "见《流水线使用指南》OptiType 安装节"),
}

PIPELINE_SCRIPTS: list[dict[str, str]] = [
    {"file": "10_prepare_ref.sh", "step": "①前置", "desc": "下载 GRCh38 参考基因组并建 BWA/STAR 索引"},
    {"file": "20_qc_trim.sh", "step": "②", "desc": "FastQC 质控 + Trimmomatic 剪接"},
    {"file": "30_align.sh", "step": "②", "desc": "BWA-MEM 比对 + 排序 + 标记重复"},
    {"file": "40_call_somatic.sh", "step": "③", "desc": "MuTect2 / Strelka2 体细胞突变检出"},
    {"file": "50_annotate.sh", "step": "③", "desc": "VEP / snpEff 突变功能注释"},
    {"file": "60_expression.sh", "step": "④", "desc": "STAR + RSEM 转录本定量（TPM）"},
    {"file": "70_hla_typing.sh", "step": "⑤", "desc": "OptiType HLA-I 分型"},
    {"file": "80_extract_mutations.sh", "step": "⑥入口", "desc": "提取错义突变 + 构造 21-mer 肽段区（自动取 UniProt 序列）"},
    {"file": "90_neoantigen.sh", "step": "⑥", "desc": "把突变交给工作台跑 NetMHCpan 全流程预测"},
    {"file": "run_all.sh", "step": "总控", "desc": "①→⑥ 串联，支持断点续跑（--start/--stop）与 --dry-run"},
]

ROUTE_STEPS: list[dict[str, Any]] = [
    {"no": "①", "name": "数据获取", "desc": "TCGA-PAAD / ICGC-PACA-AU（WES + RNA-Seq）", "tools": "GDC 门户 / gdc-client", "by_workbench": "部分（GDC 突变检索已内嵌）"},
    {"no": "②", "name": "质控比对", "desc": "FastQC / Trimmomatic → BWA-MEM (GRCh38)", "tools": "fastqc, trimmomatic, bwa, samtools", "by_workbench": "本地流水线"},
    {"no": "③", "name": "突变检出", "desc": "GATK MuTect2 / Strelka2 → VEP/snpEff 注释", "tools": "gatk, strelka2, vep/snpEff", "by_workbench": "本地流水线"},
    {"no": "④", "name": "表达定量", "desc": "STAR + RSEM（TPM）", "tools": "STAR, rsem", "by_workbench": "本地流水线"},
    {"no": "⑤", "name": "HLA 分型", "desc": "OptiType（从 WES 读段推断患者 HLA-I 型别）", "tools": "optitype, bowtie2", "by_workbench": "本地流水线"},
    {"no": "⑥", "name": "新抗原预测", "desc": "突变±10aa → 8-11aa → NetMHCpan / NetChop / NetMHCstabpan → 综合排序", "tools": "工作台三件套", "by_workbench": "已内嵌（核心）"},
    {"no": "⑦", "name": "模型排序", "desc": "XGBoost / DNN 5 折交叉验证 → 每患者 Top10-20", "tools": "自行建模", "by_workbench": "导出特征表"},
    {"no": "⑧", "name": "疫苗构建", "desc": "GGGGS 多表位串联 → 密码子优化 → UTR/T7/Poly(A)", "tools": "GenScript / JCAT", "by_workbench": "外链资源"},
    {"no": "⑨", "name": "体外制备", "desc": "IVT（m1ΨTP）→ LNP → HEK293T 验证", "tools": "湿实验", "by_workbench": "不做"},
    {"no": "⑩", "name": "体内评价", "desc": "Pan02-Neo 小鼠 + 抗 PD-1 → ELISpot / 流式", "tools": "动物实验", "by_workbench": "不做"},
]

TCGA_GUIDE: dict[str, Any] = {
    "portal": "https://portal.gdc.cancer.gov/",
    "project": "TCGA-PAAD（胰腺腺癌，185 例，含 WES+RNA-Seq）",
    "icgc": "https://dcc.icgc.org/projects/PACA-AU（国际验证队列）",
    "steps": [
        "GDC 门户 → Projects → TCGA-PAAD → Repository",
        "左侧 Filters 勾选 Experimental Strategy: WXS（WES）或 RNA-Seq；Data Category: Raw Sequencing Data",
        "加购（Add to Cart）目标样本 → Cart → Download → 下载 gdc-client_manifest.maf…（实际为 manifest 文件）",
        "命令行批量下载: gdc-client download -m <manifest 文件>",
        "临床与突变注释: Data Category = Clinical / Simple Nucleotide Variation（MAF）",
    ],
    "gdc_client": "https://portal.gdc.cancer.gov/legacy-archive/download-client（gdc-client，Windows/Linux 均有）",
    "note": "工作台「资源中心 → GDC 突变检索」可直接按基因查 TCGA-PAAD 体细胞突变（免下载 WES）。",
}

REF_GUIDE: dict[str, Any] = {
    "assembly": "GRCh38（Ensembl release-113 primary assembly，~3.1GB）",
    "download": "bash /opt/bio/app/pipeline/10_prepare_ref.sh ~/mhc-pipeline/ref",
    "star_index": "WITH_STAR=1 bash /opt/bio/app/pipeline/10_prepare_ref.sh ~/mhc-pipeline/ref",
    "gtf": "https://ftp.ensembl.org/pub/release-113/gtf/homo_sapiens/（表达定量需 GTF 注释，放到 ref/ 目录）",
    "note": "参考基因组一次性准备约 1-2 小时（含 BWA 索引）；磁盘需求约 20GB（含索引）。",
}


def load_inventory() -> dict[str, Any]:
    """读工具清单 JSON；文件缺失时现场探测（shutil.which），保证首次可用。"""
    if INVENTORY_PATH.is_file():
        try:
            data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "tools" in data:
                data["available"] = True
                return data
        except Exception:
            pass
    # 文件缺失 → 快速探测
    quick: dict[str, Any] = {}
    for name, (_step, _cn, ver_cmd, hint) in TOOL_REGISTRY.items():
        binname = ver_cmd[0]
        path = shutil.which(binname)
        quick[name] = {
            "installed": bool(path),
            "version": "",
            "path": path or "",
            "source": "probe",
            "step": _step,
            "note": "" if path else f"未安装（{hint}）",
        }
    return {"tools": quick, "available": False, "updated_at": ""}


def check_tool(tool: str) -> dict[str, Any]:
    """实时检测单个工具（白名单 + 5 秒超时）。"""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", tool or ""):
        return {"ok": False, "error": "非法工具名"}
    reg = TOOL_REGISTRY.get(tool)
    if reg is None:
        return {"ok": False, "error": f"未知工具: {tool}"}
    step, cn, ver_cmd, hint = reg
    path = shutil.which(ver_cmd[0])
    if not path and not ver_cmd[0].startswith("/"):
        return {"ok": True, "tool": tool, "installed": False, "step": step, "note": f"未安装（{hint}）"}
    version = ""
    try:
        cmd = [*ver_cmd]
        if cmd[0] == "bwa":
            cmd = ["sh", "-c", "bwa 2>&1 | head -3"]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)  # noqa: S603
        out = (proc.stdout or "") + (proc.stderr or "")
        for line in out.splitlines():
            line = line.strip()
            if line and "Usage" not in line and "VERSION" not in line.upper():
                version = line[:100]
                break
            if line:
                version = line[:100]
                break
    except subprocess.TimeoutExpired:
        version = "（版本查询超时）"
    except Exception as exc:  # noqa: BLE001
        version = f"（检测异常: {exc}）"
    return {
        "ok": True,
        "tool": tool,
        "installed": True,
        "version": version,
        "path": path or ver_cmd[0],
        "step": step,
    }


def guide() -> dict[str, Any]:
    return {
        "ok": True,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "route_steps": ROUTE_STEPS,
        "pipeline_scripts": PIPELINE_SCRIPTS,
        "pipeline_dir": str(APP_ROOT / "pipeline"),
        "tcga": TCGA_GUIDE,
        "reference": REF_GUIDE,
    }
