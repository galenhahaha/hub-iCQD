# -*- coding: utf-8 -*-
"""研究编排：后台执行研究循环，中间结果逐步落盘，最终落盘。"""
from __future__ import annotations

import logging

from . import config, storage
from .engine import DeepResearch
from .models import DraftBlock, ResearchProcess, Source, Status

logger = logging.getLogger(__name__)


async def run_research(research_id: str, topic: str) -> None:
    """后台执行一次完整研究，边跑边把中间结果写盘（status 保持 running），结束时写入最终产物。"""
    engine = DeepResearch()

    async def on_progress(snapshot: dict) -> None:
        rec = storage.get(research_id)
        if rec is None:
            return
        rec.process = ResearchProcess.model_validate(snapshot["process"])
        rec.draft = [DraftBlock.model_validate(d) for d in snapshot["draft"]]
        rec.sources = [Source.model_validate(s) for s in snapshot["sources"]]
        storage.save(rec)

    storage.update_status(research_id, "running")
    logger.info("研究开始 research_id=%s topic=%s", research_id, topic)
    try:
        result = await engine.run(topic, config.MAX_ROUNDS, on_progress)
        rec = storage.get(research_id)
        if rec is None:
            return
        rec.status = Status.completed
        rec.report = result.report
        rec.report_html = result.report_html
        rec.sources = result.sources
        rec.draft = result.draft
        rec.process = result.process
        rec.confidence = result.confidence
        storage.save(rec)
        logger.info("研究完成 research_id=%s", research_id)
    except Exception as e:
        logger.exception("研究失败 research_id=%s", research_id)
        storage.update_status(research_id, "failed", error=str(e))


if __name__ == "__main__":
    # 自检 demo：完整研究 + 落盘（端到端，需要 .env 密钥与网络，人工验证用）
    import asyncio
    import logging
    import uuid

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    async def main():
        rid = uuid.uuid4().hex
        await run_research(rid, "2026 年 AI Agent 开发框架对比")
        rec = storage.get(rid)
        print("状态:", rec.status if rec else "缺失")
        print("标题:", rec.report.title if rec and rec.report else "-")

    asyncio.run(main())
