#!/usr/bin/env python3
"""MHC 预测工作台 —— 后端入口。

用法：
    python serve.py                # 默认 127.0.0.1:8008
    MHC_PORT=9000 python serve.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mhc.web import app, store  # noqa: E402


def main() -> None:
    port = int(os.environ.get("MHC_PORT", "8008"))
    host = os.environ.get("MHC_HOST", "127.0.0.1")
    print(f"MHC 工作台后端启动于 http://{host}:{port}", flush=True)
    print(f"历史记录数据库：{store.db_path}", flush=True)
    app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
