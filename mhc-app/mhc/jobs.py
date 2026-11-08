"""任务管理与历史记录（SQLite）。

设计：所有耗时操作都在后台线程执行，前端通过 /api/jobs/<id> 轮询进度。
任务状态与结果写入 SQLite，重启应用后可回看历史。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    params      TEXT NOT NULL,
    status      TEXT NOT NULL,
    progress    REAL NOT NULL DEFAULT 0,
    stage       TEXT NOT NULL DEFAULT '',
    message     TEXT NOT NULL DEFAULT '',
    result      TEXT,
    error       TEXT,
    created_at  REAL NOT NULL,
    started_at  REAL,
    finished_at REAL,
    seconds     REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs(kind, created_at DESC);
"""

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    kind: str
    title: str
    params: dict
    status: str = STATUS_QUEUED
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    result: Any = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    seconds: float | None = None

    def to_dict(self, *, include_result: bool = True) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "params": self.params,
            "status": self.status,
            "progress": round(self.progress, 4),
            "stage": self.stage,
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "seconds": self.seconds,
        }
        if include_result:
            d["result"] = self.result
        return d


class Progress:
    """传给任务函数的进度回调。"""

    def __init__(self, store: "JobStore", job_id: str):
        self._store = store
        self._job_id = job_id
        self._cancel = threading.Event()

    def update(self, stage: str, progress: float, message: str = "") -> None:
        if self._cancel.is_set():
            raise JobCancelled()
        self._store.update_progress(self._job_id, stage, progress, message)

    def check(self) -> None:
        if self._cancel.is_set():
            raise JobCancelled()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


class JobCancelled(Exception):
    pass


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._progress: dict[str, Progress] = {}
        with self._conn() as con:
            con.executescript(SCHEMA)
        self._mark_orphans()

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _mark_orphans(self) -> None:
        """上次异常退出时残留的 running 任务标记为失败。"""
        with self._lock, self._conn() as con:
            con.execute(
                "UPDATE jobs SET status=?, error=? WHERE status IN (?,?)",
                (STATUS_FAILED, "应用已重启，任务中断", STATUS_RUNNING, STATUS_QUEUED),
            )

    # ------------------------------------------------------------ 写

    def create(self, kind: str, title: str, params: dict) -> Job:
        job = Job(id=uuid.uuid4().hex[:16], kind=kind, title=title, params=params)
        with self._lock, self._conn() as con:
            con.execute(
                "INSERT INTO jobs(id,kind,title,params,status,progress,stage,message,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (job.id, job.kind, job.title, json.dumps(params, ensure_ascii=False),
                 job.status, 0, "", "", job.created_at),
            )
        return job

    def update_progress(self, job_id: str, stage: str, progress: float, message: str) -> None:
        with self._lock, self._conn() as con:
            con.execute(
                "UPDATE jobs SET stage=?, progress=?, message=? WHERE id=?",
                (stage, max(0.0, min(1.0, progress)), message, job_id),
            )

    def mark_running(self, job_id: str) -> None:
        with self._lock, self._conn() as con:
            con.execute(
                "UPDATE jobs SET status=?, started_at=?, stage=? WHERE id=?",
                (STATUS_RUNNING, time.time(), "准备中", job_id),
            )

    def mark_done(self, job_id: str, result: Any) -> None:
        with self._lock, self._conn() as con:
            row = con.execute("SELECT started_at FROM jobs WHERE id=?", (job_id,)).fetchone()
            started = row["started_at"] if row else None
            now = time.time()
            con.execute(
                "UPDATE jobs SET status=?, progress=1.0, stage=?, message=?, result=?,"
                " finished_at=?, seconds=? WHERE id=?",
                (STATUS_DONE, "完成", "", json.dumps(result, ensure_ascii=False, default=str),
                 now, (now - started) if started else None, job_id),
            )

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock, self._conn() as con:
            row = con.execute("SELECT started_at FROM jobs WHERE id=?", (job_id,)).fetchone()
            started = row["started_at"] if row else None
            now = time.time()
            con.execute(
                "UPDATE jobs SET status=?, stage=?, message=?, error=?, finished_at=?, seconds=?"
                " WHERE id=?",
                (STATUS_FAILED, "失败", "", error, now,
                 (now - started) if started else None, job_id),
            )

    def mark_cancelled(self, job_id: str) -> None:
        with self._lock, self._conn() as con:
            con.execute(
                "UPDATE jobs SET status=?, stage=?, message=?, finished_at=? WHERE id=?",
                (STATUS_CANCELLED, "已取消", "", time.time(), job_id),
            )

    # ------------------------------------------------------------ 读

    def get(self, job_id: str) -> Job | None:
        with self._conn() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list(self, limit: int = 100, kind: str | None = None, offset: int = 0) -> list[Job]:
        sql = "SELECT * FROM jobs"
        args: list[Any] = []
        if kind:
            sql += " WHERE kind=?"
            args.append(kind)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._conn() as con:
            rows = con.execute(sql, args).fetchall()
        return [self._row_to_job(r) for r in rows]

    def count(self, kind: str | None = None) -> int:
        sql = "SELECT COUNT(*) c FROM jobs"
        args: list[Any] = []
        if kind:
            sql += " WHERE kind=?"
            args.append(kind)
        with self._conn() as con:
            return con.execute(sql, args).fetchone()["c"]

    def delete(self, job_id: str) -> bool:
        with self._lock, self._conn() as con:
            cur = con.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            return cur.rowcount > 0

    def clear_all(self) -> int:
        with self._lock, self._conn() as con:
            cur = con.execute("DELETE FROM jobs")
            return cur.rowcount

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            params=json.loads(row["params"]) if row["params"] else {},
            status=row["status"],
            progress=row["progress"],
            stage=row["stage"],
            message=row["message"],
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            seconds=row["seconds"],
        )

    # ------------------------------------------------------------ 执行

    def submit(self, job: Job, fn: Callable[[Progress], Any]) -> Job:
        """在后台线程执行 fn(progress)，结果写库。"""
        progress = Progress(self, job.id)
        self._progress[job.id] = progress

        def worker() -> None:
            self.mark_running(job.id)
            try:
                result = fn(progress)
                if progress.cancelled:
                    self.mark_cancelled(job.id)
                else:
                    self.mark_done(job.id, result)
            except JobCancelled:
                self.mark_cancelled(job.id)
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
                if hasattr(exc, "to_dict"):
                    detail = json.dumps(exc.to_dict(), ensure_ascii=False)
                tb = traceback.format_exc()
                self.mark_failed(job.id, f"{detail}\n\n{tb}" if not hasattr(exc, "to_dict") else detail)
            finally:
                self._progress.pop(job.id, None)

        threading.Thread(target=worker, name=f"job-{job.id}", daemon=True).start()
        return job

    def cancel(self, job_id: str) -> bool:
        p = self._progress.get(job_id)
        if p:
            p.cancel()
            return True
        return False

    def running_count(self) -> int:
        return len(self._progress)
