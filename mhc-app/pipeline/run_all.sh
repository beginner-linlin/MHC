#!/usr/bin/env bash
# run_all.sh — 设计书①→⑥流程总控（串联 10→90 各步骤脚本）
# 用法:
#   bash run_all.sh --fastq R1 R2 --normal-fastq N1 N2 --alleles "HLA-A*02:01,..." [选项]
# 常用选项:
#   --ref DIR          参考基因组目录（默认 ~/mhc-pipeline/ref，无索引会先跑 10_prepare_ref）
#   --start N --stop N 只跑第 N..M 步（默认 1..8，对应脚本 10..90）
#   --dry-run          只打印将执行的命令
#   --force            忽略已完成检查点强制重跑
#   --work DIR         每个患者的工作目录（默认 ~/mhc-pipeline/patient1）
#   --with-star        第 1 步同时建 STAR 索引（表达定量用）
# 步骤映射: 1=10参考 2=20质控 3=30比对 4=40突变 5=50注释 6=60定量 7=70HLA 8=80提取 9=90预测
set -euo pipefail
source "$(dirname "$0")/_common.sh"

R1=""; R2=""; N1=""; N2=""; ALLELES=""; REF="$HOME/mhc-pipeline/ref"; WORK="$HOME/mhc-pipeline/patient1"; EXT_VCF=""
START=1; STOP=9; DRYRUN=0; FORCE=0; WITH_STAR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --fastq) R1="$2"; R2="$3"; shift 3 ;;
    --normal-fastq) N1="$2"; N2="$3"; shift 3 ;;
    --alleles) ALLELES="$2"; shift 2 ;;
    --ref) REF="$2"; shift 2 ;;
    --work) WORK="$2"; shift 2 ;;
    --start) START="$2"; shift 2 ;;
    --stop) STOP="$2"; shift 2 ;;
    --vcf) EXT_VCF="$2"; shift 2 ;;
    --maf) EXT_VCF="$2"; shift 2 ;;
    --with-star) WITH_STAR=1; shift ;;
    --dry-run) DRYRUN=1; shift ;;
    --force) FORCE=1; shift ;;
    *) die "未知参数: $1（-h 看用法）" ;;
  esac
done
[ -n "$EXT_VCF" ] || [ -n "$R1" ] || die "必须提供肿瘤 FASTQ: --fastq R1 R2，或已注释 VCF/MAF: --vcf/--maf PATH"
if [ -n "$EXT_VCF" ]; then
  must_file "$EXT_VCF"
  [ "$START" -lt 8 ] && START=8
  log "外部注释 VCF/MAF 模式: 跳过 ②-⑦，从第 8 步起跑（$EXT_VCF）"
fi
mkdir -p "$WORK"

run_step() {
  local n="$1" script="$2"; shift 2
  local donef="$WORK/.done_step$n"
  if [ "$FORCE" = "0" ] && [ -f "$donef" ]; then log "== 步骤 $n 已完成，跳过（--force 重跑）"; return 0; fi
  if [ "$n" -lt "$START" ] || [ "$n" -gt "$STOP" ]; then log "== 步骤 $n 不在 $START..$STOP 范围，跳过"; return 0; fi
  log "== 步骤 $n: $(basename "$script") =="
  if [ "$DRYRUN" = "1" ]; then
    echo "  bash $MHC_PIPE_ROOT/$script $*"
  else
    bash "$MHC_PIPE_ROOT/$script" "$@"
    touch "$donef"
  fi
}

if [ -n "$EXT_VCF" ]; then
  # 外部 VCF/MAF：①-⑦ 全跳（无需参考基因组），直达第 8 步
  log "== 外部注释 VCF/MAF 模式: 跳过 ①-⑦ =="
  for n in 1 2 3 4 5 6 7; do touch "$WORK/.skip_step$n"; done
  run_step 8 80_extract_mutations.sh "$EXT_VCF" "$WORK/neoantigen"
