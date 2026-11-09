#!/usr/bin/env bash
# 10_prepare_ref.sh — 设计书第②步前置：准备 GRCh38 参考基因组并建索引
# 用法: bash 10_prepare_ref.sh [REF_DIR]        （默认 ~/mhc-pipeline/ref）
# 输入: 无（自动下载 Ensembl GRCh38 primary assembly）
# 输出: REF_DIR/genome.fa + genome.fa.fai + BWA 索引 + STAR 索引（可选 --with-star）
set -euo pipefail
source "$(dirname "$0")/_common.sh"

REF_DIR="${1:-$HOME/mhc-pipeline/ref}"
WITH_STAR="${WITH_STAR:-0}"
GENOME_URL="https://ftp.ensembl.org/pub/release-113/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"
GENOME_URL_ALT="https://mirror.ghproxy.com/https://ftp.ensembl.org/pub/release-113/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz"

mkdir -p "$REF_DIR"
FA="$REF_DIR/genome.fa"

if [ -s "$FA" ] && [ -s "$FA.fai" ]; then
  log "参考基因组已存在: $FA（跳过下载）"
else
  log "下载 GRCh38 primary assembly（约 3.3GB，解压后 ~3.1GB）…"
  cd "$REF_DIR"
  wget -c --tries=5 --timeout=60 -q "$GENOME_URL" || wget -c --tries=5 --timeout=60 -q "$GENOME_URL_ALT"
  must_file Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz
  log "解压…"
  gunzip -kf Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz
  mv Homo_sapiens.GRCh38.dna.primary_assembly.fa genome.fa
fi

must_file "$FA"
log "samtools faidx…"
require_samtools
samtools faidx "$FA"

if [ ! -s "$FA.bwt" ]; then
  log "bwa index（约 20-40 分钟）…"
  require_bwa
  bwa index "$FA"
else
  log "BWA 索引已存在，跳过"
fi

# GATK sequence dictionary（有 gatk 就建）
if command -v gatk >/dev/null 2>&1 && [ ! -s "${FA%.fa}.dict" ]; then
  log "gatk CreateSequenceDictionary…"
  gatk CreateSequenceDictionary -R "$FA" || log "（gatk 建字典失败，MuTect2 时需补建）"
fi

if [ "$WITH_STAR" = "1" ]; then
  require_star
  if [ ! -s "$REF_DIR/star_index/Genome" ]; then
    log "建 STAR 索引（需约 32GB 内存，请确认机器配置）…"
    mkdir -p "$REF_DIR/star_index"
    STAR --runMode genomeGenerate --runThreadN "$(nproc)" \
      --genomeDir "$REF_DIR/star_index" --genomeFastaFiles "$FA" \
      --sjdbOverhang 100
  else
    log "STAR 索引已存在，跳过"
  fi
else
  log "如需表达定量，运行: WITH_STAR=1 bash $0 $REF_DIR（建 STAR 索引）"
fi

log "完成: $FA"
ls -lh "$REF_DIR" | head -20