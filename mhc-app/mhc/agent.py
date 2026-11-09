"""Agent 模块：自然语言 → 数据库筛选 → 三工具预测 → 结果总结。

借鉴 BioAgent（github.com/yinyinglv0-lab/BioAgent）的极简 tool-calling 设计：
- 不用 LangChain，直接调 OpenAI 兼容 API（DeepSeek/GLM/Qwen/GPT 任一）
- 工具注册表：每工具 = 1 个函数 + 1 个 JSON Schema
- Errors as data：工具失败返回 {"error": ...}，由模型向用户解释
- 有界循环（默认 12 轮），超限自动收尾总结
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import urllib.request
import urllib.error
import urllib.parse

APP_ROOT = Path(os.environ.get("MHC_APP_ROOT", "/opt/bio/app"))
AGENT_DB = APP_ROOT / "data" / "agent.sqlite3"
MAX_TURNS = 12          # 工具调用轮数上限
HISTORY_WINDOW = 24      # 每次请求携带的历史消息条数
HTTP_TIMEOUT = 25

# ---------------------------------------------------------------- provider

@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""

    @classmethod
    def load(cls) -> "LLMConfig":
        cfg = _load_agent_config()
        return cls(
            base_url=cfg.get("base_url", "").rstrip("/"),
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", ""),
        )

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


_LLM_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_LLM_RETRY_DELAYS = (1.0, 3.0)   # 指数退避：第 1 次重试前 1s，第 2 次前 3s

# 平台控制台域名 → 正确的 OpenAI 兼容 API 端点示例（用户最常填错的地址）
# 注意：只收录「控制台域名 ≠ API 域名」的平台；智谱 open.bigmodel.cn 的控制台与
# API 同 host，故不在此列（否则会把正确端点误判为网页地址）。
_CONSOLE_HOST_HINTS = {
    "platform.deepseek.com": "https://api.deepseek.com",
    "platform.openai.com": "https://api.openai.com/v1",
    "console.moonshot.cn": "https://api.moonshot.cn/v1",
    "bailian.console.aliyun.com": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "cloud.siliconflow.cn": "https://api.siliconflow.cn/v1",
}

# 免费/低成本模型预设（base_url + 推荐 model）。用户只需填 API key。
MODEL_PRESETS = {
    "siliconflow": {
        "label": "SiliconFlow 免费 · Qwen2.5-7B-Instruct",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "hint": "登录 https://cloud.siliconflow.cn 创建 API 密钥（新用户有免费额度），填入下方 Key 即可",
    },
    "siliconflow-deepseek": {
        "label": "SiliconFlow · DeepSeek-V3",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "hint": "需账户有额度；推理质量更高",
    },
    "deepseek": {
        "label": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "hint": "platform.deepseek.com 注册拿 key",
    },
    "glm": {
        "label": "智谱 GLM-4-Flash（免费）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "hint": "open.bigmodel.cn 实名后可免费使用 glm-4-flash",
    },
    "qwen": {
        "label": "阿里云百炼 Qwen（免费额度）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "hint": "bailian.console.aliyun.com 开通后领免费额度",
    },
}


def get_model_presets() -> dict:
    """返回预设清单（含 label/base_url/model/hint），供前端下拉选择。"""
    return {k: {"label": v["label"], "base_url": v["base_url"], "model": v["model"],
                "hint": v.get("hint", "")} for k, v in MODEL_PRESETS.items()}


def _extract_title(html: str) -> str:
    """从上游 HTML 封锁页里提取 <title>（如 Error - Request Blocked）。"""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()[:60]


def _known_api_hosts() -> frozenset:
    """所有已收录的正确 API host（提示表 example + 预设 base_url），用于豁免误判。"""
    hosts = set()
    for example in _CONSOLE_HOST_HINTS.values():
        try:
            hosts.add(urllib.parse.urlparse(example).netloc.lower())
        except Exception:
            pass
    for p in MODEL_PRESETS.values():
        try:
            hosts.add(urllib.parse.urlparse(p["base_url"]).netloc.lower())
        except Exception:
            pass
    return frozenset(hosts)


_KNOWN_API_HOSTS = _known_api_hosts()


def _endpoint_hint(base_url: str) -> str:
    """base_url 疑似填成平台网页地址时给出正确端点示例。

    已知正确 API host（含智谱 open.bigmodel.cn）直接豁免，绝不误判。
    """
    try:
        host = urllib.parse.urlparse(base_url).netloc.lower()
    except Exception:
        return ""
    if host in _KNOWN_API_HOSTS:
        return ""
    for dom, example in _CONSOLE_HOST_HINTS.items():
        if dom in host:
            return f"当前 API 地址疑似填成了平台网页地址（{host}），正确端点示例：{example}。"
    return ""


def _cap(msg: str, limit: int = 200) -> str:
    return msg if len(msg) <= limit else msg[: limit - 1] + "…"


def _provider_of(base_url: str) -> str:
    """按 base_url host 识别 LLM 平台：deepseek / zhipu（智谱）/ 其他返回 ""。"""
    try:
        host = urllib.parse.urlparse(base_url or "").netloc.lower()
    except Exception:
        return ""
    if "deepseek" in host:
        return "deepseek"
    if "bigmodel.cn" in host or "zhipu" in host or "zhipuai" in host:
        return "zhipu"
    return ""


def _extract_upstream_error(body: str) -> tuple[str, str]:
    """从 JSON 错误响应提取 (message, error.code)。

    兼容两种结构：OpenAI 式 {"error": {"message": ...}}（无 code）与
    智谱式 {"error": {"code": "1002", "message": "..."}}。非 JSON 返回 ("", "")。
    """
    try:
        data = json.loads(body)
    except Exception:
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    err = data.get("error")
    code_val = ""
    if isinstance(err, dict):
        code_val = str(err.get("code") or "")
        msg = err.get("message")
        if isinstance(msg, dict):
            msg = str(msg.get("message") or json.dumps(msg, ensure_ascii=False)[:120])
        msg = str(msg or "") or str(err.get("type") or "")
    elif isinstance(err, str):
        msg = err
    else:
        msg = ""
    msg = msg or str(data.get("message") or "")
    return msg, code_val


def _key_length_hint(api_key: str, provider: str = "") -> str:
    """Key 长度可疑时的诊断提示（绝不回显 key 本身，只给长度）。"""
    key = api_key or ""
    if not key:
        return ""
    if provider == "zhipu":
        if len(key) < 20:
            return (f"注意：当前 Key 仅 {len(key)} 个字符，而正常智谱 Key 为 30+ 字符，"
                    f"疑似复制不完整或已截断，请重新完整复制。")
    elif provider == "deepseek":
        if len(key) < 20:
            return (f"注意：当前 Key 仅 {len(key)} 个字符，而正常 DeepSeek Key 以 sk- 开头、"
                    f"长度 30+，疑似复制不完整，请重新完整复制。")
    else:
        if len(key) < 15:
            return f"注意：当前 API Key 仅 {len(key)} 个字符，疑似复制不完整，请重新完整复制。"
    return ""


def _diagnose_llm_error(
    code: int, msg: str, err_code: str, base_url: str = "", api_key: str = "",
) -> tuple[str, str]:
    """把常见 LLM 错误细分成人话 + 可执行建议（平台感知：DeepSeek / 智谱 / 通用）。

    返回 (reason, suggestion)；无规则命中返回 ("", "")，由调用方走通用透传。
    """
    low = (msg or "").lower()
    provider = _provider_of(base_url)
    key_hint = _key_length_hint(api_key, provider)

    # ---- 智谱：错误码在 error.code 里（字符串；实测 401 时 code="401"，文档另有 1002/1113/1211）----
    if provider == "zhipu":
        if code == 401 or err_code in ("1002", "401"):
            if err_code in ("1002", "401") or "令牌" in msg or "token" in low or "无效" in msg:
                sug = ("请到 open.bigmodel.cn 用户中心重新创建 API Key 并完整复制（智谱 Key 为 "
                       "id.secret 格式、共 30+ 字符），粘贴到「智能助手 → 配置」后保存。")
                return "API Key 无效、已过期或被删除", (sug + key_hint)
            return ("认证失败", "请核对 Key 是否复制完整、是否属于 open.bigmodel.cn 平台。" + key_hint)
        if err_code == "1113" or code == 402 or "余额" in msg or "额度" in msg:
            return ("账户余额不足或免费额度已用完",
                    "请到 open.bigmodel.cn 充值或领取免费额度后重试（glm-4-flash 免费但需实名认证）。")
        if err_code == "1211" or (code in (400, 404) and ("model" in low or "模型" in msg)):
            return ("模型名无效",
                    "请到 open.bigmodel.cn 核对模型名（如 glm-4-flash、glm-4-plus），"
                    "在「智能助手 → 配置」里更换后再试。")

    # ---- DeepSeek：message 里带特征词 ----
    if provider == "deepseek":
        if code == 401:
            if "no such user" in low:
                return ("API Key 不存在或已被删除",
                        "请到 platform.deepseek.com/api_keys 重新创建，并把新 Key 填到「智能助手 → 配置」。" + key_hint)
            if "api key" in low or "api-key" in low:
                return ("API Key 无效或已过期",
                        "请重新创建并完整复制后再试（前后不应有多余空格或换行）。" + key_hint)
            return ("认证失败",
                    "请核对 Key 是否复制完整、是否属于当前 API 地址对应平台（platform.deepseek.com）。" + key_hint)
        if code == 402:
            return ("账户余额不足", "请到 platform.deepseek.com 充值后重试。")
        if code == 400 and ("model" in low or "模型" in msg):
            return ("模型名无效。DeepSeek 官方仅支持 deepseek-chat 与 deepseek-reasoner",
                    "请在「智能助手 → 配置」里把模型改为 deepseek-chat 或 deepseek-reasoner。")

    # ---- 通用兜底（其他平台 / 无法识别 host）----
    if code == 401:
        if "no such user" in low:
            return ("API Key 不存在或已被删除",
                    "请到对应平台重新创建 API Key，并把新 Key 填到「智能助手 → 配置」。")
        if "api key" in low or "api-key" in low or "令牌" in msg or "token" in low:
            return ("API Key 无效或已过期",
                    "请重新创建并完整复制后再试；请核对 Key 是否属于当前 API 地址对应平台。" + key_hint)
        return ("认证失败", "请核对 Key 是否复制完整、是否属于当前 API 地址对应的平台。" + key_hint)
    if code == 402:
        return ("账户余额不足", "请到对应平台控制台充值后重试。")
    if code == 400 and ("model" in low or "模型" in msg):
        return ("模型名无效", "请检查「智能助手 → 配置」里的模型拼写，或换成平台支持的模型。")
    return "", ""


def _humanize_llm_error(code: int, body: str, base_url: str = "", api_key: str = "") -> str:
    """把 LLM 上游错误响应转成一句人话；绝不透传整页 HTML / 长 CSS。

    401 / 402 / 400(模型名) 等常见错误按平台细分（DeepSeek / 智谱），给出可执行建议。
    """
    body = (body or "").strip()
    title = _extract_title(body) if ("<" in body[:400]) else ""
    hint = _endpoint_hint(base_url)
    tail = "请到「智能助手 → 配置」更换 API 地址或模型；若已确认地址正确请稍后重试。"
    if body.startswith("<") or "<html" in body[:200].lower():
        title_part = f"，{title}" if title else ""
        if code == 429:
            lead = f"模型服务限流（HTTP 429{title_part}）：{hint}"
        else:
            lead = f"模型服务异常（HTTP {code}{title_part}）：{hint}"
        return _cap(lead + tail)
    # JSON 错误响应：先按平台细分（401/402/400-model 等），未命中再透传 message
    msg, err_code = _extract_upstream_error(body)
    reason, sug = _diagnose_llm_error(code, msg, err_code, base_url, api_key)
    if reason:
        return _cap(f"模型服务返回错误（HTTP {code}）：{reason}。{sug}")
    if msg:
        return _cap(f"模型服务返回错误（HTTP {code}）：{msg}")
    plain = re.sub(r"\s+", " ", body)[:120] if body else "(空响应)"
    return _cap(f"模型服务返回错误（HTTP {code}）：{plain}")


def _parse_retry_after(val: str | None, fallback: float) -> float:
    try:
        return min(max(float(val), 0.2), 10.0)
    except (TypeError, ValueError):
        return fallback


def chat_completion(cfg: LLMConfig, messages: list[dict], tools: list[dict]) -> dict:
    """OpenAI 兼容 /chat/completions。返回解析后的 JSON。

    对 429 / 5xx / 网络错误做指数退避重试（最多 2 次重试，Retry-After 头优先，
    间隔约 1s / 3s）；错误信息统一美化成中文人话，绝不把上游 HTML 封锁页透传给用户。
    """
    url = f"{cfg.base_url}/chat/completions"
    payload: dict[str, Any] = {"model": cfg.model, "messages": messages, "temperature": 0.2}
    if tools:
        payload["tools"] = tools
    body = json.dumps(payload).encode("utf-8")
    max_attempts = 3  # 1 次原始请求 + 2 次重试
    last_err = ""
    for attempt in range(max_attempts):
        if attempt:
            time.sleep(_LLM_RETRY_DELAYS[attempt - 1] if attempt - 1 < len(_LLM_RETRY_DELAYS) else 3.0)
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT + 55) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8", "replace")
            last_err = _humanize_llm_error(e.code, resp_body, cfg.base_url, cfg.api_key)
            if e.code in _LLM_RETRYABLE_CODES and attempt < max_attempts - 1:
                time.sleep(_parse_retry_after(e.headers.get("Retry-After"), _LLM_RETRY_DELAYS[attempt]))
                continue
            raise RuntimeError(last_err) from e
        except Exception as e:  # 网络 / 连接失败等
            if attempt < max_attempts - 1:
                time.sleep(_LLM_RETRY_DELAYS[attempt])
                continue
            raise RuntimeError(_cap(f"LLM 服务连接失败：{e}；请检查网络与「智能助手 → 配置」里的 API 地址")) from e
        else:
            try:
                return json.loads(raw)
            except Exception:
                # HTTP 200 但不是 JSON：多半是地址配错（打到网页/网关），重试无意义
                title = _extract_title(raw)
                title_part = f"，{title}" if title else ""
                snippet = "" if title else re.sub(r"\s+", " ", raw.strip())[:100]
                snippet_part = f"：{snippet}" if snippet else ""
                raise RuntimeError(_cap(
                    f"模型服务返回了非 JSON 内容（HTTP 200{title_part}{snippet_part}）；"
                    "请检查「智能助手 → 配置」里的 API 地址是否为 OpenAI 兼容端点"
                ))
    raise RuntimeError(last_err or "LLM 请求失败")


def test_llm_connection(cfg: dict) -> dict:
    """连通性自检：用最小 chat 请求（max_tokens=4，超时 10s）探测配置是否可用。

    绝不抛异常，永远返回：
      {"ok": bool, "status": int|None, "message": str, "suggestion": str, "key_len": int}
    message / suggestion 全中文；日志与消息中绝不含完整 API Key。
    """
    def _get(d: dict, name: str) -> str:
        for k, v in (d or {}).items():
            if isinstance(k, str) and k.strip().lower() == name:
                return str(v or "").strip()
        return ""

    base_url = _get(cfg, "base_url").rstrip("/")
    api_key = _get(cfg, "api_key")
    model = _get(cfg, "model")
    key_len = len(api_key)

    missing = [n for n, v in (("base_url", base_url), ("api_key", api_key), ("model", model)) if not v]
    if missing:
        return {
            "ok": False, "status": None, "key_len": key_len,
            "message": f"配置不完整：缺少 {', '.join(missing)}。",
            "suggestion": "请到「智能助手 → 配置」填写完整的 API 地址、API Key 和模型名后保存。",
        }

    hint = _endpoint_hint(base_url)
    if hint:
        return {
            "ok": False, "status": None, "key_len": key_len,
            "message": hint,
            "suggestion": "API 地址应填平台提供的 OpenAI 兼容端点（而非平台网页地址），"
                          "可在「智能助手 → 配置」的预设下拉里直接选择对应平台。",
        }

    url = f"{base_url}/chat/completions"
    payload = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", None)
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8", "replace")
        msg, err_code = _extract_upstream_error(resp_body)
        reason, sug = _diagnose_llm_error(e.code, msg, err_code, base_url, api_key)
        if reason:
            return {"ok": False, "status": e.code, "key_len": key_len, "message": reason, "suggestion": sug}
        shown = msg or "平台未返回详细原因"
        return {
            "ok": False, "status": e.code, "key_len": key_len,
            "message": _cap(f"模型服务返回错误（HTTP {e.code}）：{shown}"),
            "suggestion": "请检查「智能助手 → 配置」里的 Key / 模型 / API 地址，或稍后重试。",
        }
    except Exception as e:
        return {
            "ok": False, "status": None, "key_len": key_len,
            "message": _cap(f"连接失败：{e}"),
            "suggestion": "请检查网络连接，以及「智能助手 → 配置」里的 API 地址是否为 OpenAI 兼容端点。",
        }

    # HTTP 200 但不是 JSON：多半打到网页 / 网关
    try:
        data = json.loads(raw)
    except Exception:
        title = _extract_title(raw)
        detail = f"页面标题：{title}" if title else "可能请求到了网页或网关页面"
        return {
            "ok": False, "status": status, "key_len": key_len,
            "message": f"模型服务返回了非 JSON 内容（{detail}）。",
            "suggestion": "请核对 API 地址是否为平台的 OpenAI 兼容端点（如 https://api.deepseek.com、"
                          "https://open.bigmodel.cn/api/paas/v4）。",
        }
    choices = (data or {}).get("choices") or []
    if not isinstance(data, dict) or not choices:
        return {
            "ok": False, "status": status, "key_len": key_len,
            "message": "服务响应格式异常（缺少 choices 字段）。",
            "suggestion": "请确认 API 地址为 OpenAI 兼容的 /chat/completions 端点。",
        }
    return {
        "ok": True, "status": status, "key_len": key_len,
        "message": f"连接成功：模型 {model} 可正常调用。",
        "suggestion": "配置可用，可直接保存使用。",
    }

# ---------------------------------------------------------------- 工具注册表

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema（object）
    func: Callable[..., Any]
    label: str = ""           # 前端显示名

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, Tool] = {}


def register(name: str, description: str, parameters: dict, label: str = ""):
    def deco(fn):
        _REGISTRY[name] = Tool(name, description, parameters, fn, label or name)
        return fn
    return deco


def get_tools() -> list[dict]:
    return [t.schema() for t in _REGISTRY.values()]


def call_tool(name: str, args: dict) -> Any:
    t = _REGISTRY.get(name)
    if not t:
        return {"error": f"未知工具 {name}"}
    try:
        return t.func(**args)
    except TypeError as e:
        return {"error": f"参数不匹配: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

# ---------------------------------------------------------------- 会话存储

def _connect():
    AGENT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(AGENT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT DEFAULT '',
            created_at REAL,
            updated_at REAL,
            message_count INTEGER DEFAULT 0
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,           -- user / assistant / tool_event
            content TEXT NOT NULL,
            created_at REAL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, id)")
    return conn


def new_session() -> dict:
    sid = uuid.uuid4().hex[:16]
    now = time.time()
    with _connect() as c:
        c.execute(
            "INSERT INTO sessions(id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (sid, "新对话", now, now),
        )
    return {"id": sid, "title": "新对话", "created_at": now}


def list_sessions(limit: int = 60) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT id, title, created_at, updated_at, message_count FROM sessions "
            "ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(sid: str) -> bool:
    with _connect() as c:
        cur = c.execute("DELETE FROM sessions WHERE id=?", (sid,))
        c.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        return cur.rowcount > 0


def append_message(sid: str, role: str, content: str):
    now = time.time()
    with _connect() as c:
        c.execute(
            "INSERT INTO messages(session_id, role, content, created_at) VALUES (?,?,?,?)",
            (sid, role, content, now),
        )
        c.execute(
            "UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?",
            (now, sid),
        )


def set_title(sid: str, title: str):
    with _connect() as c:
        c.execute("UPDATE sessions SET title=? WHERE id=?", (title[:60], sid))


def get_history(sid: str, limit: int = HISTORY_WINDOW) -> list[dict]:
    with _connect() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE session_id=? AND role IN ('user','assistant') "
            "ORDER BY id DESC LIMIT ?", (sid, limit)
        ).fetchall()
    msgs = []
    for r in reversed(rows):
        try:
            content = json.loads(r["content"])
            if isinstance(content, list):           # 历史里存的完整消息数组
                msgs.extend(content)
                continue
        except Exception:
            pass
        msgs.append({"role": r["role"], "content": r["content"]})
    return msgs

# ---------------------------------------------------------------- agent 设置

def _load_agent_config() -> dict:
    path = APP_ROOT / "data" / "agent_config.json"
    if path.exists():
        try:
            return json.loads(path.read_text("utf-8"))
        except Exception:
            pass
    return {}


def save_agent_config(cfg: dict):
    path = APP_ROOT / "data" / "agent_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # api_key 单独加密存储太薄；本机单用户场景直接明文，但绝不出现在前端回显里
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")


def get_agent_config_public() -> dict:
    cfg = _load_agent_config()
    key = cfg.get("api_key", "")
    return {
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", ""),
        "has_key": bool(key),
        "key_hint": f"{key[:6]}…{key[-4:]}" if len(key) >= 12 else "",
        "preset": cfg.get("preset", ""),
    }

# ---------------------------------------------------------------- HTTP 工具（三库，零 key）

def _http_get_json(url: str, headers: dict | None = None, retries: int = 2) -> Any:
    req_headers = {"Accept": "application/json", "User-Agent": "MHC-Workbench-Agent/1.0"}
    if headers:
        req_headers.update(headers)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            return {"error": f"{type(e).__name__}: {e}"}
    return {"error": "http_get_json 失败"}


def _fasta_of_uniprot(entry: str) -> str:
    """把 UniProt FASTA 文本解析成 {name, desc, seq}。"""
    url = f"https://rest.uniprot.org/uniprotkb/{urllib.parse.quote(entry)}.fasta"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return {"error": f"UniProt 请求失败: {e}"}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines or not lines[0].startswith(">"):
        return {"error": f"未取到 {entry} 的序列"}
    head = lines[0][1:]
    name = head.split("|")[1] if "|" in head else head.split()[0]
    return {"entry": name, "header": head, "sequence": "".join(lines[1:])}


@register(
    "query_uniprot",
    "按基因名/蛋白名/UniProt accession 查询蛋白信息与序列（UniProt REST，人类优先）。"
    "返回 accession、蛋白全名、功能摘要、长度、序列。得到序列后可直接交给预测工具。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "基因符号或蛋白名，如 EGFR、TP53、BRCA1"},
        },
        "required": ["query"],
    },
    label="查 UniProt",
)
def tool_query_uniprot(query: str) -> dict:
    q = query.strip()
    if not q:
        return {"error": "query 不能为空"}
    if re.fullmatch(r"[OPQ][0-9][A-Z0-9]{3}\d|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}\d){1,2}", q):
        return _uniprot_detail(q)
    url = (
        "https://rest.uniprot.org/uniprotkb/search?"
        + urllib.parse.urlencode(
            {
                "query": f"{q} AND (organism_id:9606)",
                "format": "json",
                "fields": "accession,protein_name,gene_names,length,ft_domain,cc_function",
                "size": "3",
            }
        )
    )
    data = _http_get_json(url)
    if isinstance(data, dict) and "error" in data:
        return data
    results = (data or {}).get("results") or []
    if not results:
        url2 = (
            "https://rest.uniprot.org/uniprotkb/search?"
            + urllib.parse.urlencode(
                {
                    "query": q,
                    "format": "json",
                    "fields": "accession,protein_name,gene_names,length",
                    "size": "3",
                }
            )
        )
        data = _http_get_json(url2)
        results = (data or {}).get("results") or []
    if not results:
        return {"error": f"UniProt 没有找到「{q}」"}
    out = []
    for r in results[:3]:
        acc = r.get("primaryAccession", "")
        names = (r.get("proteinDescription") or {}).get("recommendedName") or {}
        full = names.get("fullName", {}).get("value", "")
        genes = [g.get("geneName", {}).get("value", "") for g in r.get("genes", [])][:2]
        out.append({"accession": acc, "name": full, "genes": genes, "length": r.get("sequence", {}).get("length")})
    return {"query": q, "matches": out}


def _uniprot_detail(acc: str) -> dict:
    url = (
        "https://rest.uniprot.org/uniprotkb/search?"
        + urllib.parse.urlencode(
            {
                "query": f"accession:{acc}",
                "format": "json",
                "fields": "accession,protein_name,gene_names,sequence,cc_function",
            }
        )
    )
    data = _http_get_json(url)
    if isinstance(data, dict) and "error" in data:
        return data
    results = (data or {}).get("results") or []
    if not results:
        return {"error": f"UniProt 没有 {acc}"}
    r = results[0]
    names = (r.get("proteinDescription") or {}).get("recommendedName") or {}
    full = names.get("fullName", {}).get("value", "")
    seq = r.get("sequence", {}).get("value", "")
    func = ""
    for c in r.get("comments", []) or []:
        if c.get("commentType") == "FUNCTION":
            for t in c.get("texts", []) or []:
                func += t.get("value", "") + " "
            break
    return {
        "accession": acc,
        "name": full,
        "length": len(seq),
        "function": func.strip()[:500],
        "sequence": seq,
    }


@register(
    "get_protein_sequence",
    "按 UniProt accession 直接取蛋白氨基酸序列（FASTA）。需要完整序列喂给预测工具时用这个。",
    {
        "type": "object",
        "properties": {
            "entry": {"type": "string", "description": "UniProt accession，如 P00533"},
        },
        "required": ["entry"],
    },
    label="取蛋白序列",
)
def tool_get_sequence(entry: str) -> dict:
    return _fasta_of_uniprot(entry.strip())


@register(
    "query_clinvar",
    "按基因名查 ClinVar 临床意义变异（疾病相关的突变位点，含 HGVS 与临床分级）。",
    {
        "type": "object",
        "properties": {
            "gene": {"type": "string", "description": "基因符号，如 EGFR"},
        },
        "required": ["gene"],
    },
    label="查 ClinVar",
)
def tool_query_clinvar(gene: str) -> dict:
    g = gene.strip()
    if not g:
        return {"error": "gene 不能为空"}
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        + urllib.parse.urlencode(
            {"db": "clinvar", "term": f"{g}[gene] AND pathogenic[clinsig]", "retmax": "10", "retmode": "json"}
        )
    )
    data = _http_get_json(url)
    if isinstance(data, dict) and "error" in data:
        return data
    ids = (data.get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return {"gene": g, "variants": [], "note": "没有 pathogenic 级别变异"}
    url2 = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
        + urllib.parse.urlencode({"db": "clinvar", "id": ",".join(ids), "retmode": "json"})
    )
    data2 = _http_get_json(url2, retries=3)
    if isinstance(data2, dict) and "error" in data2:
        return data2
    out = []
    for vid in ids:
        item = (data2.get("result") or {}).get(vid) or {}
        if not item:
            continue
        # 真实 esummary 结构（2026 实测）：
        #   title（含 HGVS）、variation_set[0].cdna_change / variation_name、
        #   protein_change、germline_classification / clinical_impact_classification
        vs = item.get("variation_set") or []
        vs0 = vs[0] if vs and isinstance(vs[0], dict) else {}
        hgvs = vs0.get("cdna_change", "") or vs0.get("variation_name", "") or item.get("title", "")
        sig = ""
        for k in ("germline_classification", "clinical_impact_classification"):
            v = item.get(k)
            if isinstance(v, dict):
                sig = v.get("description", "") or v.get("clinical_significance", "") or ""
                if sig:
                    break
            elif isinstance(v, str) and v:
                sig = v
                break
        conds = []
        for c in (item.get("trait_set") or []) or []:
            if isinstance(c, dict) and c.get("name"):
                conds.append(c["name"])
        out.append(
            {
                "title": item.get("title", "")[:140],
                "hgvs": hgvs[:80],
                "protein_change": (item.get("protein_change") or "")[:40],
                "significance": sig,
                "conditions": conds[:3],
            }
        )
    return {"gene": g, "variants": out[:10]}


@register(
    "search_pubmed",
    "检索 PubMed 文献（标题+摘要线索）。用于给预测结论找文献佐证或了解靶点背景。",
    {
        "type": "object",
        "properties": {
            "term": {"type": "string", "description": "检索词，如 EGFR peptide vaccine"},
            "max_results": {"type": "integer", "description": "返回条数，默认 5，最大 10", "default": 5},
        },
        "required": ["term"],
    },
    label="查 PubMed",
)
def tool_search_pubmed(term: str, max_results: int = 5) -> dict:
    t = term.strip()
    if not t:
        return {"error": "term 不能为空"}
    n = max(1, min(10, int(max_results or 5)))
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"
        + urllib.parse.urlencode({"db": "pubmed", "term": t, "retmax": str(n), "retmode": "json"})
    )
    data = _http_get_json(url)
    if isinstance(data, dict) and "error" in data:
        return data
    res = data.get("esearchresult") or {}
    ids = res.get("idlist") or []
    total = res.get("count", "?")
    if not ids:
        return {"term": t, "total": total, "papers": []}
    url2 = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
        + urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
    )
    data2 = _http_get_json(url2)
    if isinstance(data2, dict) and "error" in data2:
        return data2
    out = []
    for pid in ids:
        item = (data2.get("result") or {}).get(pid) or {}
        if not item:
            continue
        out.append(
            {
                "pmid": pid,
                "title": item.get("title", ""),
                "journal": item.get("fulljournalname") or item.get("source", ""),
                "year": (item.get("pubdate") or "")[:4],
            }
        )
    return {"term": t, "total": total, "papers": out}

# ---------------------------------------------------------------- 预测工具（包装本地三件套）

def _run_local_job(kind: str, payload: dict) -> dict:
    """直接调用 Flask 应用内的任务函数（不经 HTTP）。

    走 web 层的 JobStore 单例，任务会出现在历史记录里（可导出）。
    fn(progress) 签名与 jobs.submit 一致；同步等待完成（上限 300s）。
    """
    from . import runner, pipeline as pl
    from .jobs import Progress
    from .web import store as _job_store, caller

    # create 的 params 必须可 JSON 序列化：FastaRecord/对象→dict，大序列截断
    serializable: dict = {}
    for k, v in payload.items():
        if k == "records":
            serializable["records"] = [{"name": r.name, "seq": r.seq} for r in v][:5]
        elif k == "peptides":
            serializable["peptides"] = list(v)[:2000]
        elif isinstance(v, (str, int, float, bool, list, dict)) and v is not None:
            serializable[k] = v

    job = _job_store.create(kind, payload.get("_title", "agent"), {"source": "agent", **serializable})
    result_box: dict = {}

    def fn(progress) -> dict:
        try:
            c = caller()
            if kind == "pan":
                rows, _, _ = runner.predict_binding(
                    c,
                    peptides=payload.get("peptides"),
                    records=payload.get("records"),
                    alleles=payload.get("alleles", []),
                    with_ba=payload.get("with_ba", True),
                    sort=payload.get("sort", False),
                    threshold=payload.get("threshold"),
                    lengths=payload.get("lengths"),
                )
                result_box["rows"] = [r.to_dict() if hasattr(r, "to_dict") else r for r in rows]
            elif kind == "chop":
                by_prot, _, _ = runner.predict_cleavage(
                    c,
                    records=payload.get("records", []),
                    version=payload.get("version", 0),
                    threshold=payload.get("threshold", 0.5),
                )
                rows = []
                for prot, ch_rows in by_prot.items():
                    for r in ch_rows:
                        d = r.to_dict() if hasattr(r, "to_dict") else r
                        d["protein"] = prot
                        rows.append(d)
                result_box["rows"] = rows
            elif kind == "stab":
                rows, _ = runner.predict_stability_mixed(
                    c,
                    payload.get("peptides", []),
                    payload.get("alleles", []),
                    with_ia=payload.get("with_ia", True),
                )
                result_box["rows"] = [r.to_dict() if hasattr(r, "to_dict") else r for r in rows]
            elif kind == "pipeline":
                pr = pl.run_pipeline(
                    c,
                    records=payload.get("records", []),
                    alleles=payload.get("alleles", []),
                    params=payload.get("params", dict(pl.PIPE_DEFAULTS)),
                    progress=progress,
                )
                result_box["rows"] = pr.rows
                result_box["steps"] = [s.to_dict() for s in pr.steps]
            elif kind == "mutant":
                subs = pl.find_substitutions(payload["ref_seq"], payload["alt_seq"])
                peps = pl.mutant_peptides(payload["ref_seq"], payload["alt_seq"], payload.get("lengths", [9]))
                rows, _, _ = runner.predict_binding(
                    c, peptides=[p["peptide"] for p in peps], alleles=payload.get("alleles", []),
                    with_ba=True,
                )
                by_pep = {r.peptide: r for r in rows}
                out_rows = []
                for p in peps:
                    r = by_pep.get(p["peptide"])
                    if not r:
                        continue
                    out_rows.append(
                        {
                            "pos": p["pos"], "peptide": p["peptide"], "ref_peptide": p["ref_peptide"],
                            "mutation": " / ".join(f"{m['ref']}{m['pos']}{m['alt']}" for m in p["mut_sites"]),
                            "mhc": r.mhc, "rank_el": r.rank_el, "score_el": r.score_el,
                            "aff_nm": r.aff_nm, "bind_pan": r.bind or "—",
                        }
                    )
                result_box["rows"] = out_rows
                result_box["mutations"] = [
                    {"pos": s[0], "ref": s[1], "alt": s[2]} for s in subs
                ]
            else:
                result_box["error"] = f"未知 kind {kind}"
        except Exception as e:
            result_box["error"] = f"{type(e).__name__}: {e}"
        return result_box

    _job_store.submit(job, fn)
    j = _job_store.get(job.id)
    timeout = time.time() + 300
    while j and j.status in ("queued", "running") and time.time() < timeout:
        time.sleep(0.25)
        j = _job_store.get(job.id)
    if not j:
        return {"error": "任务丢失"}
    if j.status != "done":
        return {"error": f"任务{ '失败' if j.status=='failed' else j.status }: {j.error or ''}"}
    res = j.result if isinstance(j.result, dict) else {}
    return {
        "job_id": job.id,
        "rows": res.get("rows", []),
        "steps": res.get("steps", []),
        "count": len(res.get("rows", [])),
    }


def _summary_of_rows(rows: list[dict], top_key: str = "rank_el") -> dict:
    """把行结果压缩成模型可读的摘要（行数、SB/WB、Top 表）——防止上下文爆炸。"""
    if not rows:
        return {"count": 0}
    n = len(rows)
    sb = sum(1 for r in rows if r.get("bind") == "<= SB" or r.get("bind_pan") == "<= SB")
    wb = sum(1 for r in rows if r.get("bind") == "<= WB" or r.get("bind_pan") == "<= WB")
    def key(r):
        v = r.get(top_key)
        return v if isinstance(v, (int, float)) else 9999
    top = sorted(rows, key=key)[:15]
    slim = []
    for r in top:
        d = {}
        for k in ("peptide", "mhc", "hla", "rank_el", "aff_nm", "bind", "bind_pan",
                  "thalf", "rank_stab", "combined_rank", "protein", "identity",
                  "pos", "mutation", "ref_peptide", "cut_score"):
            if k in r and r[k] is not None:
                d[k] = r[k]
        slim.append(d)
    return {"count": n, "strong_binders": sb, "weak_binders": wb, "top_rows": slim,
            "note": "只展示前 15 行，完整结果可用 job_id 在工作台历史里导出"}


@register(
    "predict_binding",
    "预测肽段-MHC 结合（NetMHCpan 4.2e）。输入肽列表或蛋白序列+等位基因，返回 %Rank、亲和力 nM、SB/WB 分级摘要。",
    {
        "type": "object",
        "properties": {
            "peptides": {"type": "array", "items": {"type": "string"},
                         "description": "肽列表（8-60aa）。与 fasta 二选一"},
            "fasta": {"type": "string",
                      "description": "蛋白序列（纯氨基酸或 FASTA 格式），自动滑窗切肽。与 peptides 二选一"},
            "alleles": {"type": "array", "items": {"type": "string"},
                        "description": "HLA 等位基因列表，写法 HLA-A02:01（不带星号）"},
            "threshold": {"type": "number", "description": "只保留 %Rank≤该值的行，如 2；省略则全保留"},
        },
        "required": ["alleles"],
    },
    label="结合预测",
)
def tool_predict_binding(peptides=None, fasta=None, alleles=None, threshold=None) -> dict:
    from . import runner
    if not alleles:
        return {"error": "必须提供 alleles"}
    peptides = peptides or []
    records = []
    if fasta:
        records = runner.parse_fasta(fasta) if runner.looks_like_fasta(fasta) else []
        if not records:
            peptides = [l.strip().upper() for l in fasta.splitlines() if l.strip() and not l.startswith(">")]
    if not peptides and not records:
        return {"error": "需要 peptides 或 fasta 之一"}
    out = _run_local_job("pan", {
        "peptides": peptides, "records": records,
        "alleles": runner.resolve_alleles(alleles),
        "with_ba": True, "threshold": threshold,
    })
    if "error" in out:
        return out
    out["summary"] = _summary_of_rows(out.pop("rows", []))
    return out


@register(
    "predict_cleavage",
    "预测蛋白酶体切割位点（NetChop 3.1d）。输入蛋白序列，返回切割概率与位点摘要。",
    {
        "type": "object",
        "properties": {
            "fasta": {"type": "string", "description": "蛋白序列（FASTA 或纯序列）"},
            "model": {"type": "integer", "enum": [0, 1], "description": "0=C-term 3.0（默认），1=20S 3.0"},
            "threshold": {"type": "number", "description": "切割判定阈值 0-1，默认 0.5"},
        },
        "required": ["fasta"],
    },
    label="酶切预测",
)
def tool_predict_cleavage(fasta: str, model: int = 0, threshold: float = 0.5) -> dict:
    from . import runner
    records = runner.parse_fasta(fasta)
    if not records:
        seq = "".join(l.strip() for l in fasta.splitlines() if not l.startswith(">"))
        if not seq:
            return {"error": "fasta 为空"}
        records = [runner.FastaRecord("seq", seq)]
    out = _run_local_job("chop", {"records": records, "version": model, "threshold": threshold})
    if "error" in out:
        return out
    rows = out.pop("rows", [])
    sites = [r for r in rows if r.get("cleavage") == "S"]
    by_prot: dict[str, int] = {}
    for r in sites:
        by_prot[r.get("protein", "?")] = by_prot.get(r.get("protein", "?"), 0) + 1
    return {"count": len(rows), "cleavage_sites": len(sites),
            "sites_by_protein": by_prot,
            "first_sites": [r["pos"] for r in sites[:40]],
            "job_id": out.get("job_id")}


@register(
    "predict_stability",
    "预测 pMHC 复合物稳定性（NetMHCstabpan 1.0，含亲和力综合分）。输入肽列表+等位基因。",
    {
        "type": "object",
        "properties": {
            "peptides": {"type": "array", "items": {"type": "string"}, "description": "肽列表（7-20aa，可混合长度）"},
            "alleles": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["peptides", "alleles"],
    },
    label="稳定性预测",
)
def tool_predict_stability(peptides, alleles) -> dict:
    from . import runner
    if not peptides or not alleles:
        return {"error": "必须提供 peptides 和 alleles"}
    out = _run_local_job("stab", {
        "peptides": [p.upper() for p in peptides],
        "alleles": runner.resolve_alleles(alleles), "with_ia": True,
    })
    if "error" in out:
        return out
    out["summary"] = _summary_of_rows(out.pop("rows", []), top_key="combined_rank")
    return out


@register(
    "run_pipeline",
    "三工具串联流水线：酶切→候选肽→结合预测→稳定性（一次跑完）。输入蛋白序列+等位基因。",
    {
        "type": "object",
        "properties": {
            "fasta": {"type": "string", "description": "蛋白序列（FASTA 或纯序列）"},
            "alleles": {"type": "array", "items": {"type": "string"}},
            "peptide_lengths": {"type": "array", "items": {"type": "integer"},
                                "description": "肽长列表，默认 [9]"},
            "rank_cutoff": {"type": "number", "description": "结合筛选 %Rank 阈值，默认 2.0"},
        },
        "required": ["fasta", "alleles"],
    },
    label="流水线",
)
def tool_run_pipeline(fasta: str, alleles, peptide_lengths=None, rank_cutoff: float = 2.0) -> dict:
    from . import runner, pipeline as pl
    records = runner.parse_fasta(fasta)
    if not records:
        seq = "".join(l.strip() for l in fasta.splitlines() if not l.startswith(">"))
        if not seq:
            return {"error": "fasta 为空"}
        records = [runner.FastaRecord("seq", seq)]
    if not alleles:
        return {"error": "必须提供 alleles"}
    params = dict(pl.PIPE_DEFAULTS)
    if peptide_lengths:
        params["lengths"] = peptide_lengths
    params["rank_cutoff"] = rank_cutoff
    out = _run_local_job("pipeline", {
        "records": records, "alleles": runner.resolve_alleles(alleles), "params": params,
    })
    if "error" in out:
        return out
    out["summary"] = _summary_of_rows(out.pop("rows", []))
    return out


@register(
    "screen_mutant",
    "新抗原筛选：野生型/突变型序列比对 → 只预测覆盖突变位点的肽（结合+可选稳定性）。",
    {
        "type": "object",
        "properties": {
            "ref_seq": {"type": "string", "description": "野生型蛋白序列（纯氨基酸）"},
            "alt_seq": {"type": "string", "description": "突变型蛋白序列（与野生型等长）"},
            "alleles": {"type": "array", "items": {"type": "string"}},
            "peptide_lengths": {"type": "array", "items": {"type": "integer"}, "description": "默认 [9]"},
        },
        "required": ["ref_seq", "alt_seq", "alleles"],
    },
    label="突变筛选",
)
def tool_screen_mutant(ref_seq: str, alt_seq: str, alleles, peptide_lengths=None) -> dict:
    from . import runner
    ref = "".join(ref_seq.split()).upper()
    alt = "".join(alt_seq.split()).upper()
    if len(ref) != len(alt):
        return {"error": f"两序列必须等长（{len(ref)} vs {len(alt)}）"}
    if ref == alt:
        return {"error": "两序列完全相同，无突变位点"}
    if not alleles:
        return {"error": "必须提供 alleles"}
    out = _run_local_job("mutant", {
        "ref_seq": ref, "alt_seq": alt,
        "alleles": runner.resolve_alleles(alleles),
        "lengths": peptide_lengths or [9],
    })
    if "error" in out:
        return out
    out["summary"] = _summary_of_rows(out.pop("rows", []))
    return out

# ---------------------------------------------------------------- 主循环

SYSTEM_PROMPT = """你是 MHC 预测工作台的科研助手，服务对象是免疫学/肿瘤学研究人员。
你的职责：理解用户的自然语言需求 → 调用工具（数据库查询 + 本地预测）→ 汇总成专业结论。

