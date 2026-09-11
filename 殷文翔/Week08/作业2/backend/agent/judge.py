"""Decide whether the current research needs additional searches."""

import json

from .. import config
from ..models import JudgeDecision, Source
from .base import BaseAgent


class JudgeAgent(BaseAgent):
    agent_name = "JudgeAgent"
    template_name = "judge_agent.jinja2"

    async def judge(
        self,
        topic: str,
        draft_text: str,
        sources: list[Source],
        searched_keywords: list[str],
    ) -> JudgeDecision:
        return await self.call_json(
            {"topic": topic, "today": config.today_str()},
            json.dumps(
                {
                    "draft": draft_text,
                    "sources": [source.model_dump() for source in sources],
                    "source_count": len(sources),
                    "searched_keywords": searched_keywords,
                },
                ensure_ascii=False,
            ),
            JudgeDecision,
        )
