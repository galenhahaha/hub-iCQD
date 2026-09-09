"""Summarize search snippets into one draft paragraph."""

import json
import re
from typing import Any

from .. import config
from .base import BaseAgent


class SummaryAgent(BaseAgent):
    agent_name = "SummaryAgent"
    template_name = "summary_agent.jinja2"

    async def summarize(
        self, topic: str, keyword: str, results: list[dict[str, Any]]
    ) -> str:
        text = await self._run(
            {"topic": topic, "keyword": keyword, "today": config.today_str()},
            json.dumps(results, ensure_ascii=False),
        )
        # Accept a single accidental Markdown fence without parsing prose as JSON.
        text = text.strip()
        fence = re.fullmatch(r"```[^\r\n]*\r?\n(.*?)\r?\n```", text, re.DOTALL)
        return fence.group(1).strip() if fence else text
