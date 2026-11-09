#!/usr/bin/env bash
# 90_neoantigen.sh — 设计书第⑥步：把突变清单交给工作台跑新抗原预测
# 用法: bash 90_neoantigen.sh MUT_JSON PROTEINS_FASTA OUT_DIR --alleles "HLA-A*02:01,HLA-A*11:01" [--lengths 8,9,10,11]
#   MUT_JSON        80 步输出的 neoantigen.json
#   PROTEINS_FASTA  80 步输出的 proteins.fasta
#   OUT_DIR         结果目录（汇总 TSV + CSV 导出下载）
# 前置: 工作台已启动（默认 http://127.0.0.1:8008，可用 MHC_API 环境变量改）
set -euo pipefail
source "$(dirname "$0")/_common.sh"

MUT="${1:-}"; FASTA="${2:-}"; OUT="${3:-}"; shift 3 || true
[ -n "$MUT" ] && [ -n "$FASTA" ] && [ -n "$OUT" ] || die "用法: bash 90_neoantigen.sh MUT_JSON PROTEINS_FASTA OUT_DIR --alleles HLA-A*02:01,..."
must_file "$MUT"; must_file "$FASTA"
check_api
command -v python3 >/dev/null 2>&1 || die "缺少 python3"

# 解析 --alleles / --lengths
ALLELES=""; LENGTHS="8,9,10,11"
while [ $# -gt 0 ]; do
  case "$1" in
    --alleles) ALLELES="${2:-}"; shift 2 ;;
    --lengths) LENGTHS="${2:-8,9,10,11}"; shift 2 ;;
    *) die "未知参数: $1" ;;
  esac
done
[ -n "$ALLELES" ] || die "必须用 --alleles 提供至少一个 HLA 等位基因，如 --alleles \"HLA-A*02:01,HLA-B*07:02\""
mkdir -p "$OUT"

log "组装提交载荷…"
python3 - "$MUT" "$FASTA" "$OUT/payload.json" "$ALLELES" "$LENGTHS" <<'PYEOF'
import json, sys
mut = json.load(open(sys.argv[1]))
fasta, outp, alleles, lengths = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
seqs, name, buf = {}, None, []
for line in open(fasta):
    if line.startswith(">"):
        if name: seqs[name] = "".join(buf)
        name, buf = line[1:].strip().split()[0], []
    else:
        buf.append(line.strip())
if name: seqs[name] = "".join(buf)
input_fa = "".join(f">{g}\n{s}\n" for g, s in seqs.items())
payload = {
    "input": input_fa,
    "mutations": mut.get("mutations", []),
    "alleles": [a.strip() for a in alleles.split(",") if a.strip()],
    "peptide_lengths": [int(x) for x in lengths.split(",")],
    "nonstandard_action": "mark",
}
json.dump(payload, open(outp, "w"), ensure_ascii=False)
print(f"[90] 载荷: {len(seqs)} 蛋白 / {len(payload['mutations'])} 突变 / {len(payload['alleles'])} 等位 / 肽长 {payload['peptide_lengths']}")
PYEOF

log "提交工作台 /api/jobs/mutant …"
RESP="$(api_post /api/jobs/mutant "$(cat "$OUT/payload.json")")"
JOB_ID="$(echo "$RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('job_id') or (d.get('job') or {}).get('id') or '')" 2>/dev/null || true)"
[ -n "$JOB_ID" ] || die "提交失败，响应: $(echo "$RESP" | head -c 300)"

log "任务 ID: $JOB_ID，轮询中…"
STATUS=""
for i in $(seq 1 240); do
  sleep 5
  ST="$(api_get "/api/jobs/$JOB_ID")"
  STATUS="$(echo "$ST" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print((d.get('job') or d).get('status') or '')" 2>/dev/null || echo '?')"
  case "$STATUS" in
    done) break ;;
    failed)
      MSG="$(echo "$ST" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print((d.get('job') or d).get('error') or '')" 2>/dev/null || echo '?')"
      die "任务失败: $MSG" ;;
    running|pending) [ $((i % 12)) -eq 0 ] && log "  …进行中 ${i}x5s" ;;
    *) [ $((i % 24)) -eq 0 ] && log "  状态=$STATUS" ;;
  esac
done
[ "$STATUS" = "done" ] || die "任务超时（20 分钟）未完成，可手动查看工作台历史: job_id=$JOB_ID"

echo "$ST" > "$OUT/result.json"
log "导出汇总…"
python3 - "$OUT/result.json" "$OUT/neoantigen_summary.tsv" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1]))
job = r.get("job") or {}
rows = (job.get("result") or {}).get("rows") or r.get("rows") or r.get("result", {}).get("rows") or []
cols = ["peptide", "protein", "allele", "Score_EL", "%Rank_EL", "Aff(nM)", "BindLevel", "mutation", "pos"]
with open(sys.argv[2], "w") as fh:
    fh.write("\t".join(c for c in cols) + "\n")
    for x in rows:
        fh.write("\t".join(str(x.get(c, "")) for c in cols) + "\n")
print(f"[90] 结果 {len(rows)} 行候选肽")
for x in rows[:10]:
    print("   ", x.get("peptide"), x.get("protein"), x.get("allele"), x.get("BindLevel", ""))
PYEOF

log "下载完整 CSV…"
api_get "/api/jobs/$JOB_ID/export?format=csv" > "$OUT/neoantigen_full.csv" || true
log "完成。产物:"
echo "  $OUT/neoantigen_summary.tsv  — 汇总表"
echo "  $OUT/neoantigen_full.csv     — 完整导出（可打开工作台历史继续分析）"
echo "  $OUT/result.json             — 原始 JSON"