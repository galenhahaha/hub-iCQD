"""
本地启动入口
============
用法：  python run.py
等价于： uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import uvicorn

from app.config import Settings


if __name__ == "__main__":
    cfg = Settings()
    # reload 仅建议在 DEBUG=1 的开发环境开启
    uvicorn.run(
        "app.main:app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.debug,
    )
