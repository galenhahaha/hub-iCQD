# -*- coding: utf-8 -*-
"""ReportAgent：报告生成，两次 LLM 调用——先元信息，再渲染 HTML。"""
from __future__ import annotations

import json
import logging

from .. import config
from ..models import ReportContent, ReportOutline, Section
from .base import BaseAgent, strip_fence

logger = logging.getLogger(__name__)


class ReportAgent:
    """生成结构化报告 + HTML。

    第一次调用输出报告元信息 ReportOutline（title/summary/key_conclusions/open_questions），
    正文分节由草稿段落直接映射（heading=keyword、body=text，不走 LLM 重新组织）；
    第二次调用把组装好的 ReportContent 渲染成自包含 HTML。
    """

    def __init__(self):
        self._outline_agent = BaseAgent("report", "report_agent.jinja2")
        self._html_agent = BaseAgent("report_html", "report_html_agent.jinja2")

    async def generate(self, topic: str, draft: list, sources: list, confidence) -> tuple[ReportContent, str]:
        # 第一次：报告元信息
        user = json.dumps(
            {"draft": [d.model_dump() for d in draft], "sources": [s.model_dump() for s in sources]},
            ensure_ascii=False,
        )
        outline = await self._outline_agent.call_json(
            {"topic": topic, "today": config.today_str()},
            user,
            ReportOutline,
        )

        content = ReportContent(
            title=outline.title,
            summary=outline.summary,
            sections=[Section(heading=d.keyword, body=d.text) for d in draft],
            key_conclusions=outline.key_conclusions,
            open_questions=outline.open_questions,
        )

        # 第二次：渲染 HTML（final_output 即 HTML 原文，不包 JSON）
        html = await self._html_agent.run_text(
            {}, content.model_dump_json(indent=2, ensure_ascii=False)
        )
        html = strip_fence(html)
        logger.info("报告生成完成，HTML 长度=%d", len(html))
        return content, html


if __name__ == "__main__":
    # 自检 demo：生成结构化报告 + HTML（需要 .env 密钥与网络，人工验证用）
    import asyncio
    import logging

    from ..models import ConfidenceNote, DraftBlock, Source

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")

    async def main():
        draft = [DraftBlock(round=1, keyword="示例关键词", text="示例正文段落。")]
        sources = [Source(url="https://example.com", title="示例", date="2026-09-01")]
        content, html = await ReportAgent().generate(
            "测试主题", draft, sources, ConfidenceNote(overall="medium")
        )
        print("标题:", content.title)
        print("HTML 长度:", len(html))

    asyncio.run(main())
