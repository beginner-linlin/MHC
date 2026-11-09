"""对外接入：应用自签 API 密钥 + 工具化 REST 接口。

设计要点
--------
1. 密钥由应用自己生成（`mhc_` + 32 位十六进制），只在创建时明文返回一次，
   库里只存 SHA-256 摘要与前缀，泄露数据库也拿不到可用密钥。
2. 鉴权只作用于 `/api/v1/*`（对外工具面），不影响工作台自身前端调用的
   `/api/jobs/*` 等内部路由，避免自锁。
3. `/api/v1/tools` 直接复用 agent 的工具注册表（`_REGISTRY`），
   所以「智能助手能做的事」和「外部 agent 能做的事」永远一致。
4. 同时提供 OpenAI function-calling 格式的 schema，外部 LLM 可直接吃。
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path
from typing import Any

from flask import jsonify, request

APP_ROOT = Path(__import__("os").environ.get("MHC_APP_ROOT", "/opt/bio/app"))
DATA_DIR = APP_ROOT / "data"
TOKEN_DB = DATA_DIR / "api_tokens.sqlite3"

TOKEN_PREFIX = "mhc_"


# ---------------------------------------------------------------- 存储


def _connect() -> sqlite3.Connection:
    TOKEN_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(TOKEN_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS api_tokens (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            prefix      TEXT NOT NULL,
            token_hash  TEXT NOT NULL UNIQUE,
            created_at  REAL NOT NULL,
            last_used_at REAL,
            calls       INTEGER NOT NULL DEFAULT 0,
            revoked     INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_token_hash ON api_tokens(token_hash)")
    return conn


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 密钥生命周期


def create_token(name: str = "") -> dict:
    """生成一枚新密钥。明文只在此处返回一次。"""
    token = TOKEN_PREFIX + secrets.token_hex(16)
    tid = secrets.token_hex(8)
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO api_tokens (id, name, prefix, token_hash, created_at) VALUES (?,?,?,?,?)",
            (tid, (name or "未命名").strip()[:60], token[:12], _hash(token), now),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": tid,
        "name": (name or "未命名").strip()[:60],
        "token": token,
        "prefix": token[:12],
        "created_at": now,
        "note": "密钥只显示这一次，请立即复制保存。",
    }


def list_tokens() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name, prefix, created_at, last_used_at, calls, revoked "
            "FROM api_tokens ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def revoke_token(tid: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("UPDATE api_tokens SET revoked = 1 WHERE id = ?", (tid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_token(tid: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM api_tokens WHERE id = ?", (tid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def verify_token(token: str) -> dict | None:
    """校验密钥；命中则更新 last_used_at / calls 并返回记录。"""
    if not token or not token.startswith(TOKEN_PREFIX):
        return None
    h = _hash(token)
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM api_tokens WHERE token_hash = ? AND revoked = 0", (h,)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE api_tokens SET last_used_at = ?, calls = calls + 1 WHERE id = ?",
            (time.time(), row["id"]),
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def has_any_token() -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT 1 FROM api_tokens WHERE revoked = 0 LIMIT 1").fetchone()
        return row is not None
    finally:
        conn.close()


# ---------------------------------------------------------------- 鉴权装饰器


def _extract_token() -> str:
    """支持 Authorization: Bearer xxx 与 X-API-Key: xxx 两种写法。"""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("X-API-Key", "").strip()


def require_token(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        tok = _extract_token()
        if not tok:
            return jsonify({
                "ok": False,
                "error": "缺少密钥。请在请求头带 Authorization: Bearer <密钥> 或 X-API-Key: <密钥>。",
                "hint": "密钥在「数据库与工具 → 对外接入」页面生成。",
            }), 401
        rec = verify_token(tok)
        if not rec:
            return jsonify({
                "ok": False,
                "error": "密钥无效或已被撤销。",
            }), 403
        request.environ["mhc_token"] = rec
        return fn(*a, **kw)

    return wrapper


# ---------------------------------------------------------------- 工具面


def tool_manifest() -> dict:
    """返回全部可用工具：OpenAI function schema + 简表。"""
    from . import agent

    schemas = agent.get_tools()
    items = []
    for s in schemas:
        f = s.get("function") or {}
        items.append({
            "name": f.get("name"),
            "description": f.get("description"),
            "parameters": f.get("parameters"),
        })
    return {
        "count": len(items),
        "tools": items,
        # 直接可喂给 OpenAI / DeepSeek / 通义等兼容接口的 tools 数组
        "openai_tools": schemas,
    }


def call_tool(name: str, args: dict) -> Any:
    from . import agent

    return agent.call_tool(name, args)


# ---------------------------------------------------------------- 路由注册


def register_routes(app) -> None:
    """把对外接口挂到 Flask app 上。"""

    # ---------- 密钥管理（仅本机前端用，不走 token 鉴权） ----------

    @app.get("/api/tokens")
    def api_tokens_list():
        return jsonify({"ok": True, "tokens": list_tokens(), "has_any": has_any_token()})

    @app.post("/api/tokens")
    def api_tokens_create():
        p = request.get_json(silent=True) or {}
        rec = create_token(p.get("name") or "")
        return jsonify({"ok": True, **rec})

    @app.delete("/api/tokens/<tid>")
    def api_tokens_delete(tid: str):
        if delete_token(tid):
            return jsonify({"ok": True, "deleted": tid})
        return jsonify({"ok": False, "error": "密钥不存在"}), 404

    @app.post("/api/tokens/<tid>/revoke")
    def api_tokens_revoke(tid: str):
        if revoke_token(tid):
            return jsonify({"ok": True, "revoked": tid})
        return jsonify({"ok": False, "error": "密钥不存在"}), 404

    # ---------- 对外工具面（需密钥） ----------

    @app.get("/api/v1/ping")
    @require_token
    def v1_ping():
        from . import __version__

        rec = request.environ.get("mhc_token") or {}
        return jsonify({
            "ok": True,
            "app": "MHC 预测工作台",
            "version": __version__,
            "token_name": rec.get("name"),
            "time": time.time(),
        })

    @app.get("/api/v1/tools")
    @require_token
    def v1_tools():
        return jsonify({"ok": True, **tool_manifest()})

    @app.post("/api/v1/tools/<name>")
    @require_token
    def v1_call(name: str):
        from . import agent

        if name not in agent._REGISTRY:
            return jsonify({
                "ok": False,
                "error": f"未知工具 {name}",
                "available": sorted(agent._REGISTRY.keys()),
            }), 404
        args = request.get_json(silent=True) or {}
        # 允许 {"args": {...}} 包裹，也允许直接扁平传参
        if isinstance(args, dict) and set(args.keys()) == {"args"} and isinstance(args["args"], dict):
            args = args["args"]
        t0 = time.time()
        result = call_tool(name, args)
        dt = time.time() - t0
        failed = isinstance(result, dict) and "error" in result
        return jsonify({
            "ok": not failed,
            "tool": name,
            "args": args,
            "result": result,
            "seconds": round(dt, 3),
        }), (200 if not failed else 400)

    # ---------- 便捷直连（把最常用的三个预测单独暴露，省掉一次 schema 查询） ----------

    @app.post("/api/v1/predict/binding")
    @require_token
    def v1_binding():
        p = request.get_json(silent=True) or {}
        return _proxy_tool("predict_binding", p)

    @app.post("/api/v1/predict/cleavage")
    @require_token
    def v1_cleavage():
        p = request.get_json(silent=True) or {}
        return _proxy_tool("predict_cleavage", p)

    @app.post("/api/v1/predict/stability")
    @require_token
    def v1_stability():
        p = request.get_json(silent=True) or {}
        return _proxy_tool("predict_stability", p)

    @app.post("/api/v1/pipeline")
    @require_token
    def v1_pipeline():
        p = request.get_json(silent=True) or {}
        return _proxy_tool("run_pipeline", p)

    @app.post("/api/v1/mutant")
    @require_token
    def v1_mutant():
        p = request.get_json(silent=True) or {}
        return _proxy_tool("screen_mutant", p)

    def _proxy_tool(name: str, args: dict):
        t0 = time.time()
        result = call_tool(name, args)
        dt = time.time() - t0
        failed = isinstance(result, dict) and "error" in result
        return jsonify({
            "ok": not failed,
            "tool": name,
            "result": result,
            "seconds": round(dt, 3),
        }), (200 if not failed else 400)
