"""后台执行一次研究：改状态、跑循环、逐步落盘。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from . import storage
from .engine import run_loop
from .models import ResearchRecord

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def create_record(topic: str) -> ResearchRecord:
    ts = _now()
    record = ResearchRecord(
        id=new_id(),
        topic=topic.strip(),
        status="pending",
        created_at=ts,
        updated_at=ts,
    )
    storage.save(record)
    return record


async def _on_progress(record: ResearchRecord) -> None:
    record.status = "running"
    storage.save(record)


async def run_research(rid: str) -> None:
    record = storage.load(rid)
    if record is None:
        logger.error("research missing id=%s", rid)
        return
    record.status = "running"
    record.updated_at = _now()
    storage.save(record)
    logger.info("research start id=%s topic=%s", rid, record.topic)
    try:
        await run_loop(record, on_progress=_on_progress)
        record.status = "completed"
        record.error = None
        record.updated_at = _now()
        storage.save(record)
        logger.info("research completed id=%s", rid)
    except Exception as exc:
        logger.exception("research failed id=%s", rid)
        latest = storage.load(rid) or record
        latest.status = "failed"
        latest.error = str(exc)
        latest.updated_at = _now()
        storage.save(latest)


if __name__ == "__main__":
    import asyncio
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    rec = create_record("本地自检主题（不会自动跑完整研究）")
    loaded = storage.load(rec.id)
    print("created", rec.id, loaded.status if loaded else None)
    # 清理自检记录
    path = storage._path(rec.id)
    if path.exists():
        path.unlink()
        print("cleaned")
