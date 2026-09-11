"""研究任务接口：发起立即返回 id，前端轮询过程与产物。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status

from .. import research, storage
from ..core import config
from ..models import ResearchCreate, ResearchCreated, ResearchRecord, ResearchSummary

router = APIRouter()
_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "深度研究助手",
        "health": "/health",
        "docs": "/docs",
        "research": "/api/research",
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/research", status_code=status.HTTP_202_ACCEPTED, response_model=ResearchCreated)
async def create_research(body: ResearchCreate) -> ResearchCreated:
    topic = (body.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is missing")
    if not config.BOCHA_API_KEY:
        raise HTTPException(status_code=500, detail="BOCHA_API_KEY is missing")
    record = research.create_record(topic)
    _spawn(research.run_research(record.id))
    return ResearchCreated(id=record.id, status=record.status, topic=record.topic)


@router.get("/api/research", response_model=list[ResearchSummary])
async def list_research() -> list[ResearchSummary]:
    return storage.list_records()


@router.get("/api/research/{rid}", response_model=ResearchRecord)
async def get_research(rid: str) -> ResearchRecord:
    record = storage.load(rid)
    if record is None:
        raise HTTPException(status_code=404, detail="research not found")
    return record
