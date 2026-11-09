#!/usr/bin/env bash
# 30_align.sh — 设计书第②步：BWA-MEM 比对到 GRCh38 + 排序 + 标记重复
# 用法: bash 30_align.sh REF_FASTA FASTQ_R1 FASTQ_R2 OUT_PREFIX
# 输出: OUT_PREFIX.sorted.mkdup.bam + .bai（供 40/60/70 步使用）
set -euo pipefail
source "$(dirname "$0")/_common.sh"

REF="${1:-}"; R1="${2:-}"; R2="${3:-}"; OUTP="${4:-}"
[ -n "$REF" ] && [ -n "$R1" ] && [ -n "$OUTP" ] || die "用法: bash 30_align.sh REF FASTQ_R1 FASTQ_R2 OUT_PREFIX"
must_file "$REF"; must_file "$R1"; must_file "$R2"
require_bwa; require_samtools

mkdir -p "$(dirname "$OUTP")"
THREADS="$(nproc)"
TMP="$(mktemp -d /tmp/align.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

log "bwa mem 比对（$THREADS 线程）…"
bwa mem -t "$THREADS" -R "@RG\tID:${OUTP##*/}\tSM:${OUTP##*/}\tPL:ILLUMINA" \
  "$REF" "$R1" "$R2" 2> "$TMP/bwa.log" | samtools sort -@ "$THREADS" -o "$OUTP.sorted.bam" -
must_file "$OUTP.sorted.bam"

log "标记重复…"
if command -v gatk >/dev/null 2>&1; then
  gatk --java-options "-Xmx8g" MarkDuplicates -I "$OUTP.sorted.bam" \
    -O "$OUTP.sorted.mkdup.bam" -M "$OUTP.mkdup_metrics.txt" --CREATE_INDEX true >/dev/null
else
  samtools markdup -@ "$THREADS" "$OUTP.sorted.bam" "$OUTP.sorted.mkdup.bam"
  samtools index "$OUTP.sorted.mkdup.bam"
fi
rm -f "$OUTP.sorted.bam"   # 保留空间，mkdup 版已含全部信息

log "比对统计:"
samtools flagstat "$OUTP.sorted.mkdup.bam" | head -8
log "完成: $OUTP.sorted.mkdup.bam"