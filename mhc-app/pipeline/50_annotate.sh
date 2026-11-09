#!/usr/bin/env bash
# 50_annotate.sh — 设计书第③步：突变功能注释（VEP 优先，snpEff 兜底）
# 用法: bash 50_annotate.sh SOMATIC_VCF OUT_VCF
# 输出: OUT_VCF（带 ANN/CSQ 注释，含 missense_variant 标记；供 80 步提取突变肽段）
set -euo pipefail
source "$(dirname "$0")/_common.sh"

IN="${1:-}"; OUTV="${2:-}"
[ -n "$IN" ] && [ -n "$OUTV" ] || die "用法: bash 50_annotate.sh SOMATIC_VCF OUT_VCF"
must_file "$IN"
require_annotator
mkdir -p "$(dirname "$OUTV")"

# 确保索引存在
[ -s "$IN.tbi" ] || tabix -f -p vcf "$IN" 2>/dev/null || bcftools index -f "$IN" || true

if [ "$ANNOTATOR" = "vep" ]; then
  log "VEP 注释…"
  # cache 模式优先（需先 vep_install 下载缓存），否则 database 模式在线注释
  if [ -d "$HOME/.vep" ] && ls "$HOME"/.vep/*/info.txt >/dev/null 2>&1; then
    vep -i "$IN" -o "$OUTV" --vcf --cache --assembly GRCh38 --everything \
      --force_overwrite --offline --symbol --numbers --hgvs
  else
    log "（未找到 VEP 本地缓存，用在线 database 模式；大批量样本建议先装缓存）"
    vep -i "$IN" -o "$OUTV" --vcf --assembly GRCh38 --everything \
      --force_overwrite --database --symbol --numbers
  fi
else
  log "snpEff 注释（GRCh38.105 数据库，首次运行会自动下载 ~200MB）…"
  snpEff -download GRCh38.105 "$IN" > "$OUTV" 2> "${OUTV%.vcf}.snpeff.log" \
    || die "snpEff 注释失败，日志: ${OUTV%.vcf}.snpeff.log"
fi

must_file "$OUTV"
log "错义突变数: $(bcftools view -H "$OUTV" | grep -c 'missense_variant' || echo 0)"
log "完成: $OUTV（下一步: 80_extract_mutations.sh）"