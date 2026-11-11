"""pipeweb.py — 流水线运行器（后台跑 run_all.sh，状态被动读文件）。

运行目录: /opt/bio/app/data/pipeline_runs/<run_id>/
  meta.json  参数与状态
  log.txt    run_all.sh 的合并 stdout/stderr
  wrapper.sh 实际启动的包装脚本（manifest 模式先 gdc-client 下载）

状态判定（无后台线程，status 每次被动读）:
  work/.done_stepN 存在 → 该步 done
  log 尾部最近一次 "== 步骤 N:" 且进程活着 → 该步 running
  进程退出 exit_code != 0 → 最近步骤 failed
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

RUNS_DIR = Path("/opt/bio/app/data/pipeline_runs")
UPLOAD_DIR = Path("/opt/bio/app/data/uploads")
# run_id -> Popen，保活退出码收割（同进程生命周期内有效）
_PROCS: dict[str, "subprocess.Popen"] = {}
RUN_ALL = Path("/opt/bio/app/pipeline/run_all.sh")
RUN_WRAPPER = RUNS_DIR / "_run_wrapper.sh"

STEPS: list[tuple[int, str, str]] = [
    (1, "参考基因组", "10_prepare_ref.sh"),
    (2, "质控剪接", "20_qc_trim.sh"),
    (3, "序列比对", "30_align.sh"),
    (4, "突变检出", "40_call_somatic.sh"),
    (5, "功能注释", "50_annotate.sh"),
    (6, "表达定量", "60_expression.sh"),
    (7, "HLA 分型", "70_hla_typing.sh"),
    (8, "提取突变肽", "80_extract_mutations.sh"),
    (9, "工作台预测", "90_neoantigen.sh"),
]


def _run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def _new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + "".join(
        random.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(4))


def _wsl_path(p: str) -> str:
    """把 /mnt/c/... 或 ~/... 原样透传；只做基础整洁化。"""
    return (p or "").strip()


# gdc-client 候选路径（Flask 进程 PATH 不含 /opt/bio/tools/bin，which 会漏）
_GDC_CANDIDATES = (
    "/opt/bio/tools/bin/gdc-client",
    "/opt/bio/tools/gdc-client-venv/bin/gdc-client",
)


def _find_gdc_client() -> str:
    p = shutil.which("gdc-client")
    if p:
        return p
    for c in _GDC_CANDIDATES:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return ""


def _validate(spec: dict) -> tuple[str, list[str], dict]:
    """返回 (mode, cmd_args, meta_extra)。非法直接抛 ValueError。"""
    mode = (spec.get("mode") or "fastq").strip().lower()
    work = _wsl_path(spec.get("work") or "~/mhc-pipeline/patient1")
    alleles = (spec.get("alleles") or "").strip()
    base = ["--work", work]

    if mode == "fastq":
        r1, r2 = _wsl_path(spec.get("tumor_r1")), _wsl_path(spec.get("tumor_r2"))
        if not r1 or not r2:
            raise ValueError("FASTQ 模式需要肿瘤双端文件: tumor_r1 / tumor_r2")
        base += ["--fastq", r1, r2]
        n1, n2 = _wsl_path(spec.get("normal_r1")), _wsl_path(spec.get("normal_r2"))
        if n1 and n2:
            base += ["--normal-fastq", n1, n2]
        elif n1 or n2:
            raise ValueError("正常对照需同时提供 N1/N2 两个文件")
        if alleles:
            base += ["--alleles", alleles]
        if (spec.get("with_star") or "").strip() in ("1", "true", "on"):
            base += ["--with-star"]
        return mode, base, {}

    if mode in ("manifest", "gdc"):
        mf = _wsl_path(spec.get("manifest"))
        if not mf:
            raise ValueError("manifest 模式需要 GDC manifest 文件路径")
        gdc = _find_gdc_client()
        extra = {"manifest": mf, "gdc_client": bool(gdc)}
        return mode, base, extra  # args 由 wrapper 拼

    if mode in ("mafvcf", "maf", "vcf"):
        mv = _wsl_path(spec.get("maf_vcf"))
        if not mv:
            raise ValueError("MAF/VCF 模式需要已注释文件路径: maf_vcf")
        if not alleles:
            raise ValueError("MAF/VCF 模式跳过了 OptiType，请提供等位基因（逗号分隔，如 HLA-A*02:01）")
        return mode, base + ["--maf", mv, "--alleles", alleles], {}

    raise ValueError(f"未知模式: {mode}（fastq / manifest / mafvcf）")


_WRAPPER = r"""#!/usr/bin/env bash
# 自动生成的流水线包装脚本（不要手改）
set -uo pipefail
RUN_DIR="$1"; WORK="$2"; MODE="$3"; MANIFEST="$4"; GDC_BIN="$5"
LOG="$RUN_DIR/log.txt"
shift 5
cd /tmp
{
  echo "[$(date '+%F %T')] 流水线启动 mode=$MODE work=$WORK"
  if [ "$MODE" = "manifest" ]; then
    if [ -z "$GDC_BIN" ]; then
      echo "BLOCKED_GDC: 未安装 gdc-client，无法自动下载 manifest"
      echo "__EXIT__1"
      exit 1
    fi
    RAW="$WORK/raw"
    mkdir -p "$RAW"
    # 校验 manifest：GDC 官方 manifest 是 TSV，必须有 id 列
    if ! head -1 "$MANIFEST" | grep -qiE '(^|[\t,])id([\t,]|$)'; then
      echo "ERROR_MANIFEST: 该文件不是 GDC 官方下载 manifest（表头缺 id 列）"
      echo "  → 「GDC 突变检索」导出的 CSV 请改用「已注释 MAF-VCF（跳上游）」模式：第 8 步可直接解析"
      echo "  → 官方下载 manifest 从 GDC 官网 Cart 下载，文件名形如 gdc_manifest_*.txt"
      echo "__EXIT__2"
      exit 2
    fi
    echo "== gdc-client 下载 manifest → $RAW =="
    "$GDC_BIN" download -d "$RAW" -n 4 -m "$MANIFEST"
    rc=$?
    echo "__GDC_RC__$rc"
    if [ $rc -ne 0 ]; then
      echo "gdc-client 下载失败（exit=$rc），终止"
      echo "__EXIT__$rc"
      exit $rc
    fi
    # 下载到的 FASTQ 若成对则直接续跑
    R1="$(find "$RAW" -name '*.fastq.gz' 2>/dev/null | grep -iE 'R1|_1\.|tumor|T__' | head -1)"
    R2="$(find "$RAW" -name '*.fastq.gz' 2>/dev/null | grep -iE 'R2|_2\.' | head -1)"
    if [ -n "$R1" ] && [ -n "$R2" ]; then
      echo "== 检出 FASTQ 对，续跑 run_all =="
      exec bash /opt/bio/app/pipeline/run_all.sh --fastq "$R1" "$R2" "$@"
    fi
    echo "NOTE: manifest 下载完成但未找到成对 FASTQ（TCGA WES 常为 BAM，需 samtools fastq 转换后再以 FASTQ 模式启动）"
    ls -la "$RAW" || true
    echo "__EXIT__0"
    exit 0
  fi
  exec bash /opt/bio/app/pipeline/run_all.sh "$@"
}
"""


def start(spec: dict) -> dict:
    mode, args, extra = _validate(spec)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_id = _new_run_id()
    rd = _run_dir(run_id)
    rd.mkdir(parents=True)

    work = (spec.get("work") or "~/mhc-pipeline/patient1").strip()
    gdc_bin = _find_gdc_client()

    if mode == "manifest":
        wrapper = rd / "wrapper.sh"
        wrapper.write_text(_WRAPPER, encoding="utf-8")
        cmd = ["bash", str(wrapper), str(rd), work, "manifest",
               extra.get("manifest", ""), gdc_bin] + args
        # alleles 透传给 wrapper 末尾（run_all 的 "$@"）
    else:
        cmd = ["bash", str(RUN_ALL)] + args

    log_f = (rd / "log.txt").open("wb")
    proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    log_f.close()
    # 保留 Popen 引用以便事后收割退出码（否则对象被 GC，退出码永远拿不到）
    _PROCS[run_id] = proc

    meta = {
        "run_id": run_id, "mode": mode, "state": "running",
        "started": time.strftime("%F %T"), "pid": proc.pid,
        "exit_code": None, "work": work, "params": {k: v for k, v in spec.items()},
        **extra,
    }
    (rd / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return meta


def _proc_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        cmd = Path(f"/proc/{pid}/cmdline")
        txt = cmd.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        return ("run_all.sh" in txt) or ("wrapper.sh" in txt)
    except Exception:
        return False


def _log_tail(rd: Path, n: int = 12) -> list[str]:
    log = rd / "log.txt"
    if not log.exists():
        return []
    try:
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    return lines[-n:]


def _steps_state(rd: Path, meta: dict) -> list[dict]:
    work = Path(os.path.expanduser(meta.get("work") or "~/mhc-pipeline/patient1"))
    alive = _proc_alive(meta.get("pid"))
    state = meta.get("state") or "running"
    exit_code = meta.get("exit_code")

    # 最近一次步骤 banner
    cur_no = 0
    try:
        for line in (rd / "log.txt").read_text(encoding="utf-8", errors="replace").splitlines()[-400:]:
            import re
            m = re.search(r"==\s*(?:gdc-client|步骤)\s*(\d+)", line)
            if m:
                cur_no = max(cur_no, int(m.group(1)))
            m2 = re.search(r"==\s*步骤\s*(\d+)", line)
            if m2:
                cur_no = max(cur_no, int(m2.group(1)))
    except Exception:
        pass

    steps = []
    for no, name, script in STEPS:
        if (work / f".skip_step{no}").exists() and not (work / f".done_step{no}").exists():
            st = "skipped"
        elif (work / f".done_step{no}").exists():
            st = "done"
        elif no == cur_no:
            st = "running" if (alive and state == "running") else (
                "failed" if (exit_code not in (None, 0) and state != "stopped") else "pending")
        elif no < cur_no:
            st = "failed" if (exit_code not in (None, 0) and state != "stopped") else "done"
        else:
            st = "pending"
        steps.append({"no": no, "name": name, "script": script, "status": st})
    return steps


def status(run_id: str) -> dict | None:
    rd = _run_dir(run_id)
    mp = rd / "meta.json"
    if not mp.exists():
        return None
    meta = json.loads(mp.read_text(encoding="utf-8"))
    pid = meta.get("pid")
    alive = _proc_alive(pid)
    exit_code = meta.get("exit_code")
    if meta.get("state") == "running":
        if alive:
            pass
        elif exit_code is None:
            # 先看内存里的 Popen 有没有可收割的退出码
            rc = None
            proc = _PROCS.get(run_id)
            if proc is not None:
                try:
                    rc = proc.poll()
                except Exception:
                    rc = None
            if rc is None:
                # 进程没了且拿不到退出码（重启过服务等）——判为外力终止
                rc = -1
                meta["state"] = "failed"
            else:
                meta["state"] = "done" if rc == 0 else "failed"
            meta["exit_code"] = rc
            meta["ended"] = time.strftime("%F %T")
            mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        exit_code = meta["exit_code"]
    out = {
        "run_id": run_id,
        "mode": meta.get("mode"),
        "state": meta.get("state"),
        "started": meta.get("started"),
        "ended": meta.get("ended"),
        "exit_code": exit_code,
        "work": meta.get("work"),
        "alive": alive,
        "log_tail": _log_tail(rd),
        "steps": _steps_state(rd, meta),
        "note": meta.get("note", ""),
    }
    if meta.get("mode") == "manifest":
        out["gdc_client"] = meta.get("gdc_client")
        tail = "\n".join(out["log_tail"])
        if "BLOCKED_GDC" in tail:
            out["state"] = "blocked_gdc"
            out["note"] = "未安装 gdc-client：请等工具帮手装好，或手动下载后用 MAF/VCF 模式启动"
        elif "NOTE:" in tail:
            out["note"] = [l for l in out["log_tail"] if l.startswith("NOTE:")][0][6:]
    # done 的收尾:进程退出 0 且第 9 步 done
    steps = out["steps"]
    if exit_code == 0 and not alive and steps and steps[-1]["status"] == "done":
        out["state"] = "done"
        mp2 = json.loads(mp.read_text(encoding="utf-8"))
        mp2["state"] = "done"
        mp2["ended"] = mp2.get("ended") or time.strftime("%F %T")
        mp.write_text(json.dumps(mp2, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def stop(run_id: str) -> dict:
    rd = _run_dir(run_id)
    mp = rd / "meta.json"
    if not mp.exists():
        return {"ok": False, "error": "run 不存在"}
    meta = json.loads(mp.read_text(encoding="utf-8"))
    pid = meta.get("pid")
    killed = False
    if pid:
        try:
            os.killpg(os.getpgid(pid), 15)  # SIGTERM 整个进程组
            killed = True
        except Exception:
            try:
                os.kill(pid, 15)
                killed = True
            except Exception:
                killed = False
    if killed:
        meta["state"] = "stopped"
        meta["ended"] = time.strftime("%F %T")
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": killed}


def list_runs(limit: int = 8) -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    runs = []
    for mp in sorted(RUNS_DIR.glob("*/meta.json"), reverse=True)[:limit]:
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = meta.get("run_id") or mp.parent.name
        st = status(rid) or {}
        done_n = sum(1 for s in st.get("steps", []) if s["status"] == "done")
        runs.append({
            "run_id": rid, "mode": meta.get("mode"), "state": st.get("state"),
            "started": meta.get("started"), "work": meta.get("work"),
            "steps_done": f"{done_n}/9",
        })
    return runs


def save_upload(filename: str, data: bytes) -> dict:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name.replace("..", "_") or "upload.bin"
    stamp = time.strftime("%H%M%S")
    dst = UPLOAD_DIR / f"{stamp}_{safe}"
    dst.write_bytes(data)
    return {"path": str(dst), "size": len(data)}
