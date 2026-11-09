#!/usr/bin/env bash
# 40_call_somatic.sh — 设计书第③步：体细胞突变检出（GATK MuTect2 优先，Strelka2 兜底）
# 用法: bash 40_call_somatic.sh REF TUMOR_BAM NORMAL_BAM OUT_DIR
# 输出: OUT_DIR/somatic.vcf.gz（未注释；下一步 50_annotate.sh 处理）
set -euo pipefail
source "$(dirname "$0")/_common.sh"

REF="${1:-}"; TUMOR="${2:-}"; NORMAL="${3:-}"; OUT="${4:-}"
[ -n "$REF" ] && [ -n "$TUMOR" ] && [ -n "$OUT" ] || die "用法: bash 40_call_somatic.sh REF TUMOR_BAM [NORMAL_BAM] OUT_DIR"
must_file "$REF"; must_file "$TUMOR"; [ -z "$NORMAL" ] || must_file "$NORMAL"
mkdir -p "$OUT"
require_caller

TN=$(basename "$TUMOR"); TN="${TN%%.*}"

if [ "$SOMATIC_CALLER" = "gatk" ]; then
  log "GATK MuTect2（tumor: $TUMOR normal: ${NORMAL:-无}）…"
  # gnomAD 胚系资源可选（有则 --germline-resource 减少假阳性）
  GERMLINE=""
  if [ -s "${REF_DIR_GERMLINE:-/nonexistent}" ]; then GERMLINE="--germline-resource $REF_DIR_GERMLINE"; fi
  if [ -n "$NORMAL" ]; then
    gatk --java-options "-Xmx16g" Mutect2 -R "$REF" -I "$TUMOR" -I "$NORMAL" \
      -normal "$(basename "$NORMAL" | cut -d. -f1)" $GERMLINE \
      -O "$OUT/somatic.vcf.gz" > "$OUT/mutect2.log" 2>&1
  else
    gatk --java-options "-Xmx16g" Mutect2 -R "$REF" -I "$TUMOR" $GERMLINE \
      -O "$OUT/somatic.vcf.gz" > "$OUT/mutect2.log" 2>&1
  fi
  must_file "$OUT/somatic.vcf.gz"
  log "MuTect2 完成（含 FilterMutectCalls 前的原始 calls）"
  gatk --java-options "-Xmx8g" FilterMutectCalls -R "$REF" -V "$OUT/somatic.vcf.gz" \
    -O "$OUT/somatic.filtered.vcf.gz" >> "$OUT/mutect2.log" 2>&1 || log "（FilterMutectCalls 失败，用原始 calls 继续）"
  [ -s "$OUT/somatic.filtered.vcf.gz" ] && ln -sf somatic.filtered.vcf.gz "$OUT/somatic.final.vcf.gz" \
    || ln -sf somatic.vcf.gz "$OUT/somatic.final.vcf.gz"

else
  log "Strelka2（tumor: $TUMOR normal: $NORMAL）…"
  [ -n "$NORMAL" ] || die "Strelka2 体细胞检出必须提供 normal BAM"
  CFG="$OUT/strelka_cfg"
  /opt/bio/tools/bin/configureStrelkaSomaticWorkflow \
    --tumorBam "$TUMOR" --normalBam "$NORMAL" --ref "$REF" --config "$CFG" > "$OUT/strelka.log" 2>&1
  "$CFG/runWorkflow.py" -m local -j "$(nproc)" >> "$OUT/strelka.log" 2>&1
  RES="$(dirname "$CFG")/results"
  must_file "$RES/variants/somatic.snvs.vcf.gz"
  # 合并 SNV + indel 为单一 VCF
  bcftools concat -a "$RES/variants/somatic.snvs.vcf.gz" "$RES/variants/somatic.indels.vcf.gz" \
    -O z -o "$OUT/somatic.final.vcf.gz"
  tabix -f -p vcf "$OUT/somatic.final.vcf.gz" 2>/dev/null || bcftools index -f "$OUT/somatic.final.vcf.gz"
fi

log "突变数: $(bcftools view -H "$OUT/somatic.final.vcf.gz" 2>/dev/null | wc -l)"
log "完成: $OUT/somatic.final.vcf.gz（下一步: 50_annotate.sh）"