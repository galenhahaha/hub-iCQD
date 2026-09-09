"""
FastAPI 入口
============
- 用 lifespan 统一完成 配置 / LLM / 引擎 / 任务管理器 的组装与资源释放；
- 暴露 REST 接口：
    POST /api/v1/research            提交深度研究任务（异步），立即返回 task_id
    GET  /api/v1/research/{task_id}  轮询任务状态与结果
    GET  /api/v1/research/{task_id}/markdown  直接导出 Markdown 报告（完成后）

启动：python run.py   或   uvicorn app.main:app
接口文档：http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .engine import ResearchEngine
from .llm import LLMClient
from .schemas import ResearchRequest, TaskStatus
from .task_manager import ResearchTaskManager


# ===========================================================================
# 生命周期：启动时组装依赖，退出时释放资源
# ===========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- 启动阶段：构造全局单例 ----
    settings = Settings()
    llm = LLMClient(settings)          # 未配置 Key 也可构造，内部自动进入离线模式
    engine = ResearchEngine(settings, llm)
    manager = ResearchTaskManager(settings, engine)

    app.state.settings = settings
    app.state.llm = llm
    app.state.engine = engine
    app.state.manager = manager

    yield

    # ---- 关闭阶段：释放连接 ----
    await llm.aclose()


# ===========================================================================
# 应用对象
# ===========================================================================
app = FastAPI(
    title="深度研究助手 · Deep Research Assistant",
    version="0.1.0",
    description=(
        "输入一个研究主题，自动完成 多轮检索 → 阅读抽取 → 智能补检 → 综合生成，"
        "产出一份 带来源引用、可追溯、含置信度说明 的结构化研究报告。"
        "接口为「异步任务 + 结果轮询」模式。"
    ),
    lifespan=lifespan,
)

# 本地联调常需跨域（前端单独起服务时）；生产请按白名单收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# 工具：从 request 里取 manager 实例
# ===========================================================================
def _manager(request: Request) -> ResearchTaskManager:
    return request.app.state.manager


def _settings(request: Request) -> Settings:
    return request.app.state.settings


# ===========================================================================
# 路由
# ===========================================================================
@app.get("/", tags=["基础"])
async def root(request: Request) -> Dict[str, Any]:
    """服务信息与使用指引。"""
    settings = _settings(request)
    return {
        "app": settings.app_name,
        "version": settings.version,
        "research_mode": settings.research_mode,
        "docs": "/docs",
        "health": "/health",
        "create_task": "POST /api/v1/research",
        "poll_task": "GET /api/v1/research/{task_id}",
        "notice": (
            "当前已配置 LLM，将以完整模式（深度综合）运行。"
            if settings.llm_available
            else "未配置 LLM_API_KEY，任务将以离线模式生成基础报告；"
            "如需高质量深度研究，请在 .env 中配置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL。"
        ),
    }


@app.get("/health", tags=["基础"])
async def health(request: Request) -> Dict[str, str]:
    """健康检查。"""
    settings = _settings(request)
    return {"status": "ok", "research_mode": settings.research_mode}


@app.post("/api/v1/research", tags=["研究任务"])
async def create_research(req: ResearchRequest, request: Request) -> Dict[str, Any]:
    """提交一个深度研究任务。

    - 任务立即返回 task_id，研究与 HTTP 响应解耦（异步执行）；
    - 前端/客户端拿到 task_id 后，调用 GET 轮询接口追踪进度与最终结果。
    """
    manager = _manager(request)
    options = {
        "max_rounds": req.max_rounds,
        "results_per_query": req.results_per_query,
        "extra_instructions": req.extra_instructions,
    }
    entry = manager.submit(req.topic, options)

    notice = None
    if entry["research_mode"] == "offline":
        notice = (
            "当前未配置 LLM_API_KEY，任务将按「离线模式」执行（仅检索 + 机械拼装基础报告）。"
            "如需高质量深度研究，请配置 LLM_API_KEY 后重新提交。"
        )

    return {
        "task_id": entry["task_id"],
        "status": entry["status"].value,          # pending
        "research_mode": entry["research_mode"],
        "topic": req.topic,
        "poll_url": f"/api/v1/research/{entry['task_id']}",
        "notice": notice,
    }


@app.get("/api/v1/research/{task_id}", tags=["研究任务"])
async def get_research(task_id: str, request: Request) -> Dict[str, Any]:
    """轮询指定任务：返回实时阶段进展；完成后 result 里携带结构化研究报告。"""
    entry = _manager(request).get(task_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="任务不存在（可能已过期被清理）")

    # 枚举在 JSON 序列化时自动转成字符串值
    return entry


@app.get("/api/v1/research/{task_id}/markdown", tags=["研究任务"])
async def get_research_markdown(task_id: str, request: Request) -> Dict[str, Any]:
    """完成任务后，直接返回渲染好的 Markdown 报告文本（便于保存/粘贴）。"""
    entry = _manager(request).get(task_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="任务不存在（可能已过期被清理）")

    status = entry["status"]
    if status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(status_code=409, detail="任务仍在进行中，请稍后再试")
    if status == TaskStatus.FAILED:
        raise HTTPException(status_code=500, detail=entry.get("error"))

    result = entry.get("result") or {}
    return {
        "task_id": task_id,
        "markdown": result.get("markdown", "（无结果）"),
        "filename": f"deep_research_{task_id}.md",
    }
