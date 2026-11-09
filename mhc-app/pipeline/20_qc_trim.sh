#!/usr/bin/env bash
# 20_qc_trim.sh — 设计书第②步：FastQC 质控 + Trimmomatic 剪接
# 用法: bash 20_qc_trim.sh FASTQ_R1 FASTQ_R2 OUT_DIR   （双端测序；单端传 R2 为空串）
# 输出: OUT_DIR/fastqc_raw/ fastqc_trimmed/  OUT_DIR/*_trimmed.fastq.gz
set -euo pipefail
source "$(dirname "$0")/_common.sh"

R1="${1:-}"; R2="${2:-}"; OUT="${3:-}"
[ -n "$R1" ] && [ -n "$OUT" ] || die "用法: bash 20_qc_trim.sh FASTQ_R1 [FASTQ_R2] OUT_DIR"
must_file "$R1"; [ -z "$R2" ] || must_file "$R2"
mkdir -p "$OUT/fastqc_raw" "$OUT/fastqc_trimmed"

require_tool fastqc "sudo apt-get install -y fastqc"
require_trim

ADAPTERS="$(dirname "$(command -v TrimmomaticPE 2>/dev/null || command -v trimmomatic)")/../share/trimmomatic/adapters"
[ -d "$ADAPTERS" ] || ADAPTERS="/usr/share/trimmomatic/adapters"
log "适配器目录: $ADAPTERS"

log "FastQC 原始数据…"
fastqc -q -t "$(nproc)" -o "$OUT/fastqc_raw" "$R1" ${R2:+"$R2"}

BASE="$(basename "$R1")"; BASE="${BASE%%.*}"
log "Trimmomatic 剪接（$TRIMMOATIC_CMD）…"
if [ -n "$R2" ]; then
  if [ "$TRIMMOATIC_CMD" = "TrimmomaticPE" ]; then
    TrimmomaticPE -threads "$(nproc)" "$R1" "$R2" \
      "$OUT/${BASE}_R1_trimmed.fastq.gz" "$OUT/${BASE}_R1_unpaired.fastq.gz" \
      "$OUT/${BASE}_R2_trimmed.fastq.gz" "$OUT/${BASE}_R2_unpaired.fastq.gz" \
      "ILLUMINACLIP:$ADAPTERS/TruSeq3-PE.fa:2:30:10 LEADING:3 TRAILING:3 SLIDINGWINDOW:4:15 MINLEN:36"
  else
    trimmomatic PE -threads "$(nproc)" "$R1" "$R2" \
      "$OUT/${BASE}_R1_trimmed.fastq.gz" "$OUT/${BASE}_R1_unpaired.fastq.gz" \
      "$OUT/${BASE}_R2_trimmed.fastq.gz" "$OUT/${BASE}_R2_unpaired.fastq.gz" \
      "ILLUMINACLIP:$ADAPTERS/TruSeq3-PE.fa:2:30:10 LEADING:3 TRAILING:3 SLIDINGWINDOW:4:15 MINLEN:36"
  fi
  T1="$OUT/${BASE}_R1_trimmed.fastq.gz"; T2="$OUT/${BASE}_R2_trimmed.fastq.gz"
else
  TrimmomaticSE -threads "$(nproc)" "$R1" "$OUT/${BASE}_trimmed.fastq.gz" \
    "ILLUMINACLIP:$ADAPTERS/TruSeq3-SE.fa:2:30:10 LEADING:3 TRAILING:3 SLIDINGWINDOW:4:15 MINLEN:36"
  T1="$OUT/${BASE}_trimmed.fastq.gz"; T2=""
fi

log "FastQC 剪接后数据…"
fastqc -q -t "$(nproc)" -o "$OUT/fastqc_trimmed" "$T1" ${T2:+"$T2"}

log "完成。剪接后文件:"
echo "  R1: $T1"; [ -z "$T2" ] || echo "  R2: $T2"