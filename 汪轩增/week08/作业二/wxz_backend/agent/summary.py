# -*- coding: utf-8 -*-
"""SummaryAgent：资料阅读员，把一次搜索结果综合成一段报告正文（纯文字）。"""
from __future__ import annotations

import json
import logging

from .base import BaseAgent, strip_fence

logger = logging.getLogger(__name__)


class SummaryAgent(BaseAgent):
    """把一次搜索结果综合成一段正文文字（产物是字符串，不走 JSON 解析）。"""

    def __init__(self):
        super().__init__("summary", "summary_agent.jinja2")

    async def summarize(self, topic: str, keyword: str, results: list[dict]) -> str:
        user = json.dumps(results, ensure_ascii=False)
        text = await self.run_text({"topic": topic, "keyword": keyword}, user)
        text = strip_fence(text)
        logger.info("关键词 %r 总结出 %d 字正文", keyword, len(text))
        return text


if __name__ == "__main__":
    # 自检 demo：总结一次搜索结果（需要 .env 密钥与网络，人工验证用）
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    async def main():
        sample = [
            {"title": "示例", "url": "https://example.com", "snippet": "一段示例摘要", "site_name": "example", "date": "2026-09-01"}
        ]
        text = await SummaryAgent().summarize("测试主题", "测试关键词", sample)
        print("正文:", text)

    asyncio.run(main())
