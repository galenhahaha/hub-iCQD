"""Plan search keywords for a research topic."""

from .. import config
from ..models import KeywordOutput
from .base import BaseAgent


class KeywordAgent(BaseAgent):
    agent_name = "KeywordAgent"
    template_name = "keyword_agent.jinja2"

    async def generate_keywords(self, topic: str) -> list[str]:
        output = await self.call_json(
            {"topic": topic, "today": config.today_str()},
            topic,
            KeywordOutput,
        )
        # Leave the empty-plan fallback to the research engine.
        return list(dict.fromkeys(word.strip() for word in output.keywords if word.strip()))
