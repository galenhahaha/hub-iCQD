"""Generate report metadata, preserve draft sections, then request HTML."""

import json

from .. import config
from ..models import (
    ConfidenceNote,
    DraftBlock,
    ReportContent,
    ReportOutline,
    Section,
    Source,
    SourceRef,
)
from .base import BaseAgent


class ReportAgent(BaseAgent):
    agent_name = "ReportAgent"
    template_name = "report_agent.jinja2"

    async def generate(
        self,
        topic: str,
        draft: list[DraftBlock],
        sources: list[Source],
        confidence: ConfidenceNote,
    ) -> tuple[ReportContent, str]:
        system_vars = {"topic": topic, "today": config.today_str()}
        source_data = [source.model_dump() for source in sources]
        outline = await self.call_json(
            system_vars,
            json.dumps(
                {
                    "draft": [block.model_dump() for block in draft],
                    "sources": source_data,
                    "confidence": confidence.model_dump(),
                },
                ensure_ascii=False,
            ),
            ReportOutline,
        )

        # Keep only references present in the collected source list.
        source_by_url = {source.url: source for source in sources}
        for conclusion in outline.key_conclusions:
            urls = dict.fromkeys(ref.url for ref in conclusion.sources)
            conclusion.sources = [
                SourceRef(url=url, title=source_by_url[url].title)
                for url in urls
                if url in source_by_url
            ]
            if not conclusion.sources:
                conclusion.is_model_inference = True

        report = ReportContent(
            title=outline.title,
            summary=outline.summary,
            sections=[Section(heading=block.keyword, body=block.text) for block in draft],
            key_conclusions=outline.key_conclusions,
            open_questions=outline.open_questions,
        )
        html = await self._run(
            system_vars,
            json.dumps(
                {
                    "report": report.model_dump(),
                    "sources": source_data,
                    "confidence": confidence.model_dump(),
                },
                ensure_ascii=False,
            ),
            template_name="report_html_agent.jinja2",
        )
        return report, html
