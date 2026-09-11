"""FastAPI 入口：CORS、日志、挂载路由。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router
from .core import config

logger = logging.getLogger(__name__)

_CHROME_DEVTOOLS_PATHS = ("/json/version", "/json/list")


class _SkipChromeDevtoolsProbe(logging.Filter):
    """Cursor / Chrome 会探测本机调试端口，忽略这些访问日志。"""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, dict):
            path = str(args.get("full_path") or args.get("path") or "")
        elif isinstance(args, (tuple, list)) and len(args) >= 3:
            path = str(args[2])
        else:
            path = record.getMessage()
        return not any(probe in path for probe in _CHROME_DEVTOOLS_PATHS)


def _quiet_chrome_devtools_probes() -> None:
    access = logging.getLogger("uvicorn.access")
    if any(isinstance(f, _SkipChromeDevtoolsProbe) for f in access.filters):
        return
    access.addFilter(_SkipChromeDevtoolsProbe())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    _quiet_chrome_devtools_probes()
    logger.info("deep research api ready, max_rounds=%s", config.RESEARCH_MAX_ROUNDS)
    yield


app = FastAPI(title="深度研究助手", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    routes = [f"{r.methods} {r.path}" for r in app.routes if hasattr(r, "path")]
    print("routes", routes)
    import uvicorn

    uvicorn.run(
        "backend.app:app",
        host=config.BACKEND_HOST,
        port=config.BACKEND_PORT,
        reload=True,
    )
