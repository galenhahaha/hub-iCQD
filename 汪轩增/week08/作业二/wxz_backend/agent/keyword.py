# -*- coding: utf-8 -*-
"""KeywordAgent：规划员，把研究主题拆成可检索关键词。"""
from __future__ import annotations

import logging

from .. import config
from ..models import KeywordOutput
from .base import BaseAgent

logger = logging.getLogger(__name__)


class KeywordAgent(BaseAgent):
    """把研究主题拆成 3-5 个可检索关键词（单次 LLM 调用，无工具）。"""

    def __init__(self):
        super().__init__("keyword", "keyword_agent.jinja2")

    async def generate_keywords(self, topic: str) -> list[str]:
        out = await self.call_json(
            {"topic": topic, "today": config.today_str()},
            topic,
            KeywordOutput,
        )
        logger.info("生成 %d 个关键词: %s", len(out.keywords), out.keywords)
        return out.keywords


if __name__ == "__main__":
    # 自检 demo：单次 LLM 生成关键词（需要 .env 密钥与网络，人工验证用）
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    async def main():
        keywords = await KeywordAgent().generate_keywords("2026 年 AI Agent 开发框架对比")
        print("关键词:", keywords)

    asyncio.run(main())
