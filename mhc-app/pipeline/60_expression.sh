#!/usr/bin/env bash
# 60_expression.sh — 设计书第④步：STAR 比对 + RSEM 转录本定量（TPM）
# 用法: bash 60_expression.sh REF FASTQ_R1 FASTQ_R2 OUT_DIR
# 前置: bash 10_prepare_ref.sh REF_DIR 后需建 STAR 索引（WITH_STAR=1）并下载 GTF 注释
# 输出: OUT_DIR/rsem/*.isoform.TPM 等定量表
set -euo pipefail
source "$(dirname "$0")/_common.sh"

REF="${1:-}"; R1="${2:-}"; R2="${3:-}"; OUT="${4:-}"
[ -n "$REF" ] && [ -n "$R1" ] && [ -n "$R2" ] && [ -n "$OUT" ] || die "用法: bash 60_expression.sh REF FASTQ_R1 FASTQ_R2 OUT_DIR"
must_file "$REF"; must_file "$R1"; must_file "$R2"
require_star; require_rsem

STAR_IDX="${REF%/*}/star_index"
GTF="${REF%/*}/Homo_sapiens.GRCh38.113.gtf.gz"
[ -d "$STAR_IDX" ] || die "STAR 索引不存在: $STAR_IDX（WITH_STAR=1 bash 10_prepare_ref.sh $(dirname "$REF")）"
[ -s "$GTF" ] || GTF="${REF%/*}/Homo_sapiens.GRCh38.113.gtf"
[ -s "$GTF" ] || die "缺少 GTF 注释文件（从 Ensembl 下载 Homo_sapiens.GRCh38.N.gtf.gz 放到 $(dirname "$REF")）"

mkdir -p "$OUT/star" "$OUT/rsem"
THREADS="$(nproc)"

# RSEM 需要自己的参考（transcript 序列，从 genome+GTF 提取，或直接用 rsem-prepare-reference）
RSEM_REF="$OUT/rsem_ref"
if [ ! -s "$RSEM_REF/seq" ]; then
  log "rsem-prepare-reference（一次性，约 30-60 分钟）…"
  [ -s "$GTF" ] && gunzip -kf "$GTF" 2>/dev/null || true
  GTFU="${GTF%.gz}"
  rsem-prepare-reference --gtf "$GTFU" --num-threads "$THREADS" "$REF" "$RSEM_REF" \
    > "$OUT/rsem_prepare.log" 2>&1
fi

log "STAR 第一遍比对（--quantMode TranscriptomeSAM 出 transcript BAM）…"
STAR --genomeDir "$STAR_IDX" --readFilesIn "$R1" "$R2" \
  --readFilesCommand zcat --runThreadN "$THREADS" --outFileNamePrefix "$OUT/star/" \
  --quantMode TranscriptomeSAM GeneCounts --outSAMtype BAM SortedByCoordinate \
  > "$OUT/star/run.log" 2>&1

log "RSEM 定量（paired-end）…"
rsem-calculate-expression --paired-end --num-threads "$THREADS" \
  "$OUT/star/Aligned.toTranscriptome.out.bam" "$RSEM_REF" "$OUT/rsem/gene" \
  > "$OUT/rsem_run.log" 2>&1

must_file "$OUT/rsem/gene.isoform.results"
log "TPM Top 10（转录本水平）:"
head -1 "$OUT/rsem/gene.isoform.results"
sort -k6,6gr "$OUT/rsem/gene.isoform.results" 2>/dev/null | head -10 || head -10 "$OUT/rsem/gene.isoform.results"
log "完成: $OUT/rsem/（gene.isoform.results 第 6 列 = TPM；供第⑥步多维特征）"