else
# 1 参考基因组
run_step 1 10_prepare_ref.sh "$REF" $([ "$WITH_STAR" = "1" ] && echo "WITH_STAR=1")
# 2 质控剪接
run_step 2 20_qc_trim.sh "$R1" "$R2" "$WORK/qc"
# 3 比对（肿瘤）
B1="$(ls "$WORK"/qc/*_R1_trimmed.fastq.gz 2>/dev/null | head -1)"
B2="$(ls "$WORK"/qc/*_R2_trimmed.fastq.gz 2>/dev/null | head -1)"
[ -n "$B1" ] || die "第 2 步未产出剪接后 FASTQ"
run_step 3 30_align.sh "$REF/genome.fa" "$B1" "$B2" "$WORK/align/tumor"
# 4 突变检出
if [ -n "$N1" ]; then
  log "== 步骤 3b: normal 比对 =="
  NB1="$WORK/qc_normal/N1_trimmed.fastq.gz"; NB2="$WORK/qc_normal/N2_trimmed.fastq.gz"
  if [ "$DRYRUN" = "0" ]; then
    mkdir -p "$WORK/qc_normal"
    bash "$MHC_PIPE_ROOT/20_qc_trim.sh" "$N1" "$N2" "$WORK/qc_normal"
    nb1="$(ls "$WORK"/qc_normal/*_R1_trimmed.fastq.gz | head -1)"; nb2="$(ls "$WORK"/qc_normal/*_R2_trimmed.fastq.gz | head -1)"
    bash "$MHC_PIPE_ROOT/30_align.sh" "$REF/genome.fa" "$nb1" "$nb2" "$WORK/align/normal"
  else
    echo "  20+30 (normal)"
  fi
  run_step 4 40_call_somatic.sh "$REF/genome.fa" "$WORK/align/tumor.sorted.mkdup.bam" "$WORK/align/normal.sorted.mkdup.bam" "$WORK/variants"
else
  log "== 步骤 4: 无 normal，仅肿瘤模式 =="
  run_step 4 40_call_somatic.sh "$REF/genome.fa" "$WORK/align/tumor.sorted.mkdup.bam" "" "$WORK/variants"
fi
# 5 注释
run_step 5 50_annotate.sh "$WORK/variants/somatic.final.vcf.gz" "$WORK/variants/annotated.vcf"
# 6 表达定量（可选但设计书要求）
run_step 6 60_expression.sh "$REF/genome.fa" "$B1" "$B2" "$WORK/expression"
# 7 HLA 分型（可选；也可手动提供等位基因）
run_step 7 70_hla_typing.sh "$WORK/align/tumor.sorted.mkdup.bam" "$WORK/hla" --dna
# 8 提取突变肽段
run_step 8 80_extract_mutations.sh "$WORK/variants/annotated.vcf" "$WORK/neoantigen"
fi
# 9 工作台预测（等位基因: 显式提供 > OptiType 分型结果 > 报错）
if [ "$STOP" = "9" ] && [ -z "$ALLELES" ]; then
  HLA_TSV="$(ls "$WORK"/hla/*.tsv 2>/dev/null | head -1 || true)"
  [ -n "$HLA_TSV" ] || die "缺等位基因: 用 --alleles 指定（如 HLA-A*02:01），或先跑第 7 步让 OptiType 自动分型"
  ALLELES="$(awk -F'\t' 'NR==1{o="";for(i=1;i<=6;i++) if($i ~ /^HLA/){o=(o==""?$i:o","$i)} print o; exit}' "$HLA_TSV")"
  printf '%s\n' "$ALLELES" > "$WORK/hla/alleles.txt"
  log "等位基因来自 OptiType 分型: $ALLELES"
fi
if [ -s "$WORK/neoantigen/proteins.fasta" ]; then
  run_step 9 90_neoantigen.sh "$WORK/neoantigen/neoantigen.json" "$WORK/neoantigen/proteins.fasta" "$WORK/neoantigen" --alleles "$ALLELES"
else
  log "第 8 步提取到 0 个可用突变，跳过第 9 步预测（无候选新抗原）"
  touch "$WORK/.done_step9"
fi

log "全部完成。患者目录: $WORK"
[ "$DRYRUN" = "0" ] && ls "$WORK"