# -*- coding: utf-8 -*-
"""JudgeAgent：进度评估员，判断已有草稿是否足够、是否需要补检。"""
from __future__ import annotations

import json
import logging

from ..models import JudgeDecision
from .base import BaseAgent

logger = logging.getLogger(__name__)


class JudgeAgent(BaseAgent):
    """判断是否补检 + 生成新关键词（单次 LLM 调用，无工具）。"""

    def __init__(self):
        super().__init__("judge", "judge_agent.jinja2")

    async def judge(self, topic: str, draft_text: str, sources: list, searched: list[str]) -> JudgeDecision:
        user = json.dumps(
            {"searched": searched, "draft": draft_text, "sources": sources},
            ensure_ascii=False,
        )
        decision = await self.call_json({"topic": topic}, user, JudgeDecision)
        logger.info("判断结果 sufficient=%s, reason=%s", decision.sufficient, decision.reason)
        return decision


if __name__ == "__main__":
    # 自检 demo：判断补检（需要 .env 密钥与网络，人工验证用）
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    async def main():
        decision = await JudgeAgent().judge(
            "测试主题", "已累积的正文草稿……", [], ["已检索关键词"]
        )
        print("决策:", decision.model_dump())

    asyncio.run(main())
