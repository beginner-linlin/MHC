#!/usr/bin/env bash
# _common.sh — 流水线公共函数（被各步骤脚本 source）
# 设计书步骤：通用
MHC_PIPE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/bio/tools/bin:$PATH"
MHC_API="${MHC_API:-http://127.0.0.1:8008}"

log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die()  { printf '[错误] %s\n' "$*" >&2; exit 1; }
must_dir() { [ -d "$1" ] || die "目录不存在: $1（先执行前置步骤）"; mkdir -p "$1"; }
must_file() { [ -s "$1" ] || die "文件不存在或为空: $1"; }

# require_tool <命令名> <安装提示>
require_tool() {
  command -v "$1" >/dev/null 2>&1 && return 0
  die "缺少工具: $1 — 请安装: $2"
}
# 一次性检查常用工具
require_samtools() { require_tool samtools "sudo apt-get install -y samtools"; }
require_bwa()      { require_tool bwa "sudo apt-get install -y bwa"; }
require_gatk()     { require_tool gatk "见《流水线使用指南》GATK4 安装节（或改用 Strelka2）"; }
require_star()     { require_tool STAR "sudo apt-get install -y rna-star"; }
require_rsem()     { require_tool rsem-calculate-expression "sudo apt-get install -y rsem"; }
require_optitype() { require_tool OptiTypePipeline.py "见《流水线使用指南》OptiType 安装节"; }
require_trim() {
  if command -v trimmomatic >/dev/null 2>&1; then TRIMMOATIC_CMD="trimmomatic"; return 0; fi
  if command -v TrimmomaticPE >/dev/null 2>&1; then TRIMMOATIC_CMD="TrimmomaticPE"; return 0; fi
  die "缺少工具: trimmomatic — sudo apt-get install -y trimmomatic"
}
require_annotator() {
  if command -v vep >/dev/null 2>&1; then ANNOTATOR="vep"; return 0; fi
  if command -v snpEff >/dev/null 2>&1; then ANNOTATOR="snpeff"; return 0; fi
  die "缺少注释工具: vep 或 snpEff — sudo apt-get install -y ensembl-vep 或 snpeff"
}
require_caller() {
  if command -v gatk >/dev/null 2>&1; then SOMATIC_CALLER="gatk"; return 0; fi
  if [ -x /opt/bio/tools/bin/configureStrelkaSomaticWorkflow ]; then SOMATIC_CALLER="strelka2"; return 0; fi
  die "缺少突变检出工具: gatk(MuTect2) 或 strelka2 — 见《流水线使用指南》"
}

check_api() {
  curl -s -o /dev/null -w '%{http_code}' "$MHC_API/api/health" 2>/dev/null | grep -q 200 \
    || die "工作台 API 不可达: $MHC_API（先启动 MHC 工作台）"
}
api_post() { curl -s -X POST -H 'Content-Type: application/json' -d "$2" "$MHC_API$1"; }
api_get()  { curl -s "$MHC_API$1"; }

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; }
case "${1:-}" in -h|--help) usage; exit 0;; esac