可用能力：
- 数据库：UniProt（蛋白信息/序列）、ClinVar（临床变异）、PubMed（文献）
- 预测：结合预测(predict_binding)、酶切(predict_cleavage)、稳定性(predict_stability)、
  串联流水线(run_pipeline)、新抗原突变筛选(screen_mutant)

工作规则：
1. 先想清楚步骤再调用工具；一次只解决一个子任务。
2. 需要蛋白序列时：先 query_uniprot 找 accession，再用 get_protein_sequence 取序列，然后交给预测工具。
3. 等位基因写法必须是不带星号的 HLA-A02:01 形式；用户给 HLA-A*02:01 或 HLA-A0201 时你要负责转换。
4. 大任务（如多条蛋白）用 run_pipeline 分批跑，把每批摘要记下来最后统一总结。
5. 工具返回 error 时：向用户解释原因并给出替代方案（比如换关键词、换等位基因），不要重复失败调用。
6. 最终回答用中文 Markdown：结论先行；预测结果给 Top 表格（肽段/等位基因/%Rank/亲和力/半衰期）；
   给出 SB/WB 统计；注明数据来源（工具名）；给后续实验建议（合成哪些肽、验证顺序）。
7. 不编造数据：所有数字必须来自工具返回；没有结果就说没有。"""


def run_agent_turn(sid: str, user_text: str, on_event: Callable[[dict], None] | None = None):
    """执行一轮 agent 对话。on_event 用于 SSE 推送事件流。"""
    cfg = LLMConfig.load()
    if not cfg.ready:
        yield {"type": "error", "message": "尚未配置大模型 API。请先在「智能助手」页的设置里填写 base_url / api_key / model。"}
        return
    emit = on_event or (lambda e: None)

    history = get_history(sid)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "user", "content": user_text}]
    tools = get_tools()

    append_message(sid, "user", user_text)
    if not history:
        set_title(sid, user_text[:30])

    turns = 0
    final_text = ""
    tool_calls_log: list[dict] = []

    while turns < MAX_TURNS:
        turns += 1
        try:
            resp = chat_completion(cfg, messages, tools)
        except RuntimeError as e:
            yield {"type": "error", "message": str(e)}
            return
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        calls = msg.get("tool_calls") or []

        if not calls:
            final_text = content
            break

        messages.append({
            "role": "assistant", "content": content,
            "tool_calls": calls,
        })
        for call in calls:
            fn = (call.get("function") or {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            emit({"type": "tool_start", "name": name, "args": args})
            result = call_tool(name, args)
            # 截断超长结果保护上下文
            text = json.dumps(result, ensure_ascii=False)
            if len(text) > 12000:
                if isinstance(result, dict):
                    for k in ("sequence",):
                        if k in result and isinstance(result[k], str) and len(result[k]) > 3000:
                            result[k] = result[k][:3000] + f"…(共{len(text)}字符已截断)"
                    text = json.dumps(result, ensure_ascii=False)
                if len(text) > 12000:
                    text = text[:12000] + "…(已截断)"
            event = {"type": "tool_result", "name": name,
                     "ok": not (isinstance(result, dict) and "error" in result),
                     "preview": text[:400]}
            emit(event)
            tool_calls_log.append({"name": name, "args": args, "ok": event["ok"]})
            messages.append({
                "role": "tool", "tool_call_id": call.get("id", ""), "content": text,
            })

    else:
        # 达到轮数上限：强制收尾
        messages.append({
            "role": "user",
            "content": "（系统提示：工具调用轮数已达上限，请立即基于已有结果给出最终总结，不要再调用工具。）",
        })
        try:
            resp = chat_completion(cfg, messages, [])
            final_text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        except RuntimeError as e:
            final_text = f"总结生成失败：{e}"
        if not final_text:
            final_text = "（已达工具调用上限，且未能生成总结。）"

    append_message(sid, "assistant", final_text)
    yield {"type": "final", "message": final_text, "turns": turns, "tools": tool_calls_log}
