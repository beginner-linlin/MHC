#!/usr/bin/env bash
# 70_hla_typing.sh — 设计书第⑤步：OptiType HLA-I 分型（从 WES/RNA BAM 或 FASTQ）
# 用法: bash 70_hla_typing.sh BAM_OR_FASTQ OUT_DIR [--rna]
# 输出: OUT_DIR/*.tsv（OptiType 结果：每个 HLA-A/B/C 等位基因两份拷贝）
set -euo pipefail
source "$(dirname "$0")/_common.sh"

IN="${1:-}"; OUT="${2:-}"; MODE_FLAG="${3:---dna}"
[ -n "$IN" ] && [ -n "$OUT" ] || die "用法: bash 70_hla_typing.sh BAM_OR_FASTQ OUT_DIR [--dna|--rna]"
must_file "$IN"
require_optitype
mkdir -p "$OUT"

log "OptiType 分型（$MODE_FLAG，输入: $IN，约 30-120 分钟取决于数据量）…"
OT_BIN="$(command -v OptiTypePipeline.py)"
OT_DIR="$(dirname "$OTBIN_REAL" 2>/dev/null || dirname "$(readlink -f "$OT_BIN" 2>/dev/null || echo "$OT_BIN")")"

# OptiType 需要配置文件 config.ini（首次使用生成默认）
if [ ! -s "$OT_DIR/config.ini" ]; then
  cat > "$OT_DIR/config.ini" <<'CFG'
[_mapping]
razers3=
bowtie2=bowtie2
[ilp]
solver=cbc
thread=1
[behavior]
delete_unidentified=0
verbose=1
CFG
fi

/opt/bio/tools/optitype-venv/bin/python "$OT_BIN" \
  -i "$IN" -o "$OUT" "$MODE_FLAG" 2>&1 | tee "$OUT/optitype.log" | tail -5

RESULT="$(ls "$OUT"/*.tsv 2>/dev/null | head -1 || true)"
[ -n "$RESULT" ] || die "OptiType 未产出结果 TSV，查看 $OUT/optitype.log"

log "检出等位基因:"
awk -F'\t' 'NR==1{for(i=1;i<=6;i++) if($i ~ /^HLA/) printf "%s ", $i; print ""}' "$RESULT"
log "完成: $RESULT（把其中等位基因填入工作台的 HLA 输入框，格式如 HLA-A*02:01）"