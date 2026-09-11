"""Deterministic orchestration of planning, searches, summaries, and reports."""

from collections.abc import Awaitable, Callable, Iterable
from datetime import date
import inspect
import logging
from typing import Any

from . import config, tools
from .agent import JudgeAgent, KeywordAgent, ReportAgent, SummaryAgent
from .models import (
    ConfidenceNote,
    DeepResearchResult,
    DraftBlock,
    ProcessStep,
    ResearchProcess,
    Source,
)


logger = logging.getLogger(__name__)
ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class DeepResearch:
    """Run tool-free roles in a bounded research loop."""

    def __init__(self, topic: str) -> None:
        self.topic = topic
        self.keyword_agent = KeywordAgent()
        self.summary_agent = SummaryAgent()
        self.judge_agent = JudgeAgent()
        self.report_agent = ReportAgent()

    async def run(
        self,
        max_rounds: int | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> DeepResearchResult:
        """Publish detached snapshots after planning and each completed step."""
        limit = config.MAX_ROUNDS if max_rounds is None else max_rounds
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("max_rounds 必须是大于 0 的整数。")

        process = ResearchProcess(plan=[], search_queries=[], reviewed_urls=[])
        draft: list[DraftBlock] = []
        sources: list[Source] = []
        seen_urls: set[str] = set()
        searched: set[str] = set()
        all_dates: list[str] = []

        initial = await self.keyword_agent.generate_keywords(self.topic)
        todo = _new_keywords(initial, searched) or [self.topic]
        process.plan = list(todo)
        process.steps.append(ProcessStep(type="plan", detail={"keywords": list(todo)}))
        await self._progress(on_progress, process, draft, sources)

        for round_no in range(1, limit + 1):
            process.iterations = round_no
            for keyword in todo:
                searched.add(keyword)
                process.search_queries.append(keyword)
                search_detail: dict[str, Any] = {"keyword": keyword}
                try:
                    results = await tools.web_search(keyword)
                except Exception as exc:
                    # A single search failure is recoverable; cancellation still propagates.
                    results = []
                    search_detail["error"] = f"搜索失败：{type(exc).__name__}"
                    logger.warning("Search failed for %r (%s)", keyword, type(exc).__name__)
                _collect_sources(results, seen_urls, sources, process, all_dates)
                search_detail["results"] = len(results)
                process.steps.append(ProcessStep(type="search", round=round_no, detail=search_detail))
                await self._progress(on_progress, process, draft, sources)

                text = await self.summary_agent.summarize(self.topic, keyword, results)
                draft.append(DraftBlock(round=round_no, keyword=keyword, text=text))
                process.steps.append(
                    ProcessStep(type="summarize", round=round_no, detail={"keyword": keyword, "chars": len(text)})
                )
                await self._progress(on_progress, process, draft, sources)

            decision = await self.judge_agent.judge(
                self.topic, _join_draft(draft), sources, list(process.search_queries)
            )
            process.steps.append(ProcessStep(type="judge", round=round_no, detail=decision.model_dump()))
            await self._progress(on_progress, process, draft, sources)
            if decision.sufficient:
                break
            todo = _new_keywords(decision.new_keywords, searched)
            if not todo:
                break

        confidence = _compute_confidence(sources, draft, all_dates)
        report, report_html = await self.report_agent.generate(self.topic, draft, sources, confidence)
        return DeepResearchResult(
            report=report,
            report_html=report_html,
            sources=sources,
            draft=draft,
            process=process,
            confidence=confidence,
        )

    @staticmethod
    async def _progress(
        on_progress: ProgressCallback | None,
        process: ResearchProcess,
        draft: list[DraftBlock],
        sources: list[Source],
    ) -> None:
        if on_progress is None:
            return
        result = on_progress(
            {
                "process": process.model_dump(mode="json"),
                "draft": [block.model_dump(mode="json") for block in draft],
                "sources": [source.model_dump(mode="json") for source in sources],
            }
        )
        if inspect.isawaitable(result):
            await result


def _new_keywords(keywords: Iterable[str], searched: set[str]) -> list[str]:
    return list(dict.fromkeys(word.strip() for word in keywords if word.strip() and word.strip() not in searched))


def _collect_sources(
    results: list[dict[str, Any]],
    seen_urls: set[str],
    sources: list[Source],
    process: ResearchProcess,
    all_dates: list[str],
) -> None:
    """Keep first-seen source metadata, while accumulating dates for valid URLs."""
    for result in results:
        url = (result.get("url") or "").strip()
        if not url:
            continue
        if url not in seen_urls:
            seen_urls.add(url)
            process.reviewed_urls.append(url)
            sources.append(
                Source(
                    url=url,
                    title=result.get("title") or "",
                    site_name=result.get("site_name") or "",
                    snippet=result.get("snippet") or "",
                    accessed_at=config.today_str(),
                )
            )
        source_date = result.get("date")
        if source_date and source_date not in all_dates:
            all_dates.append(source_date)


def _join_draft(draft: list[DraftBlock]) -> str:
    return "\n\n".join(f"【关键词：{block.keyword}】\n{block.text}" for block in draft if block.text.strip())


def _latest_date(dates: list[str]) -> str:
    candidates = []
    for value in dates:
        try:
            candidates.append(date.fromisoformat(value[:10]))
        except (TypeError, ValueError):
            continue
    return max(candidates).isoformat() if candidates else ""


def _compute_confidence(
    sources: list[Source], draft: list[DraftBlock], all_dates: list[str]
) -> ConfidenceNote:
    """Grade distinct source counts; prefer the latest valid source date."""
    source_count = len({source.url for source in sources if source.url})
    overall = "high" if source_count >= 12 else "medium" if source_count >= 5 else "low"
    latest = _latest_date(all_dates)
    cutoff = latest or config.today_str()
    date_note = (
        f"信息截止时间取检索结果中的最新资料来源日期（{cutoff}）。"
        if latest
        else f"检索结果缺少有效资料日期，信息截止时间暂以检索当天（{cutoff}）代替。"
    )
    return ConfidenceNote(
        overall=overall,
        info_cutoff=cutoff,
        notes=[
            f"正文共 {len(draft)} 段，收集 {source_count} 个去重来源。",
            "来源数达到 12 为高、达到 5 为中，否则为低；该规则评级不等同于事实核验。",
            date_note,
            "未关联来源的结论须标注为“模型推断”。",
        ],
    )
